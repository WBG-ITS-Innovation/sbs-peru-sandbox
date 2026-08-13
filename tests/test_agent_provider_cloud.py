# SPDX-License-Identifier: Apache-2.0
"""CloudProvider (Azure OpenAI) and the boot healthcheck — no network.

The Azure client is replaced with a fake whose recorded requests and
scripted responses let us assert the wire contract: native tool calls in
both directions, usage mapping, the parameter-dialect adaptation Azure
deployments force, and — the one that matters most — that the API key
never appears in a log record, an exception, or a repr.

A live counterpart to these assertions is in the PR description's
verification commands; it needs real credentials and is not run in CI.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx
import openai
import pytest

from sbs_api.agents.providers.base import ProviderUnavailableError
from sbs_api.agents.providers.cloud import CloudProvider

FAKE_KEY = "sk-fake-key-do-not-use-0123456789"  # pragma: allowlist secret
ENDPOINT = "https://fake-resource.openai.azure.com/"
DEPLOYMENT = "gpt-test-deployment"
API_VERSION = "2024-06-01"


@pytest.fixture
def azure_env(monkeypatch):
    """A fully-configured, legally-opted-in cloud environment."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", DEPLOYMENT)
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", API_VERSION)
    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "true")
    monkeypatch.setenv("SBS_API_CLOUD_CA_BUNDLE", "")


# --------------------------------------------------------------------------
# Fake Azure client
# --------------------------------------------------------------------------


def _tool_call(name: str, arguments: str, call_id: str = "call-1"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _completion(
    *,
    content: str | None = None,
    tool_calls: list | None = None,
    finish_reason: str = "stop",
    model: str = "gpt-test-deployment-2026-01-01",
    usage: tuple[int, int, int] | None = (10, 5, 15),
):
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content, tool_calls=tool_calls),
            )
        ],
        usage=(
            None
            if usage is None
            else SimpleNamespace(
                prompt_tokens=usage[0],
                completion_tokens=usage[1],
                total_tokens=usage[2],
            )
        ),
    )


def _bad_request(param: str) -> openai.BadRequestError:
    """A 400 shaped like Azure's unsupported-parameter response."""
    body = {
        "error": {
            "message": f"Unsupported parameter: {param!r} is not supported.",
            "type": "invalid_request_error",
            "param": param,
            "code": "unsupported_parameter",
        }
    }
    return openai.BadRequestError(
        message=body["error"]["message"],
        response=httpx.Response(
            400, request=httpx.Request("POST", ENDPOINT), json=body
        ),
        body=body,
    )


class FakeAzureClient:
    """Stands in for openai.AsyncAzureOpenAI. Records every request."""

    def __init__(self, script, **kwargs):
        self.init_kwargs = kwargs
        self.requests: list[dict] = []
        self._script = list(script)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    async def _create(self, **kwargs):
        self.requests.append(kwargs)
        outcome = self._script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def close(self):
        pass


def install_fake(monkeypatch, script):
    """Point CloudProvider at a FakeAzureClient with a scripted outcome list."""
    created: dict = {}

    def factory(**kwargs):
        client = FakeAzureClient(script, **kwargs)
        created["client"] = client
        return client

    monkeypatch.setattr(openai, "AsyncAzureOpenAI", factory)
    return created


# --------------------------------------------------------------------------
# Construction: the gate and the credential check
# --------------------------------------------------------------------------


def test_cloud_provider_requires_the_legal_opt_in(azure_env, monkeypatch):
    """The opt-in is required, and the message says what it asserts."""
    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "false")
    with pytest.raises(ProviderUnavailableError) as exc_info:
        CloudProvider()
    reason = exc_info.value.reason
    assert "SBS_API_CLOUD_LEGAL_APPROVED" in reason
    assert "synthetic data only" in reason


def test_cloud_provider_gate_default_is_closed(azure_env, monkeypatch):
    monkeypatch.delenv("SBS_API_CLOUD_LEGAL_APPROVED", raising=False)
    with pytest.raises(ProviderUnavailableError):
        CloudProvider()


@pytest.mark.parametrize(
    "missing",
    [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
    ],
)
def test_cloud_provider_names_the_missing_variable(azure_env, monkeypatch, missing):
    """Half-configured is a refusal to construct, naming the gap."""
    monkeypatch.setenv(missing, "")
    with pytest.raises(ProviderUnavailableError) as exc_info:
        CloudProvider()
    assert missing in exc_info.value.reason


def test_cloud_provider_reads_the_existing_azure_variables(azure_env, monkeypatch):
    """No renamed or SBS_API_-prefixed credential variables."""
    created = install_fake(monkeypatch, [])
    CloudProvider()
    kwargs = created["client"].init_kwargs
    assert kwargs["api_key"] == FAKE_KEY
    assert kwargs["azure_endpoint"] == ENDPOINT
    assert kwargs["api_version"] == API_VERSION


