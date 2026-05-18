"""FastAPI application factory.

Why a factory: per-test fresh apps with overridden dependencies. The factory
reads :class:`Settings` from the cached singleton (or a caller-supplied
instance), registers middleware (outermost to innermost: body_size_limit →
traceparent → correlation_id), mounts the v1 router, registers exception
handlers, and configures OTel instrumentation. FastAPI's auto-generated
openapi/docs/redoc are disabled per ADR 0028 §6.
"""

from __future__ import annotations

from fastapi import FastAPI

from sbs_api.config import Settings, get_settings
from sbs_api.errors.handlers import install_exception_handlers
from sbs_api.middleware import (
    BodySizeLimitMiddleware,
    CorrelationIdMiddleware,
    TraceparentMiddleware,
)
from sbs_api.observability import configure_logging, configure_tracing
from sbs_api.observability.logging import get_logger


def create_app(settings: Settings | None = None) -> FastAPI:
    """Return a configured ASGI app.

    ``settings`` is typically ``None`` so the app uses the cached singleton.
    Tests pass an override or ``cache_clear()`` first and then call this.
    """

    settings = settings or get_settings()

    configure_logging()
    configure_tracing()

    app = FastAPI(
        title="SBS SupTech Complaints API",
        version=settings.api_version,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    # Last-added is outermost at request time. To produce the order
    # body_size_limit → traceparent → correlation_id (outermost to
    # innermost), add in reverse.
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(TraceparentMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)

    install_exception_handlers(app)

    # Late-import to avoid a circular dependency between the routes package
    # (which imports the observability logger) and this module (which
    # configures the observability logger).
    from sbs_api.routes import v1_router

    app.include_router(v1_router)

    _instrument_otel(app)

    get_logger(__name__).info(
        "app_started",
        api_version=settings.api_version,
        environment=settings.environment,
        auth_stub_enabled=settings.auth_stub_enabled,
    )

    return app


def _instrument_otel(app: FastAPI) -> None:
    """Wire OTel auto-instrumentation for FastAPI and SQLAlchemy.

    Best-effort: failures (e.g., when an OTel test fixture has already
    instrumented a SQLAlchemy engine) are swallowed so the app still starts.
    """

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:  # noqa: BLE001
        pass
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
    except Exception:  # noqa: BLE001
        pass
