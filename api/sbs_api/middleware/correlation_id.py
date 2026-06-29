# SPDX-License-Identifier: Apache-2.0
"""Generate (or echo) ``X-Correlation-Id`` and bind it to structlog.

The correlation_id is logged alongside the OTel ``trace_id`` and ``span_id``.
Operations teams hunting for a request by an upstream support-ticket id rely
on this; the OTel trace_id alone is not enough when the trace context was
dropped before reaching the API.

Implemented as a pure ASGI middleware (not BaseHTTPMiddleware) so it
composes cleanly with ``StreamingResponse`` endpoints. Stacking multiple
``BaseHTTPMiddleware`` layers around an SSE handler trips the well-known
``listen_for_disconnect`` deadlock — fixed in P10 by porting all three
custom middlewares to the pure ASGI shape (see ADR 0028 amendment).
"""

from __future__ import annotations

import uuid
from typing import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sbs_api.observability.logging import set_correlation_id

HEADER_NAME = "X-Correlation-Id"
_HEADER_NAME_BYTES = HEADER_NAME.encode("latin-1")
_HEADER_NAME_LOWER = HEADER_NAME.lower().encode("ascii")


def _read_header(headers: Iterable[tuple[bytes, bytes]], name_lower: bytes) -> str | None:
    for raw_name, raw_value in headers:
        if raw_name.lower() == name_lower:
            return raw_value.decode("latin-1")
    return None


class CorrelationIdMiddleware:
    """Read or generate the correlation id and echo it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # ASGI middlewares are invoked for `lifespan` and `websocket` scopes
        # too; only HTTP requests carry a correlation id.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _read_header(scope.get("headers", []), _HEADER_NAME_LOWER)
        correlation_id = incoming if incoming else str(uuid.uuid4())
        set_correlation_id(correlation_id)

        # Mirror onto scope["state"] so any downstream handler reading
        # ``request.state.correlation_id`` observes the same value
        # (Starlette's Request wraps scope["state"]).
        state = scope.setdefault("state", {})
        state["correlation_id"] = correlation_id

        header_bytes = correlation_id.encode("latin-1")

        async def send_with_correlation_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Strip any pre-existing X-Correlation-Id to avoid
                # duplicates if a downstream layer (or a 413 emitter)
                # also tried to set it.
                existing = message.get("headers") or []
                new_headers = [
                    (k, v) for (k, v) in existing if k.lower() != _HEADER_NAME_LOWER
                ]
                new_headers.append((_HEADER_NAME_BYTES, header_bytes))
                message["headers"] = new_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation_header)
        finally:
            # Reset defensively for synchronous code that may peek
            # between requests; the ContextVar is also bound per-task
            # so this is belt-and-braces, not load-bearing.
            set_correlation_id(None)
