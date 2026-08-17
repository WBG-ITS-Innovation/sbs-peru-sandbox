# SPDX-License-Identifier: Apache-2.0
"""Meta endpoints — version and the three health probes.

ADR 0030 locks the semantics:

* ``/health/live``    — process alive. No I/O. Always 200.
* ``/health/ready``   — DB ping with 200ms timeout, 1-second cache.
* ``/health/startup`` — alembic migrations applied.
* ``/health``         — aggregate (legacy + institution-facing summary).
* ``/version``        — build metadata.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.config import get_settings
from sbs_api.dependencies.db import get_session
from sbs_api.errors.exceptions import ServiceUnavailable
from sbs_api.models.responses import HealthStatus, VersionInfo

router = APIRouter(tags=["Meta"])


# --- /health/ready DB-ping cache ----------------------------------------------

_ready_cache: tuple[float, bool] | None = None


def _reset_ready_cache_for_test() -> None:
    global _ready_cache
    _ready_cache = None


async def _ping_db(session: AsyncSession, timeout_ms: int) -> bool:
    try:
        await asyncio.wait_for(
            session.execute(text("SELECT 1")), timeout=timeout_ms / 1000.0
        )
        return True
    except (TimeoutError, asyncio.TimeoutError, Exception):
        return False


async def _check_alembic_head(session: AsyncSession) -> bool:
    try:
        await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        return True
    except Exception:
        return False


# --- handlers -----------------------------------------------------------------


@router.get("/health/live", response_model=HealthStatus, include_in_schema=False)
async def health_live() -> HealthStatus:
    settings = get_settings()
    return HealthStatus(
        status="ok",
        version=settings.api_version,
        checked_at=datetime.now(timezone.utc),
    )


@router.get("/health/ready", response_model=HealthStatus, include_in_schema=False)
async def health_ready(session: AsyncSession = Depends(get_session)) -> HealthStatus:
    global _ready_cache
    settings = get_settings()
    now = time.monotonic()
    if _ready_cache is not None:
        cached_at, cached_ok = _ready_cache
        if now - cached_at < settings.readiness_cache_seconds:
            if cached_ok:
                return HealthStatus(
                    status="ok",
                    version=settings.api_version,
                    checked_at=datetime.now(timezone.utc),
                )
            raise ServiceUnavailable(
                detail="Database ping failed within the cache window."
            )

    ok = await _ping_db(session, settings.readiness_db_ping_timeout_ms)
    _ready_cache = (now, ok)
    if not ok:
        raise ServiceUnavailable(detail="Database ping failed.")
    return HealthStatus(
        status="ok",
        version=settings.api_version,
        checked_at=datetime.now(timezone.utc),
    )


@router.get("/health/startup", response_model=HealthStatus, include_in_schema=False)
async def health_startup(session: AsyncSession = Depends(get_session)) -> HealthStatus:
    settings = get_settings()
    ok = await _check_alembic_head(session)
    if not ok:
        raise ServiceUnavailable(detail="Alembic migrations not applied.")
    return HealthStatus(
        status="ok",
        version=settings.api_version,
        checked_at=datetime.now(timezone.utc),
    )


@router.get("/health", response_model=HealthStatus, include_in_schema=False)
async def health_aggregate() -> HealthStatus:
    settings = get_settings()
    return HealthStatus(
        status="ok",
        version=settings.api_version,
        checked_at=datetime.now(timezone.utc),
    )


@router.get("/version", response_model=VersionInfo, include_in_schema=False)
async def version() -> VersionInfo:
    settings = get_settings()
    return VersionInfo(
        api_version=settings.api_version,
        build_sha=settings.build_sha,
        schema_version=settings.schema_version,
    )
