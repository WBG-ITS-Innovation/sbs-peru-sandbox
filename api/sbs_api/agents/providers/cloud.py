# SPDX-License-Identifier: Apache-2.0
"""CloudProvider — Azure OpenAI chat completions with native tool calling.

Interface-identical to :class:`~sbs_api.agents.providers.on_prem.OnPremProvider`:
``complete()`` takes the accumulated OpenAI-style message array plus the
tool schemas the agent is allowed to call, and returns a
:class:`~sbs_api.agents.providers.base.ModelResponse` carrying either
final ``text`` or ``tool_calls``. The runtime cannot tell the two
providers apart, which is the point — the SBS workstation runs on_prem
later without touching agent code.

**Credentials.** Read from the four variables WBG ITS issues, by their
existing bare names: ``AZURE_OPENAI_API_KEY``, ``AZURE_OPENAI_ENDPOINT``,
``AZURE_OPENAI_DEPLOYMENT``, ``AZURE_OPENAI_API_VERSION``. They arrive
through ``Settings`` (see config.py) so this module keeps the one-env-seam
contract the package docstring describes. The key is never logged, never
put in an exception message, and never included in a repr: every string
this module emits passes through :meth:`CloudProvider._redact` first.

**Legal gate.** ``SBS_API_CLOUD_LEGAL_APPROVED`` must be true or the
constructor raises. Setting it asserts development use against synthetic
data only, pending legal sign-off on PII isolation and data residency
(ADR 0001 §Divergence, amended). It is an opt-in, not a sign-off.

**Redaction before egress.** This is the only provider that puts complaint
content on infrastructure the authority does not run, so ``complete()`` passes
every string in the payload through the redaction engine immediately before
building the request body — see :mod:`sbs_api.agents.providers.egress` for why
the boundary is here rather than at each upstream call site. One
``cloud_inference_audit`` row is written per outbound call recording the
deployment, the complaint, whether redaction ran, and entity counts by kind;
it stores no text, raw or redacted.

**Parameter dialects.** Azure deployments disagree about two request
fields. The current ``gpt-5.4`` deployment rejects ``max_tokens``
("Unsupported parameter: 'max_tokens' is not supported with this model.
Use 'max_completion_tokens' instead.", HTTP 400 ``unsupported_parameter``)
while older ``gpt-4o``-class deployments accept only ``max_tokens``; some
reasoning deployments also reject a non-default ``temperature``. Rather
than pin one dialect and break on the other, the provider sends the
modern form first and, on a 400 that names the offending parameter,
retries once with the older form and remembers the answer for the life of
the process. One wasted request per process, no configuration to get
wrong.
"""

from __future__ import annotations

import json
import logging
import ssl
import time
import uuid
from typing import Any

import httpx

# Imported softly on purpose. ``providers/__init__`` imports this module to
# expose the factory, so a hard import would mean a host without the openai
# SDK could not run the on_prem or replay providers either — the agent
# dispatch would die with ModuleNotFoundError before reaching any provider
# choice. (Observed: the arq worker container, whose venv volume predated
# the dependency, failed every Tier 2 dispatch this way.) Only constructing
# a CloudProvider requires the SDK, and that failure is reported like any
# other missing cloud prerequisite.
try:
    import openai
except ImportError:  # pragma: no cover - exercised by deployment, not tests
    openai = None  # type: ignore[assignment]

from sbs_api.agents.providers.base import (
    ModelResponse,
    ProviderUnavailableError,
    ToolCallRequest,
    Usage,
)
from sbs_api.agents.providers.egress import redact_messages
from sbs_api.agents.providers.egress_audit import (
    record_cloud_egress,
    summarise_for_log,
)
from sbs_api.agents.providers.egress_capture import capture_redacted_payload

log = logging.getLogger(__name__)

