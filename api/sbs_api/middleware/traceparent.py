"""Observe and echo the OpenTelemetry-managed W3C traceparent.

ADR 0028 §4 — OpenTelemetry owns the trace context. This middleware does not
parse, generate, or repair traceparent independently. It logs a WARN on a
malformed inbound header, defers to OTel (which falls through to a
freshly-generated context), and writes the resulting traceparent into the
response so clients always see the trace they should support-handoff with.
"""

from __future__ import annotations

import re

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from sbs_api.observability.logging import get_logger

_TRACEPARENT_RE = re.compile(
    r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
)

_logger = get_logger(__name__)


def current_traceparent() -> str | None:
    """Return the W3C traceparent for the active span, or None if no valid span."""

    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return None
    return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{ctx.trace_flags:02x}"


class TraceparentMiddleware(BaseHTTPMiddleware):
    """Observation + echo only. Does not own trace context."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        inbound = request.headers.get("traceparent")
        if inbound is not None and not _TRACEPARENT_RE.match(inbound):
            _logger.warning(
                "malformed_traceparent_dropped",
                inbound_traceparent=inbound,
                path=request.url.path,
            )
            # We do not need to modify the request — OTel's FastAPI
            # instrumentation will fall back to generating fresh context when
            # the inbound header is invalid.

        response: Response = await call_next(request)

        echo = current_traceparent()
        if echo is not None:
            response.headers["traceparent"] = echo
        return response
