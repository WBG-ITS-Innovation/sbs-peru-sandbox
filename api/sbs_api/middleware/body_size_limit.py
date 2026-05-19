"""Reject oversize request bodies before route dispatch.

Uvicorn's default body size is generous; this middleware caps it at
``MAX_REQUEST_BODY_BYTES`` (default 256 KiB) and returns 413 with the
stable code ``REQUEST_BODY_TOO_LARGE``. The middleware materialises the
RFC 9457 ProblemDetail JSONResponse directly because BaseHTTPMiddleware
sits outside FastAPI's exception-handler dispatch chain (ADR 0028
§Consequences).

Two changes from the Prompt 6 implementation:

* **F.2** — The 413 response carries ``X-Correlation-Id`` (pulled from
  ``request.state.correlation_id`` set by the surrounding
  ``CorrelationIdMiddleware``) and ``traceparent`` (echoed by the
  surrounding ``TraceparentMiddleware`` on the response path). The
  app's middleware install order was reversed so this header propagation
  works.
* **F.3** — The slow path replaces the unbounded ``await request.body()``
  with a bounded streaming read: iterate ``request.stream()``,
  accumulate into a bytearray, and abort with ``RequestBodyTooLarge``
  as soon as the running total exceeds ``max_body_size``. A client
  that lies about ``Content-Length`` can no longer force a full-body
  allocation.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from sbs_api.config import get_settings
from sbs_api.errors.exceptions import RequestBodyTooLarge

PROBLEM_CONTENT_TYPE = "application/problem+json"


def _too_large_response(detail: str, *, correlation_id: str | None) -> JSONResponse:
    """Build the 413 ProblemDetail directly.

    Pulls the correlation_id from the outer middleware's request-state
    binding so the response carries the support-handoff identifier.
    """

    settings = get_settings()
    exc = RequestBodyTooLarge(detail=detail)
    body: dict = {
        "type": f"{settings.problem_type_namespace}/{exc.type_suffix}",
        "title": exc.title,
        "status": exc.status,
        "code": exc.code,
        "detail": exc.detail,
    }
    headers: dict[str, str] = {}
    if correlation_id is not None:
        headers["X-Correlation-Id"] = correlation_id
    return JSONResponse(
        status_code=exc.status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforce ``settings.max_request_body_bytes``.

    Runs inside CorrelationIdMiddleware (F.2 order) so the 413 response
    can pull ``request.state.correlation_id``.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int | None = None) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes if max_bytes is not None else get_settings().max_request_body_bytes

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = getattr(request.state, "correlation_id", None)

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
                    f"server maximum is {self._max_bytes} bytes.",
                    correlation_id=correlation_id,
                )

        # F.3 — bounded streaming read. Accumulate the body chunk-by-
        # chunk and abort as soon as the running total exceeds the
        # max. A client lying about Content-Length cannot force a
        # full-body allocation.
        accumulated = bytearray()
        async for chunk in request.stream():
            accumulated.extend(chunk)
            if len(accumulated) > self._max_bytes:
                return _too_large_response(
                    f"Request body exceeded {self._max_bytes} bytes "
                    f"after streaming (declared "
                    f"{content_length or 'unknown'} bytes).",
                    correlation_id=correlation_id,
                )
        body = bytes(accumulated)

        # Replay the body for downstream handlers. ``request.body()``
        # caches in ``request._body`` on first call; we pre-populate
        # both ``_body`` and a replay ``_receive`` so any access shape
        # (``body()``, ``stream()``, ``form()``) works.
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._body = body  # type: ignore[attr-defined]
        request._receive = receive  # type: ignore[attr-defined]

        response: Response = await call_next(request)
        return response
