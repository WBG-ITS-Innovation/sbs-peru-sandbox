"""Generate (or echo) ``X-Correlation-Id`` and bind it to structlog.

The correlation_id is logged alongside the OTel ``trace_id`` and ``span_id``.
Operations teams hunting for a request by an upstream support-ticket id rely
on this; the OTel trace_id alone is not enough when the trace context was
dropped before reaching the API.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from sbs_api.observability.logging import set_correlation_id

HEADER_NAME = "X-Correlation-Id"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Read or generate the correlation id and echo it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        incoming = request.headers.get(HEADER_NAME)
        correlation_id = incoming if incoming else str(uuid.uuid4())
        set_correlation_id(correlation_id)
        # Stash on request.state so route handlers can access it without
        # threading another argument.
        request.state.correlation_id = correlation_id
        try:
            response: Response = await call_next(request)
        finally:
            # The ContextVar already returns to its prior value when the
            # async task completes; we set it back to None defensively for
            # synchronous code that may peek between requests.
            set_correlation_id(None)
        response.headers[HEADER_NAME] = correlation_id
        return response