def test_cloud_provider_passes_a_ca_bundle_to_httpx(azure_env, monkeypatch):
    """The WBG TLS-interception path is configuration, not a code branch."""
    import certifi

    monkeypatch.setenv("SBS_API_CLOUD_CA_BUNDLE", certifi.where())
    created = install_fake(monkeypatch, [])
    CloudProvider()
    assert isinstance(created["client"].init_kwargs["http_client"], httpx.AsyncClient)


def test_cloud_provider_rejects_an_unreadable_ca_bundle(azure_env, monkeypatch, tmp_path):
    """A typo'd path fails at construction, not on the first completion."""
    monkeypatch.setenv("SBS_API_CLOUD_CA_BUNDLE", str(tmp_path / "nope.pem"))
    install_fake(monkeypatch, [])
    with pytest.raises(ProviderUnavailableError) as exc_info:
        CloudProvider()
    assert "SBS_API_CLOUD_CA_BUNDLE" in exc_info.value.reason


def test_cloud_provider_uses_certifi_when_no_bundle_configured(azure_env, monkeypatch):
    created = install_fake(monkeypatch, [])
    CloudProvider()
    assert created["client"].init_kwargs["http_client"] is None


# --------------------------------------------------------------------------
# The wire contract
# --------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "classify_complaint",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


@pytest.mark.asyncio
async def test_cloud_provider_sends_tools_and_parses_tool_calls(
    azure_env, monkeypatch
):
    created = install_fake(
        monkeypatch,
        [
            _completion(
                tool_calls=[
                    _tool_call("classify_complaint", '{"motivo": "COBRANZA"}'),
                    _tool_call("query_dq_results", "{}", call_id="call-2"),
                ],
                finish_reason="tool_calls",
            )
        ],
    )
    provider = CloudProvider()
    response = await provider.complete(
        [{"role": "user", "content": "hola"}],
        tools=TOOLS,
        agent_name="triage",
        complaint_id="BCO-2026-000001",
    )

    sent = created["client"].requests[0]
    assert sent["model"] == DEPLOYMENT  # Azure routes on the deployment name
    assert sent["tools"] == TOOLS
    assert sent["tool_choice"] == "auto"

    assert response.served_by == "cloud"
    assert response.finish_reason == "tool_calls"
    assert [tc.name for tc in response.tool_calls] == [
        "classify_complaint",
        "query_dq_results",
    ]
    assert response.tool_calls[0].arguments == {"motivo": "COBRANZA"}
    assert response.tool_calls[0].id == "call-1"
    assert response.usage.total_tokens == 15
    assert response.model_id == "gpt-test-deployment-2026-01-01"


@pytest.mark.asyncio
async def test_cloud_provider_returns_final_text(azure_env, monkeypatch):
    install_fake(monkeypatch, [_completion(content="triage-complete")])
    provider = CloudProvider()
    response = await provider.complete([], agent_name="triage", complaint_id="x")
    assert response.text == "triage-complete"
    assert response.tool_calls == []
    assert response.served_by == "cloud"


@pytest.mark.asyncio
async def test_cloud_provider_omits_tools_when_agent_has_none(
    azure_env, monkeypatch
):
    created = install_fake(monkeypatch, [_completion(content="ok")])
    provider = CloudProvider()
    await provider.complete([], agent_name="triage", complaint_id="x")
    sent = created["client"].requests[0]
    assert "tools" not in sent
    assert "tool_choice" not in sent


@pytest.mark.asyncio
async def test_cloud_provider_survives_unparseable_tool_arguments(
    azure_env, monkeypatch
):
    """A truncated argument blob is the model's error, not a transport failure."""
    install_fake(
        monkeypatch,
        [
            _completion(
                tool_calls=[_tool_call("classify_complaint", '{"motivo": "COB')],
                finish_reason="tool_calls",
            )
        ],
    )
    provider = CloudProvider()
    response = await provider.complete([], agent_name="triage", complaint_id="x")
    assert response.tool_calls[0].arguments == {}


@pytest.mark.asyncio
async def test_cloud_provider_handles_missing_usage(azure_env, monkeypatch):
    install_fake(monkeypatch, [_completion(content="ok", usage=None)])
    provider = CloudProvider()
    response = await provider.complete([], agent_name="triage", complaint_id="x")
    assert response.usage.total_tokens == 0


@pytest.mark.asyncio
async def test_cloud_provider_reports_empty_choices_as_error(azure_env, monkeypatch):
    empty = SimpleNamespace(model="m", choices=[], usage=None)
    install_fake(monkeypatch, [empty])
    provider = CloudProvider()
    response = await provider.complete([], agent_name="triage", complaint_id="x")
    assert response.finish_reason == "error"


# --------------------------------------------------------------------------
# Parameter dialects
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cloud_provider_sends_max_completion_tokens_first(
    azure_env, monkeypatch
):
    created = install_fake(monkeypatch, [_completion(content="ok")])
    provider = CloudProvider()
    await provider.complete([], agent_name="triage", complaint_id="x", max_tokens=99)
    sent = created["client"].requests[0]
    assert sent["max_completion_tokens"] == 99
    assert "max_tokens" not in sent


