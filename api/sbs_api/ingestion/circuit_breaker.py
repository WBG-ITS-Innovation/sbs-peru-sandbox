"""Per-institution ingestion circuit breaker (P-RESHAPE-9).

Read on every ingestion request. When an institution's breaker is
PAUSED (set by SBS IT remediation), ingestion is rejected with a 503
``fi_circuit_breaker_paused`` problem+json. Absence of a row = NORMAL.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.fi_circuit_breaker import FiCircuitBreaker
from sbs_api.errors.exceptions import CircuitBreakerPaused


async def is_paused(session: AsyncSession, institution_code: str) -> bool:
    row = (
        await session.execute(
            select(FiCircuitBreaker.state).where(
                FiCircuitBreaker.institution_code == institution_code
            )
        )
    ).scalar_one_or_none()
    return row == "PAUSED"


async def assert_ingestion_allowed(
    session: AsyncSession, institution_code: str
) -> None:
    """Raise :class:`CircuitBreakerPaused` (503) when ingestion is paused
    for ``institution_code``."""
    if await is_paused(session, institution_code):
        raise CircuitBreakerPaused(
            detail=(
                f"Ingestion for institution {institution_code} is paused by an "
                "SBS circuit breaker (fi_circuit_breaker_paused). Retry after "
                "SBS resumes ingestion."
            )
        )