# Env-var names, quoted verbatim in operator-facing errors so the reader
# knows which line of .env to fix. Values never appear.
_REQUIRED_ENV = (
    ("AZURE_OPENAI_API_KEY", "azure_openai_api_key"),
    ("AZURE_OPENAI_ENDPOINT", "azure_openai_endpoint"),
    ("AZURE_OPENAI_DEPLOYMENT", "azure_openai_deployment"),
    ("AZURE_OPENAI_API_VERSION", "azure_openai_api_version"),
)


def _settings() -> Any:
    """Build a fresh ``Settings``.

    Deliberately not ``get_settings()``: ``reset_provider_cache()`` is the
    documented way to switch providers mid-process, and an ``lru_cache``-d
    Settings would pin whatever the environment held at import time. Same
    reasoning as ``providers/__init__._provider_from_settings``.
    """

    from sbs_api.config import Settings  # local import: avoid cycle

    return Settings()


class CloudProvider:
    """Azure OpenAI provider. Safe to share across requests."""

    name = "cloud"

    def __init__(self, settings: Any | None = None) -> None:
        s = settings or _settings()

        if openai is None:
            raise ProviderUnavailableError(
                self.name,
                "the 'openai' package is not installed in this environment, "
                "so the Azure client cannot be built. It is a declared "
                "dependency: run `uv sync`. In a container, the venv volume "
                "may predate the dependency — recreate it.",
            )

        if not s.cloud_legal_approved:
            raise ProviderUnavailableError(
                self.name,
                "SBS_API_CLOUD_LEGAL_APPROVED is not true. The cloud path "
                "sends prompt content to Azure OpenAI; setting the flag "
                "asserts development use with synthetic data only, pending "
                "legal sign-off on PII isolation and data residency "
                "(ADR 0001). Use SBS_API_MODEL_PROVIDER=on_prem for "
                "supervisory-grade content.",
            )

        missing = [env for env, attr in _REQUIRED_ENV if not getattr(s, attr, "")]
        if missing:
            raise ProviderUnavailableError(
                self.name,
                f"missing required environment variable(s): {', '.join(missing)}. "
                "Fill them in .env (see .env.example); values come from WBG "
                "ITS or the Azure portal.",
            )

        # Held only to redact it back out of anything we emit.
        self._key: str = s.azure_openai_api_key
        self._deployment: str = s.azure_openai_deployment
        self._endpoint: str = s.azure_openai_endpoint
        self._api_version: str = s.azure_openai_api_version
        self._timeout: float = s.cloud_timeout_seconds

        # A corporate TLS-terminating proxy presents a root certifi does
        # not carry, so httpx must be pointed at a bundle that does.
        # Unset (the default) keeps stock certifi verification. Passing the
        # path as ``verify=`` is deprecated in httpx, hence the explicit
        # SSLContext — and building it here means a bad path fails at
        # construction, not on the first completion.
        ca_bundle: str = s.cloud_ca_bundle
        http_client = None
        if ca_bundle:
            try:
                ssl_context = ssl.create_default_context(cafile=ca_bundle)
            except (OSError, ssl.SSLError) as exc:
                raise ProviderUnavailableError(
                    self.name,
                    f"SBS_API_CLOUD_CA_BUNDLE={ca_bundle!r} is not a readable "
                    f"PEM bundle: {exc}",
                ) from exc
            http_client = httpx.AsyncClient(
                verify=ssl_context, timeout=self._timeout
            )
        self._ca_bundle = ca_bundle

        self._client = openai.AsyncAzureOpenAI(
            api_key=self._key,
            azure_endpoint=self._endpoint,
            api_version=self._api_version,
            timeout=self._timeout,
            max_retries=s.cloud_max_retries,
            http_client=http_client,
        )

        # Request-dialect state, resolved on first 400 (see module docstring).
        self._token_limit_param = "max_completion_tokens"
        self._send_temperature = True

        log.info(
            "cloud provider ready: deployment=%s api_version=%s "
            "ca_bundle=%s (key present, not logged)",
            self._deployment,
            self._api_version,
            ca_bundle or "<certifi default>",
        )

    def __repr__(self) -> str:  # pragma: no cover - defensive
        # Never let a stack trace or debugger print the credential.
        return (
            f"CloudProvider(deployment={self._deployment!r}, "
            f"api_version={self._api_version!r}, key=<redacted>)"
        )

    def _redact(self, text: str) -> str:
        """Blank the API key out of any string before it is emitted."""
        if self._key and self._key in text:
            return text.replace(self._key, "<redacted>")
        return text

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        agent_name: str | None = None,
        complaint_id: str | None = None,
    ) -> ModelResponse:
        # --- egress boundary -------------------------------------------------
        # Last thing before the request body exists: redact every string the
        # payload carries. Structural rather than trusting each upstream call
        # site to have done it (see providers/egress.py). The agent's own
        # message history is not mutated — only the copy that goes on the wire.
        redacted_messages, entity_counts = redact_messages(messages)
        redacted_chars = sum(
            len(m["content"]) for m in redacted_messages if isinstance(m.get("content"), str)
        )

        # Written before the call, because the audited event is the egress and
        # not its outcome. Never raises, never blocks (see egress_audit.py).
        await record_cloud_egress(
            complaint_id=complaint_id,
            agent_name=agent_name,
            model_id=self._deployment,
            redaction_applied=True,
            entity_counts=entity_counts,
            message_count=len(redacted_messages),
            redacted_chars=redacted_chars,
        )
        log.info(
            "cloud.egress.redacted",
            extra={
                "event": "cloud.egress.redacted",
                "deployment": self._deployment,
                "agent_name": agent_name,
                "complaint_id": complaint_id,
                "message_count": len(redacted_messages),
                **summarise_for_log(entity_counts),
            },
        )
        # Verification hook, off unless SBS_API_CLOUD_EGRESS_CAPTURE_PATH is
        # set and refused outside dev/test. Takes the redacted payload only —
        # there is no path here that can see the raw messages. stage-h-full's
        # cloud leg reads it to prove planted PII never egressed.
        capture_redacted_payload(
            redacted_messages=redacted_messages,
            entity_counts=entity_counts,
            complaint_id=complaint_id,
            agent_name=agent_name,
            model_id=self._deployment,
        )
        # ---------------------------------------------------------------------

        request: dict[str, Any] = {
            "model": self._deployment,  # Azure routes on deployment name
            "messages": redacted_messages,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"

        started = time.monotonic()
        try:
            body = await self._create_adapting_dialect(request, temperature, max_tokens)
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            raise ProviderUnavailableError(
                self.name,
                f"cannot reach Azure OpenAI deployment {self._deployment!r}: "
                f"{type(exc).__name__}. Check AZURE_OPENAI_ENDPOINT, network "
                f"reachability, and SBS_API_CLOUD_CA_BUNDLE if TLS is "
                f"intercepted. {self._redact(str(exc))}",
            ) from exc
        except openai.AuthenticationError as exc:
            # Status only — never the response body, never the header.
            raise ProviderUnavailableError(
                self.name,
                f"Azure OpenAI rejected the credential (HTTP {exc.status_code}). "
                "AZURE_OPENAI_API_KEY may be expired, rotated, or scoped to a "
                "different resource than AZURE_OPENAI_ENDPOINT.",
            ) from exc
        except openai.APIStatusError as exc:
            raise ProviderUnavailableError(
                self.name,
                f"Azure OpenAI returned HTTP {exc.status_code} for deployment "
                f"{self._deployment!r}: {self._redact(str(exc.message))}",
            ) from exc

        latency_ms = int((time.monotonic() - started) * 1000)

        choices = body.choices or []
        if not choices:
            log.warning(
                "cloud provider returned no choices: deployment=%s agent=%s",
                self._deployment,
                agent_name,
            )
            return ModelResponse(
                served_by=self.name,
                text="",
                model_id=body.model or self._deployment,
                latency_ms=latency_ms,
                finish_reason="error",
            )

        choice = choices[0]
        msg = choice.message
        finish = choice.finish_reason or "stop"

        tool_calls: list[ToolCallRequest] = []
        for raw in msg.tool_calls or []:
            fn = getattr(raw, "function", None)
            if fn is None:  # non-function tool type (e.g. custom); skip
                continue
            try:
                arguments = json.loads(fn.arguments or "{}")
            except json.JSONDecodeError:
                # A truncated or malformed argument blob is the model's
                # error, not a transport failure: record it as an empty
                # call so the loop's TOOL_NOT_ALLOWED / tool-error path
                # captures it in the trace rather than aborting the run.
                log.warning(
                    "cloud provider: unparseable tool arguments for %s "
                    "(agent=%s complaint=%s)",
                    fn.name,
                    agent_name,
                    complaint_id,
                )
                arguments = {}
            tool_calls.append(
                ToolCallRequest(
                    id=raw.id or f"call-{uuid.uuid4().hex[:8]}",
                    name=fn.name or "",
                    arguments=arguments,
                )
            )

        usage = Usage()
        if body.usage is not None:
            usage = Usage(
                prompt_tokens=body.usage.prompt_tokens or 0,
                completion_tokens=body.usage.completion_tokens or 0,
                total_tokens=body.usage.total_tokens or 0,
            )

        log.info(
            "cloud completion: deployment=%s model=%s finish=%s tool_calls=%d "
            "latency_ms=%d tokens=%d agent=%s complaint=%s",
            self._deployment,
            body.model,
            finish,
            len(tool_calls),
            latency_ms,
            usage.total_tokens,
            agent_name,
            complaint_id,
        )

        return ModelResponse(
            served_by=self.name,
            text=msg.content,
            tool_calls=tool_calls,
            usage=usage,
            model_id=body.model or self._deployment,
            latency_ms=latency_ms,
            finish_reason=finish,
        )

    async def _create_adapting_dialect(
        self, request: dict[str, Any], temperature: float, max_tokens: int
    ) -> Any:
        """POST the completion, learning the deployment's parameter dialect.

        Deployments disagree on ``max_completion_tokens`` vs ``max_tokens``
        and on whether ``temperature`` may be set at all. Azure answers a
        wrong guess with HTTP 400 and names the parameter in ``param``, so
        one retry is enough to settle each — and the answer is cached on
        the instance, which the factory keeps for the process lifetime.
        """

        for _ in range(3):  # at most two corrections, then give up
            attempt = dict(request)
            attempt[self._token_limit_param] = max_tokens
            if self._send_temperature:
                attempt["temperature"] = temperature
            try:
                return await self._client.chat.completions.create(**attempt)
            except openai.BadRequestError as exc:
                param = _rejected_param(exc)
                if param in ("max_completion_tokens", "max_tokens"):
                    flipped = (
                        "max_tokens"
                        if self._token_limit_param == "max_completion_tokens"
                        else "max_completion_tokens"
                    )
                    log.info(
                        "cloud provider: deployment=%s rejected %s; "
                        "retrying with %s",
                        self._deployment,
                        param,
                        flipped,
                    )
                    self._token_limit_param = flipped
                    continue
                if param == "temperature":
                    log.info(
                        "cloud provider: deployment=%s rejected an explicit "
                        "temperature; dropping it (determinism now depends on "
                        "the deployment default)",
                        self._deployment,
                    )
                    self._send_temperature = False
                    continue
                raise

        raise ProviderUnavailableError(
            self.name,
            f"deployment {self._deployment!r} rejected the request parameters "
            "after adapting both the token-limit field and temperature. Check "
            "AZURE_OPENAI_API_VERSION supports tool calling.",
        )

    async def aclose(self) -> None:
        """Release the underlying HTTP connection pool."""
        await self._client.close()


def _rejected_param(exc: openai.BadRequestError) -> str | None:
    """Return the request field Azure named in a 400, if any."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            param = err.get("param")
            if isinstance(param, str):
                return param
    return None
