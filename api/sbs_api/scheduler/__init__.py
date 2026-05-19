"""In-process background jobs — APScheduler AsyncIOScheduler.

Jobs are registered by the app factory and started/stopped in the
FastAPI lifespan. Only one scheduler instance lives in the app; jobs
are coroutines registered against it.
"""

from sbs_api.scheduler.sweep import (
    sweep_expired_idempotency_records,
    SweepResult,
)

__all__ = [
    "SweepResult",
    "sweep_expired_idempotency_records",
]
