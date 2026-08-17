# SPDX-License-Identifier: Apache-2.0
"""Observe and echo the OpenTelemetry-managed W3C traceparent.

ADR 0028 §4 — OpenTelemetry owns the trace context. This middleware does not
parse, generate, or repair traceparent independently. It logs a WARN on a
malformed inbound header, defers to OTel (which falls through to a
freshly-generated context), and writes the resulting traceparent into the
response so clients always see the trace they should support-handoff with.

Implemented as a pure ASGI middleware (not BaseHTTPMiddleware) so it
composes cleanly with ``StreamingResponse`` endpoints — see
:mod:`sbs_api.middleware.correlation_id` for the rationale.
"""

from __future__ import annotations

import re

from opentelemetry import trace
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sbs_api.observability.logging import get_logger

_TRACEPARENT_RE = re.compile(
    r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
)
_TRACEPARENT_HEADER = b"traceparent"

_logger = get_logger(__name__)


def current_traceparent() -> str | None:
    """Return the W3C traceparent for the active span, or None if no valid span."""

    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return None
    return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{ctx.trace_flags:02x}"


class TraceparentMiddleware:
    """Observation + echo only. Does not own trace context."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound: str | None = None
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == _TRACEPARENT_HEADER:
                inbound = raw_value.decode("latin-1")
                break
        if inbound is not None and not _TRACEPARENT_RE.match(inbound):
            _logger.warning(
                "malformed_traceparent_dropped",
                inbound_traceparent=inbound,
                path=scope.get("path"),
            )
            # We do not modify scope["headers"] — OTel's FastAPI
            # instrumentation will fall back to generating fresh context
            # when the inbound header is invalid.

        async def send_with_traceparent(message: Message) -> None:
            if message["type"] == "http.response.start":
                echo = current_traceparent()
                if echo is not None:
                    existing = message.get("headers") or []
                    new_headers = [
                        (k, v)
                        for (k, v) in existing
                        if k.lower() != _TRACEPARENT_HEADER
                    ]
                    new_headers.append((_TRACEPARENT_HEADER, echo.encode("ascii")))
                    message["headers"] = new_headers
            await send(message)

        await self.app(scope, receive, send_with_traceparent)
