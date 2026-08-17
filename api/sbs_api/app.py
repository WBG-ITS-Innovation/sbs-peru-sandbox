# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory.

Why a factory: per-test fresh apps with overridden dependencies. The factory
reads :class:`Settings` from the cached singleton (or a caller-supplied
instance), registers middleware (outermost to innermost: body_size_limit →
traceparent → correlation_id), mounts the v1 router, registers exception
handlers, and configures OTel instrumentation. FastAPI's auto-generated
openapi/docs/redoc are disabled per ADR 0028 §6.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from sbs_api.config import Settings, get_settings
from sbs_api.db.session import get_sessionmaker
from sbs_api.errors.handlers import install_exception_handlers
from sbs_api.middleware import (
    BodySizeLimitMiddleware,
    CorrelationIdMiddleware,
    TraceparentMiddleware,
)
from sbs_api.middleware.mtls_transport import MtlsTransportCaptureMiddleware
from sbs_api.observability import configure_logging, configure_tracing
from sbs_api.observability.logging import get_logger
from sbs_api.scheduler import (
    prune_batch_storage_job,
    sweep_expired_idempotency_records,
)


async def _healthcheck_provider_or_die(settings: Settings) -> None:
    """Prove the agent pipeline has a working provider, or refuse to boot.

    One canary tool-call request. Runs only when the pipeline is enabled —
    an API that never invokes an agent does not need a model — and never
    inside pytest, where a live inference call at boot would make the
    suite depend on network reachability.

    Before this existed, ``on_prem`` answered from ``MockProvider`` when no
    vLLM was reachable, so a misconfigured host booted clean and produced
    fabricated agent_runs for hours. Failing here is the point.
    """

    if not settings.agents_pipeline_enabled or not settings.provider_healthcheck_on_boot:
        return

    from sbs_api.agents.providers.healthcheck import (
        check_ingestion_path_compatibility,
        check_provider,
    )
    from sbs_api.agents.providers.mock import in_test_process

    if in_test_process():
        return

    result = await check_provider()
    logger = get_logger(__name__)

    # A provider can pass the canary and still be unusable here: this
    # process reaches agents only through the ingestion path, and
    # DIValeVale gates that path to its own allowlist.
    if result.ok:
        incompatible = check_ingestion_path_compatibility(result.provider)
        if incompatible is not None:
            logger.error(
                "provider.healthcheck.incompatible_with_ingestion",
                provider=result.provider,
                detail=incompatible,
            )
            raise RuntimeError(
                "Agent pipeline is enabled but its model provider cannot "
                f"serve the ingestion path, so the API will not start.\n  "
                f"{incompatible}"
            )

    if not result.ok:
        logger.error(
            "provider.healthcheck.failed",
            provider=result.provider,
            detail=result.detail,
        )
        raise RuntimeError(
            "Agent pipeline is enabled but its model provider is not usable, "
            f"so the API will not start.\n  {result.render()}\n"
            "Fix the provider configuration, set "
            "SBS_API_AGENTS_PIPELINE_ENABLED=false, or select a different "
            "SBS_API_MODEL_PROVIDER (on_prem | cloud | replay). Run "
            "`uv run python scripts/provider_healthcheck.py` to retest."
        )
    logger.info(
        "provider.healthcheck.ok",
        provider=result.provider,
        skipped=result.skipped,
        detail=result.detail,
        model_id=result.model_id,
        latency_ms=result.latency_ms,
    )


