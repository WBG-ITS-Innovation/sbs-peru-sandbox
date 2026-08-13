# SPDX-License-Identifier: Apache-2.0
"""OnPremProvider — talks to a self-hosted vLLM endpoint.

The endpoint is OpenAI-compatible (``/v1/chat/completions``). When the
endpoint URL is unset or unreachable the provider raises
:class:`~sbs_api.agents.providers.base.ProviderUnavailableError`.

It used to answer from :class:`MockProvider` instead, so that the demo
never deadlocked on infrastructure the operator hadn't booted. That
traded a visible outage for an invisible one: an unconfigured host wrote
agent_runs full of canned tool calls, and only ``model_provider`` in the
database distinguished them from real inference. A supervisory tool must
not fabricate an analysis, so the fallback is gone. Deterministic output
for demos comes from ``SBS_API_MODEL_PROVIDER=replay``, which says so in
every log line it emits.

This provider is the target state for the SBS workstation and stays the
default for ``SBS_API_MODEL_PROVIDER``. See ADR 0001.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

import httpx

from sbs_api.agents.providers.base import (
    ModelResponse,
    ProviderUnavailableError,
    ToolCallRequest,
)

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:8001/v1"
DEFAULT_MODEL = "Qwen2.5-7B-Instruct"
DEFAULT_TIMEOUT_SECONDS = 30.0


class OnPremProvider:
    """OpenAI-compatible HTTP client against a vLLM server."""

    name = "on_prem"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ):
        # An explicitly-empty value — `OnPremProvider(base_url="")` or
        # `SBS_API_VLLM_BASE_URL=` in the environment — means "there is no
        # endpoint here", and complete() says so by name. Only a genuinely
        # absent variable falls through to the localhost default; pointing an
        # operator who blanked the variable at localhost:8001 would report a
        # connection error against an address they never chose.
        raw_base_url = (
            base_url
            if base_url is not None
            else os.getenv("SBS_API_VLLM_BASE_URL", DEFAULT_BASE_URL)
        )
        self._base_url = raw_base_url.strip().rstrip("/")
        self._model = model or os.getenv("SBS_API_VLLM_MODEL") or DEFAULT_MODEL
        self._timeout = float(timeout_seconds or os.getenv("SBS_API_VLLM_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)

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
        if not self._base_url:
            raise ProviderUnavailableError(
                self.name,
                "SBS_API_VLLM_BASE_URL is unset. Point it at the vLLM "
                f"endpoint (default {DEFAULT_BASE_URL}), or select a "
                "different SBS_API_MODEL_PROVIDER.",
            )

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ProviderUnavailableError(
                self.name,
                f"vLLM unreachable at {self._base_url} "
                f"(model={self._model}, timeout={self._timeout}s): {exc!r}",
            ) from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        choices = body.get("choices") or []
        if not choices:
            return ModelResponse(
                served_by=self.name,
                text="",
                model_id=self._model,
                latency_ms=latency_ms,
                finish_reason="error",
            )
        msg = choices[0].get("message") or {}
        finish = choices[0].get("finish_reason") or "stop"

        tool_calls: list[ToolCallRequest] = []
        for raw in msg.get("tool_calls") or []:
            fn = raw.get("function") or {}
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                ToolCallRequest(
                    id=raw.get("id") or f"call-{uuid.uuid4().hex[:8]}",
                    name=fn.get("name") or "",
                    arguments=arguments,
                )
            )

        return ModelResponse(
            served_by=self.name,
            text=msg.get("content"),
            tool_calls=tool_calls,
            model_id=body.get("model") or self._model,
            latency_ms=latency_ms,
            finish_reason=finish,
        )