@pytest.mark.asyncio
async def test_cloud_provider_falls_back_to_legacy_max_tokens(azure_env, monkeypatch):
    """A gpt-4o-class deployment rejects the modern field; adapt and remember."""
    created = install_fake(
        monkeypatch,
        [_bad_request("max_completion_tokens"), _completion(content="ok")],
    )
    provider = CloudProvider()
    await provider.complete([], agent_name="triage", complaint_id="x", max_tokens=99)

    requests = created["client"].requests
    assert "max_completion_tokens" in requests[0]
    assert requests[1]["max_tokens"] == 99
    # Remembered: the next call does not repeat the rejected dialect.
    assert provider._token_limit_param == "max_tokens"


@pytest.mark.asyncio
async def test_cloud_provider_drops_rejected_temperature(azure_env, monkeypatch):
    created = install_fake(
        monkeypatch, [_bad_request("temperature"), _completion(content="ok")]
    )
    provider = CloudProvider()
    await provider.complete([], agent_name="triage", complaint_id="x")
    requests = created["client"].requests
    assert "temperature" in requests[0]
    assert "temperature" not in requests[1]


@pytest.mark.asyncio
async def test_cloud_provider_reraises_unrelated_bad_request(azure_env, monkeypatch):
    """Only the two known dialect params are retried; the rest surface."""
    install_fake(monkeypatch, [_bad_request("messages")])
    provider = CloudProvider()
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.complete([], agent_name="triage", complaint_id="x")
    assert "400" in exc_info.value.reason


# --------------------------------------------------------------------------
# Failure mapping and secrecy
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cloud_provider_maps_connection_failure(azure_env, monkeypatch):
    install_fake(
        monkeypatch,
        [openai.APIConnectionError(request=httpx.Request("POST", ENDPOINT))],
    )
    provider = CloudProvider()
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.complete([], agent_name="triage", complaint_id="x")
    reason = exc_info.value.reason
    assert "cannot reach Azure OpenAI" in reason
    assert "SBS_API_CLOUD_CA_BUNDLE" in reason  # the WBG-network hint


@pytest.mark.asyncio
async def test_cloud_provider_maps_authentication_failure(azure_env, monkeypatch):
    auth_error = openai.AuthenticationError(
        message="Access denied due to invalid subscription key",
        response=httpx.Response(
            401, request=httpx.Request("POST", ENDPOINT), json={"error": {}}
        ),
        body={"error": {}},
    )
    install_fake(monkeypatch, [auth_error])
    provider = CloudProvider()
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.complete([], agent_name="triage", complaint_id="x")
    assert "rejected the credential" in exc_info.value.reason


@pytest.mark.asyncio
async def test_the_api_key_never_reaches_a_log_or_an_exception(
    azure_env, monkeypatch, caplog
):
    """The one assertion this module exists for.

    An Azure error message can quote the request back; a log line can be
    written by a future edit. Every string CloudProvider emits goes through
    _redact(), so the key cannot leave the process through either path.
    """
    leaky = openai.APIStatusError(
        message=f"request failed with api-key={FAKE_KEY} in header",
        response=httpx.Response(
            500, request=httpx.Request("POST", ENDPOINT), json={"error": {}}
        ),
        body={"error": {}},
    )
    install_fake(monkeypatch, [leaky])

    with caplog.at_level(logging.DEBUG):
        provider = CloudProvider()
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.complete([], agent_name="triage", complaint_id="x")

    assert FAKE_KEY not in str(exc_info.value)
    assert "<redacted>" in exc_info.value.reason
    assert FAKE_KEY not in caplog.text
    assert FAKE_KEY not in repr(provider)
    assert "key=<redacted>" in repr(provider)


@pytest.mark.asyncio
async def test_successful_completion_logs_no_key(azure_env, monkeypatch, caplog):
    install_fake(monkeypatch, [_completion(content="ok")])
    with caplog.at_level(logging.DEBUG):
        provider = CloudProvider()
        await provider.complete([], agent_name="triage", complaint_id="x")
    assert FAKE_KEY not in caplog.text
    assert DEPLOYMENT in caplog.text  # the useful half is still logged


def test_provider_package_imports_without_the_openai_sdk(azure_env, monkeypatch):
    """on_prem and replay must not depend on the cloud SDK being installed.

    `providers/__init__` imports this module to expose the factory. When the
    import of `openai` was unguarded, a host without the SDK failed every
    agent dispatch with ModuleNotFoundError before any provider choice was
    made — observed in the arq worker container, whose venv volume predated
    the dependency.
    """
    import sbs_api.agents.providers.cloud as cloud_module

    monkeypatch.setattr(cloud_module, "openai", None)

    # The other providers still resolve...
    from sbs_api.agents.providers import get_provider, reset_provider_cache

    reset_provider_cache()
    assert get_provider("replay").name == "replay"
    reset_provider_cache()

    # ...and constructing the cloud provider says what is missing.
    with pytest.raises(ProviderUnavailableError) as exc_info:
        cloud_module.CloudProvider()
    assert "'openai' package is not installed" in exc_info.value.reason