def _build_lifespan(settings: Settings):
    """Construct the lifespan context manager that starts/stops APScheduler
    and healthchecks the model provider.

    The scheduler runs only when ``settings.idempotency_sweep_enabled`` is
    True so tests can leave it off without monkey-patching APScheduler.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001
        await _healthcheck_provider_or_die(settings)
        scheduler: AsyncIOScheduler | None = None
        if settings.idempotency_sweep_enabled:
            scheduler = AsyncIOScheduler()

            async def _run() -> None:
                await sweep_expired_idempotency_records(get_sessionmaker())

            scheduler.add_job(
                _run,
                trigger="interval",
                seconds=settings.idempotency_sweep_interval_seconds,
                id="idempotency_sweep",
                replace_existing=True,
                next_run_time=None,  # do not run at startup; first run at +interval
            )
            # ADR 0034 §sandbox-storage: prune Tier 2 CSV files older
            # than batch_storage_prune_days. Shares the same
            # AsyncIOScheduler as the idempotency sweep.
            scheduler.add_job(
                prune_batch_storage_job,
                trigger="interval",
                hours=6,
                id="batch_storage_prune",
                replace_existing=True,
                next_run_time=None,
            )
            scheduler.start()
            get_logger(__name__).info(
                "scheduler.started",
                jobs=["idempotency_sweep", "batch_storage_prune"],
                interval_seconds=settings.idempotency_sweep_interval_seconds,
            )
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)
                get_logger(__name__).info("scheduler.stopped")

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Return a configured ASGI app.

    ``settings`` is typically ``None`` so the app uses the cached singleton.
    Tests pass an override or ``cache_clear()`` first and then call this.
    """

    settings = settings or get_settings()

    # ADR 0035 §webhook-url-validation gate. The
    # `allow_insecure_webhook_urls` knob is sandbox-only; refuse to boot
    # if it is set with a non-dev/test environment. Catching this at
    # startup is cheaper than catching it at first webhook delivery.
    if settings.allow_insecure_webhook_urls and settings.environment in {
        "staging",
        "prod",
    }:
        raise RuntimeError(
            "SBS_API_ALLOW_INSECURE_WEBHOOK_URLS=true is rejected when "
            f"SBS_API_ENVIRONMENT={settings.environment!r}. Webhook URL "
            "validation must not be bypassed outside dev/test."
        )

    configure_logging()
    configure_tracing()

    app = FastAPI(
        title="SBS SupTech Complaints API",
        version=settings.api_version,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        lifespan=_build_lifespan(settings),
    )

    # Last-added is outermost at request time. ADR 0028 amendment (F.2):
    # the middleware order is reversed so traceparent and correlation_id
    # bind BEFORE body_size_limit runs. This lets 413 responses carry
    # both `traceparent` and `X-Correlation-Id` headers, which closes
    # the Prompt 6 carry-forward observability gap.
    # Outermost → innermost at request time:
    #   cors → traceparent → correlation_id → body_size_limit
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(TraceparentMiddleware)
    app.add_middleware(MtlsTransportCaptureMiddleware)
    _install_cors(app, settings)

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


def _install_cors(app: FastAPI, settings: Settings) -> None:
    """Wire CORS for the two-laptop sandbox demo.

    ``cors_allow_origins`` is comma-separated. Literal entries (e.g.
    ``http://localhost:3000``) go to ``allow_origins``; wildcard / LAN
    patterns (``http://*.local:3000``, ``http://192.168.0.0/16:3000``)
    are translated to a single ``allow_origin_regex`` so the
    supervisor laptop can reach the API laptop on the demo LAN
    without us pre-enumerating IPs. Tighten the env var (or set it
    to a single literal) before production. See
    docs/demo/2026-05-27-two-laptop-setup.md.
    """

    raw = (settings.cors_allow_origins or "").strip()
    if not raw:
        return

    literal: list[str] = []
    regex_parts: list[str] = []
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        if entry.startswith("http://*.local:") or entry.startswith(
            "https://*.local:"
        ):
            scheme, _, tail = entry.partition("://")
            _, _, port = tail.partition(":")
            port_re = port or r"\d+"
            regex_parts.append(
                rf"{scheme}://[a-zA-Z0-9-]+\.local:{port_re}"
            )
        elif "192.168.0.0/16" in entry:
            scheme, _, tail = entry.partition("://")
            _, _, port = tail.partition(":")
            port_re = port or r"\d+"
            regex_parts.append(
                rf"{scheme}://192\.168\.\d{{1,3}}\.\d{{1,3}}:{port_re}"
            )
        elif "10.0.0.0/8" in entry:
            scheme, _, tail = entry.partition("://")
            _, _, port = tail.partition(":")
            port_re = port or r"\d+"
            regex_parts.append(rf"{scheme}://10\.\d{{1,3}}\.\d{{1,3}}\.\d{{1,3}}:{port_re}")
        else:
            literal.append(entry)

    allow_origin_regex = "|".join(regex_parts) if regex_parts else None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=literal or [],
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "ETag",
            "Idempotency-Replayed",
            "Location",
            "Retry-After",
            "traceparent",
            "X-Correlation-Id",
        ],
    )


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
