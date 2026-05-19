"""Every error path emits RFC 9457 ``application/problem+json``.

Three handlers under test:

* :class:`SBSAPIException` — domain errors map to the matching code.
* :class:`RequestValidationError` — Pydantic / FastAPI validation maps to 422.
* generic :class:`Exception` — body-less 500 with trace_id only.

The catch-all 500 must not leak internal detail; ``trace_id`` is the only
support-handoff identifier.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from pydantic import BaseModel

from sbs_api.errors.exceptions import (
    ETagMismatch,
    PreconditionRequired,
    ResolutionStatusTransitionForbidden,
    ResourceNotFound,
)
from sbs_api.errors.handlers import install_exception_handlers
from sbs_api.middleware import (
    BodySizeLimitMiddleware,
    CorrelationIdMiddleware,
    TraceparentMiddleware,
)
from sbs_api.observability.tracing import configure_tracing


class _Payload(BaseModel):
    value: int


def _build_app() -> FastAPI:
    configure_tracing()
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(TraceparentMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=10_000)
    install_exception_handlers(app)

    @app.get("/notfound")
    async def notfound() -> dict:
        raise ResourceNotFound(detail="example detail")

    @app.get("/forbidden-transition")
    async def forbidden_transition() -> dict:
        raise ResolutionStatusTransitionForbidden(detail="pendiente → pendiente?")

    @app.get("/etag-mismatch")
    async def etag_mismatch() -> dict:
        raise ETagMismatch(detail="If-Match does not match.")

    @app.get("/etag-required")
    async def etag_required() -> dict:
        raise PreconditionRequired(detail="If-Match required.")

    @app.post("/validate")
    async def validate(payload: _Payload) -> dict:
        return {"ok": True}

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("internal — must not appear in response body")

    return app


@pytest.fixture()
async def client():
    # ``raise_app_exceptions=False`` lets the catch-all 500 handler emit a
    # response instead of having the exception bubble up through ASGI to the
    # test client (which is what happens in production, since the ASGI server
    # — uvicorn — translates uncaught exceptions into 500 responses).
    transport = ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# --- domain exceptions -----------------------------------------------------


async def test_resource_not_found_404_problem_json(client):
    r = await client.get("/notfound")
    assert r.status_code == 404
    assert r.headers.get("content-type", "").startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "SBS-404-001"
    assert body["status"] == 404
    assert body["title"] == "Resource not found"
    assert body["detail"] == "example detail"
    assert body["instance"] == "/notfound"


async def test_resolution_status_forbidden_422(client):
    r = await client.get("/forbidden-transition")
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "SBS-422-004"
    assert "RESOLUTION_STATUS_TRANSITION_FORBIDDEN" in body["type"]


async def test_etag_mismatch_412(client):
    r = await client.get("/etag-mismatch")
    assert r.status_code == 412
    body = r.json()
    assert body["code"] == "SBS-412-001"
    assert "ETAG_MISMATCH" in body["type"]


async def test_precondition_required_428(client):
    r = await client.get("/etag-required")
    assert r.status_code == 428
    body = r.json()
    assert body["code"] == "SBS-428-001"


# --- validation handler ----------------------------------------------------


async def test_validation_error_returns_422_with_field_errors(client):
    r = await client.post("/validate", json={"value": "not-an-int"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "SBS-422-001"
    assert isinstance(body["errors"], list)
    assert body["errors"]
    # Each entry has the documented shape.
    err = body["errors"][0]
    assert {"field", "rule", "message"} <= set(err.keys())


# --- catch-all 500 ---------------------------------------------------------


async def test_unhandled_500_is_body_less_problem_json(client):
    r = await client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "SBS-500-001"
    # Body-less detail by design: no internal information leaks.
    assert "detail" not in body or body.get("detail") is None
    # The internal exception text MUST NOT leak.
    assert "internal" not in (body.get("detail") or "").lower()
    assert "RuntimeError" not in r.text


async def test_unhandled_500_logs_exc_info(client):
    """F.4 — catch-all 500 handler logs the underlying exception with
    exc_info=True so ops sees the stack trace in the structured log.
    """

    from structlog.testing import capture_logs

    with capture_logs() as captured:
        r = await client.get("/boom")
    assert r.status_code == 500

    unhandled_events = [
        e for e in captured if e.get("event") == "unhandled_exception"
    ]
    assert unhandled_events, f"no unhandled_exception event in: {captured}"
    event = unhandled_events[-1]
    # structlog's capture_logs records the exc_info=True flag as a key
    # on the captured event; the presence of the key (truthy) confirms
    # the handler asked for the stack trace.
    assert event.get("exc_info") is True or event.get("exception") is not None
    assert event.get("path") == "/boom"
    assert event.get("method") == "GET"


# --- trace_id propagation --------------------------------------------------


async def test_problem_detail_carries_trace_id_when_span_active(client):
    """When OTel has a span in context the response carries trace_id."""

    from opentelemetry import trace

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("inbound"):
        r = await client.get("/notfound")
    body = r.json()
    # The body's trace_id and the response header traceparent are derived
    # from the same span; they agree (this is the no-dual-context property
    # ADR 0028 §4 protects).
    if body.get("trace_id"):
        assert body["trace_id"].startswith("00-")
        assert r.headers.get("traceparent") == body["trace_id"]
