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

from sbs_api.config import Settings, get_settings
from sbs_api.errors.exceptions import BatchFileTooLarge, RequestBodyTooLarge, SBSAPIException

PROBLEM_CONTENT_TYPE = "application/problem+json"

# ADR 0034: the Tier 2 multipart upload may carry up to
# `settings.max_batch_file_bytes` of CSV, which is two orders of magnitude
# larger than the general default. The middleware applies a per-path cap
# on these endpoints and uses BATCH_FILE_TOO_LARGE as the error code so
# the integrator's error handler can distinguish "your batch is too big"
# from "your JSON payload was wrong".
_BATCH_UPLOAD_PATH = "/v1/batches"


def _too_large_response(
    exc: SBSAPIException, *, correlation_id: str | None
) -> JSONResponse:
    """Build the 413 ProblemDetail directly.

    Pulls the correlation_id from the outer middleware's request-state
    binding so the response carries the support-handoff identifier.
    """

    settings = get_settings()
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


def _limit_for(path: str, method: str, settings: Settings) -> tuple[int, type[SBSAPIException]]:
    """Return (max_bytes, exception_class) for the request shape.

    The Tier 2 multipart upload (`POST /v1/batches`) takes the batch cap;
    the equivalent GET endpoints stay on the general cap (they have no
    body to speak of). Future per-path overrides land here.
    """

    if method == "POST" and path == _BATCH_UPLOAD_PATH:
        return settings.max_batch_file_bytes, BatchFileTooLarge
    return settings.max_request_body_bytes, RequestBodyTooLarge


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforce per-path body-size caps.

    Runs inside CorrelationIdMiddleware (F.2 order) so the 413 response
    can pull ``request.state.correlation_id``. The cap and the
    error-code that surfaces on overflow are both per-path so the Tier 2
    upload at `/v1/batches` can carry tens of megabytes while everything
    else stays on the 256-KiB default.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int | None = None) -> None:
        super().__init__(app)
        self._override_max = max_bytes

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = getattr(request.state, "correlation_id", None)

        settings = get_settings()
        max_bytes, exc_cls = _limit_for(
            request.url.path, request.method, settings
        )
        if self._override_max is not None:
            # Test override: same cap on every route. Stays on the
            # general RequestBodyTooLarge code because the override is
            # only used by tests that don't care about the per-path
            # error-code distinction.
            max_bytes = self._override_max
            exc_cls = RequestBodyTooLarge

        # Fast path: trust Content-Length when present and small enough.
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = None
            if declared is not None and declared > max_bytes:
                return _too_large_response(
                    exc_cls(
                        detail=(
                            f"Request body declared {declared} bytes; "
                            f"server maximum is {max_bytes} bytes."
                        )
                    ),
                    correlation_id=correlation_id,
                )

        # Bounded streaming read. Accumulate the body chunk-by-chunk and
        # abort as soon as the running total exceeds the cap so a client
        # lying about Content-Length cannot force a full-body allocation.
        accumulated = bytearray()
        async for chunk in request.stream():
            accumulated.extend(chunk)
            if len(accumulated) > max_bytes:
                return _too_large_response(
                    exc_cls(
                        detail=(
                            f"Request body exceeded {max_bytes} bytes "
                            f"after streaming (declared "
                            f"{content_length or 'unknown'} bytes)."
                        )
                    ),
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
