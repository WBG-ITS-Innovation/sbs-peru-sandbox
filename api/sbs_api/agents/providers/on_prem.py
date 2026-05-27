"""OnPremProvider — talks to a self-hosted vLLM endpoint.

The endpoint is OpenAI-compatible (``/v1/chat/completions``). When
the endpoint URL is unset or unreachable, the provider falls back to
:class:`MockProvider` so the demo never deadlocks on infrastructure
the operator hasn't booted yet. Every fallback emits a warning log.

This provider exists today as a forward contract: the demo path is
fixture-driven (replay), but the on-prem path must be reachable for
the regulator-grade story. The fallback policy is the deliberate
divergence — see ADR 0001.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

import httpx

from sbs_api.agents.providers.base import ModelResponse, ToolCallRequest
from sbs_api.agents.providers.mock import MockProvider

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
        self._base_url = (base_url or os.getenv("SBS_API_VLLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._model = model or os.getenv("SBS_API_VLLM_MODEL") or DEFAULT_MODEL
        self._timeout = float(timeout_seconds or os.getenv("SBS_API_VLLM_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
        self._fallback = MockProvider()
        self._fallback_warned = False

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
            return await self._fallback_with_warning(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                agent_name=agent_name,
                complaint_id=complaint_id,
                reason="SBS_API_VLLM_BASE_URL unset",
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
            return await self._fallback_with_warning(
                messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                agent_name=agent_name,
                complaint_id=complaint_id,
                reason=f"vLLM unreachable: {exc!r}",
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        choices = body.get("choices") or []
        if not choices:
            return ModelResponse(
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
            text=msg.get("content"),
            tool_calls=tool_calls,
            model_id=body.get("model") or self._model,
            latency_ms=latency_ms,
            finish_reason=finish,
        )

    async def _fallback_with_warning(
        self, messages, *, reason: str, **kwargs
    ) -> ModelResponse:
        if not self._fallback_warned:
            log.warning(
                "on_prem provider falling back to mock: %s "
                "(base_url=%s, model=%s) — demo-safe but not regulator-grade",
                reason,
                self._base_url,
                self._model,
            )
            self._fallback_warned = True
        return await self._fallback.complete(messages, **kwargs)
