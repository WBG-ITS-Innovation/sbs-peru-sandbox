# SPDX-License-Identifier: Apache-2.0
"""In-process background jobs — APScheduler AsyncIOScheduler.

Jobs are registered by the app factory and started/stopped in the
FastAPI lifespan. Only one scheduler instance lives in the app; jobs
are coroutines registered against it.
"""

from sbs_api.scheduler.prune_batches import (
    PruneResult,
    prune_batch_storage,
    prune_batch_storage_job,
)
from sbs_api.scheduler.sweep import (
    sweep_expired_idempotency_records,
    SweepResult,
)

__all__ = [
    "PruneResult",
    "SweepResult",
    "prune_batch_storage",
    "prune_batch_storage_job",
    "sweep_expired_idempotency_records",
]
