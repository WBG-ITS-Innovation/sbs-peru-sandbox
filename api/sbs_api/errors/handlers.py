"""FastAPI exception handlers that emit RFC 9457 ``application/problem+json``.

ADR 0028 §2 locks the choice of handlers over middleware: handlers compose
cleanly with FastAPI's ``RequestValidationError`` and the catch-all
``Exception`` paths, and they avoid the dual-trace-context bug where a
ProblemDetail wrapped in middleware would record a trace_id different from
the one the OTel exporter sees.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace

from sbs_api.config import get_settings
from sbs_api.errors.exceptions import SBSAPIException
from sbs_api.observability.logging import get_logger

_logger = get_logger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"


def _current_traceparent() -> str | None:
    """Return the W3C traceparent string for the active OTel span, or None."""

    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return None
    trace_flags = f"{ctx.trace_flags:02x}"
    return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{trace_flags}"


def _type_uri(suffix: str) -> str:
    return f"{get_settings().problem_type_namespace}/{suffix}"


def _problem_payload(
    *,
    code: str,
    status: int,
    title: str,
    type_suffix: str,
    detail: str | None,
    instance: str | None,
    errors: list[dict[str, Any]] | None,
    trace_id: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": _type_uri(type_suffix),
        "title": title,
        "status": status,
        "code": code,
    }
    if detail is not None:
        body["detail"] = detail
    if instance is not None:
        body["instance"] = instance
    if errors:
        body["errors"] = errors
    if trace_id is not None:
        body["trace_id"] = trace_id
    return body


def _problem_response(
    status: int, payload: dict[str, Any], *, traceparent: str | None
) -> JSONResponse:
    headers: dict[str, str] = {}
    if traceparent is not None:
        headers["traceparent"] = traceparent
    return JSONResponse(
        status_code=status,
        content=jsonable_encoder(payload),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


async def sbs_api_exception_handler(
    request: Request, exc: SBSAPIException
) -> JSONResponse:
    traceparent = _current_traceparent()
    payload = _problem_payload(
        code=exc.code,
        status=exc.status,
        title=exc.title,
        type_suffix=exc.type_suffix,
        detail=exc.detail,
        instance=exc.instance or str(request.url.path),
        errors=exc.errors,
        trace_id=traceparent,
    )
    headers: dict[str, str] = {}
    if traceparent is not None:
        headers["traceparent"] = traceparent
    # Merge exception's extra_headers (e.g. Retry-After / X-RateLimit-*
    # on 429). Exception-provided values win over the handler's defaults.
    headers.update(exc.extra_headers)
    return JSONResponse(
        status_code=exc.status,
        content=jsonable_encoder(payload),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = err.get("loc", ())
        field = ".".join(str(p) for p in loc if p != "body")
        errors.append(
            {
                "field": field or "body",
                "rule": err.get("type", "validation"),
                "message": err.get("msg", "validation failed"),
            }
        )
    traceparent = _current_traceparent()
    payload = _problem_payload(
        code="SBS-422-001",
        status=422,
        title="Field validation failed",
        type_suffix="SBS-422-001",
        detail="One or more request fields failed schema validation.",
        instance=str(request.url.path),
        errors=errors,
        trace_id=traceparent,
    )
    return _problem_response(422, payload, traceparent=traceparent)


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    # Body-less detail by design: no internal information leaks. The trace_id
    # is the support handoff identifier.
    traceparent = _current_traceparent()
    # F.4 — log the underlying exception with exc_info=True so the stack
    # trace lands in the structured log. Without this the catch-all
    # handler renders a clean 500 but the cause is invisible to ops.
    correlation_id = getattr(request.state, "correlation_id", None)
    _logger.error(
        "unhandled_exception",
        exc_info=True,
        path=str(request.url.path),
        method=request.method,
        correlation_id=correlation_id,
        traceparent=traceparent,
    )
    payload = _problem_payload(
        code="SBS-500-001",
        status=500,
        title="Internal server error",
        type_suffix="SBS-500-001",
        detail=None,
        instance=str(request.url.path),
        errors=None,
        trace_id=traceparent,
    )
    return _problem_response(500, payload, traceparent=traceparent)


def install_exception_handlers(app: FastAPI) -> None:
    """Register the three exception handlers on ``app``.

    Order does not matter functionally — FastAPI dispatches by class identity —
    but the install sequence mirrors the dispatch sequence (domain → validation
    → catch-all) for documentation clarity.
    """

    app.add_exception_handler(SBSAPIException, sbs_api_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
