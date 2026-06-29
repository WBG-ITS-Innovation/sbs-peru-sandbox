# SPDX-License-Identifier: Apache-2.0
"""Async SQLAlchemy session management.

The engine is constructed lazily so a process that never opens a database
session (CLI helpers, test collection) does not need a live DSN. The session
factory is reused across requests; sessions themselves are scoped to a
single request via the :func:`get_session` dependency in
:mod:`sbs_api.dependencies.db`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sbs_api.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


async def open_session() -> AsyncIterator[AsyncSession]:
    """Yield an :class:`AsyncSession` scoped to one request.

    Wrap each request in an explicit ``async with session.begin():`` block on
    the call site so commit/rollback are explicit. Auto-commit on context
    exit is intentionally not used so the route handler can decide whether to
    persist or roll back on partial failure.
    """

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


async def reset_engine_for_test() -> None:
    """Test hook: dispose the cached engine so a new ``database_url`` takes effect."""

    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def override_engine_for_test(engine: AsyncEngine, sessionmaker: Any | None = None) -> None:
    """Test hook: inject a pre-built engine (used by the testcontainer fixture)."""

    global _engine, _sessionmaker
    _engine = engine
    _sessionmaker = sessionmaker or async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession
    )
