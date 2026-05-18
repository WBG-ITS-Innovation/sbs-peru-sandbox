"""Runtime configuration via Pydantic Settings.

All knobs that vary between dev / test / staging / prod are surfaced as
environment variables here. The application code reads from
:func:`get_settings` and never reaches for ``os.environ`` directly so the
override seam is one cache-controlled function call wide.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Environment-variable naming uses the ``SBS_API_`` prefix to keep the
    namespace clean of unrelated env vars on shared shells. Defaults aim for
    local-dev friction-free; staging and prod overlays set the secure values.
    """

    model_config = SettingsConfigDict(
        env_prefix="SBS_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- runtime ---------------------------------------------------------
    api_version: str = Field(default="0.1.0", description="Reported by GET /v1/version.")
    schema_version: str = Field(default="v0.1.0", description="Active Anexo 1-A schema version.")
    build_sha: str = Field(default="0000000", description="Git commit SHA at build time.")
    environment: Literal["dev", "test", "staging", "prod"] = Field(default="dev")

    # --- database --------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev",  # pragma: allowlist secret
        description=(
            "Async SQLAlchemy URL. The asyncpg driver is required. The "
            "test fixture overrides this with a TEST_DATABASE_URL or a "
            "testcontainer URL. Production reads from the secrets store."
        ),
    )
    db_pool_size: int = Field(default=10, ge=1, le=200)
    db_pool_max_overflow: int = Field(default=20, ge=0, le=400)

    # --- request limits --------------------------------------------------
    max_request_body_bytes: int = Field(
        default=262_144,
        ge=1024,
        description=(
            "Hard cap on request body size. Defends uvicorn's generous "
            "defaults. Default 256 KiB matches the spec note in ADR 0028. "
            "Returns 413 with stable code REQUEST_BODY_TOO_LARGE."
        ),
    )

    # --- authentication (stubbed in Prompt 6; real wiring in Prompt 7) ---
    auth_stub_enabled: bool = Field(
        default=False,
        description=(
            "When True the tenancy-binding dependency returns a fixed demo "
            "institution (BANCO_DEMO_001). When False the dependency fails "
            "closed with 503 AUTH_NOT_CONFIGURED. Defaults vary per overlay: "
            "scripts/run-api.sh exports True (local dev convenience); "
            "docker-compose.yaml sets False (staging-shaped); production "
            "inherits the False default."
        ),
    )
    auth_stub_institution_id: str = Field(
        default="SBS-001234",
        description="Institution id returned by the stub auth dependency.",
    )

    # --- idempotency -----------------------------------------------------
    idempotency_ttl_seconds: int = Field(
        default=86_400,
        ge=60,
        description="Idempotency-Key record retention window (default 24 hours).",
    )

    # --- health probe ----------------------------------------------------
    readiness_db_ping_timeout_ms: int = Field(default=200, ge=10, le=5000)
    readiness_cache_seconds: float = Field(default=1.0, ge=0.0, le=60.0)

    # --- problem details -------------------------------------------------
    problem_type_namespace: str = Field(
        default="https://sbs.gob.pe/errors",
        description=(
            "Base URI for RFC 9457 `type` URIs. The full namespace is a "
            "placeholder pending SBS sign-off; see error-catalog.md."
        ),
    )

    # --- observability ---------------------------------------------------
    log_format: Literal["console", "json"] = Field(
        default="console",
        description="`console` is human-readable (dev); `json` is one structured line per record (prod).",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    otel_service_name: str = Field(default="sbs-suptech-api")
    otel_traces_exporter: Literal["otlp", "console", "none"] = Field(default="console")
    otel_exporter_otlp_endpoint: str | None = Field(default=None)

    # --- canonical-spec serving -----------------------------------------
    canonical_openapi_path: str = Field(
        default="api/openapi/sbs-api-v1.yaml",
        description=(
            "Path (relative to repo root) of the canonical OpenAPI YAML that "
            "GET /v1/openapi.yaml serves. ADR 0027 keeps this YAML — not the "
            "FastAPI-generated openapi — as the contract."
        ),
    )

    # --- mTLS (ADR 0031) -------------------------------------------------
    mtls_mode: Literal["direct", "proxy", "disabled"] = Field(
        default="disabled",
        description=(
            "How mTLS is presented to the runtime. `direct` reads the peer "
            "cert from the ASGI scope (uvicorn-terminated TLS). `proxy` "
            "reads the verified cert metadata from the trusted "
            "X-Forwarded-Client-Cert header (Envoy de-facto standard). "
            "`disabled` accepts requests without an mTLS subject — only "
            "valid when AUTH_STUB_ENABLED=true or for tests that override "
            "the dependency."
        ),
    )
    disable_mtls_for_tests: bool = Field(
        default=False,
        description=(
            "Test-only escape hatch: when True the mTLS dependency returns "
            "an empty subject and downstream auth runs against the stub. "
            "Production overlays never set this."
        ),
    )
    proxy_trusted_xfcc_header: str = Field(
        default="x-forwarded-client-cert",
        description=(
            "Header name the proxy uses to forward the verified cert. "
            "Lowercase per Starlette's header-folding. Defaults to the "
            "Envoy convention."
        ),
    )

    # --- HMAC request signing (ADR 0027 amendment) -----------------------
    hmac_secret_rotation_grace_seconds: int = Field(
        default=3600,
        ge=0,
        description=(
            "How long after an institution rotates its HMAC secret the "
            "`previous_secret` is still accepted. 1 hour by default; "
            "operators may extend per institution during a phased rollout."
        ),
    )
    hmac_timestamp_skew_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description=(
            "Clock-skew tolerance for X-SBS-Timestamp. 5 minutes by default "
            "per the ADR 0027 amendment; future-dated signatures are "
            "additionally rejected if more than 60 seconds ahead."
        ),
    )
    hmac_replay_cache_ttl_seconds: int = Field(
        default=600,
        ge=60,
        description=(
            "Redis replay-cache TTL. timestamp_skew × 2 + headroom; the "
            "primary defence is the timestamp check, the replay cache is "
            "the bounded backstop. The 24h figure in the original ADR was "
            "a pressure-test finding."
        ),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description=(
            "Redis DSN for HMAC replay cache and (workstream E) per-"
            "institution rate limit buckets. Compose stack brings Redis "
            "up alongside Postgres; production overlay points at a "
            "managed Redis."
        ),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance.

    Cached so the constructor's env-parsing runs once per process. Tests that
    need a fresh instance call ``get_settings.cache_clear()``.
    """

    return Settings()
