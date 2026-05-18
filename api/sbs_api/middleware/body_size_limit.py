"""Reject oversize request bodies before route dispatch.

Uvicorn's default body size is generous; this middleware caps it at
``MAX_REQUEST_BODY_BYTES`` (default 256 KiB) and returns 413 with the
stable code ``REQUEST_BODY_TOO_LARGE``. The exception flows through the
SBSAPIException handler so the response is RFC 9457 problem+json.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from sbs_api.config import get_settings
from sbs_api.errors.exceptions import RequestBodyTooLarge

PROBLEM_CONTENT_TYPE = "application/problem+json"


def _too_large_response(detail: str) -> JSONResponse:
    """Build the 413 ProblemDetail directly.

    ``BaseHTTPMiddleware`` does not route exceptions through FastAPI's
    registered handlers — the dispatch coroutine runs outside the handler
    chain. So the middleware materialises the ProblemDetail itself, using
    the same shape the handler would.
    """

    settings = get_settings()
    exc = RequestBodyTooLarge(detail=detail)
    body = {
        "type": f"{settings.problem_type_namespace}/{exc.type_suffix}",
        "title": exc.title,
        "status": exc.status,
        "code": exc.code,
        "detail": exc.detail,
    }
    return JSONResponse(
        status_code=exc.status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
    )


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforce ``settings.max_request_body_bytes``."""

    def __init__(self, app: ASGIApp, *, max_bytes: int | None = None) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes if max_bytes is not None else get_settings().max_request_body_bytes

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Fast path: trust Content-Length when present and small enough.
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = None
            if declared is not None and declared > self._max_bytes:
                return _too_large_response(
                    f"Request body declared {declared} bytes; "
                    f"server maximum is {self._max_bytes} bytes."
                )

        # Slow path: read the body so we can guard against a missing or lying
        # Content-Length. Caching the body on the request lets the downstream
        # handler still parse JSON without an extra round trip.
        body = await request.body()
        if len(body) > self._max_bytes:
            return _too_large_response(
                f"Request body was {len(body)} bytes; "
                f"server maximum is {self._max_bytes} bytes."
            )

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]

        response: Response = await call_next(request)
        return response
