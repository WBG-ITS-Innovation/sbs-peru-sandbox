"""Per-request async SQLAlchemy session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.session import open_session


async def get_session() -> AsyncIterator[AsyncSession]:
    async for session in open_session():
        yield session
