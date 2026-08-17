# SPDX-License-Identifier: Apache-2.0
"""Batch storage prune job — Workstream F.2 (ADR 0034 §sandbox-storage).

Deletes CSV files in ``settings.batch_storage_path`` whose mtime is
older than ``settings.batch_storage_prune_days``. Runs in the same
APScheduler instance as the idempotency sweep so we don't add a new
operational surface.

Production overlay uses object-store lifecycle policies instead; this
prune is the sandbox equivalent. Emits a structlog event
``batch.storage.pruned`` with the count and total bytes freed so the
operator can confirm the job ran.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from sbs_api.config import get_settings
from sbs_api.observability.logging import get_logger

_logger = get_logger(__name__)


@dataclass(frozen=True)
class PruneResult:
    deleted_count: int
    bytes_freed: int
    storage_dir: str


def _resolve_storage_dir() -> Path:
    settings = get_settings()
    path = Path(settings.batch_storage_path)
    if not path.is_absolute():
        # api/sbs_api/scheduler/prune_batches.py → repo root is parents[3]
        path = Path(__file__).resolve().parents[3] / settings.batch_storage_path
    return path


def prune_batch_storage(
    *,
    older_than_days: int | None = None,
    now: float | None = None,
) -> PruneResult:
    """Delete CSV files older than the configured retention window.

    Pure function for testability — pass ``now`` (Unix epoch seconds)
    to control the deadline; pass ``older_than_days`` to override the
    setting. The structlog event fires at the end regardless of count.
    """

    settings = get_settings()
    cutoff_days = (
        older_than_days
        if older_than_days is not None
        else settings.batch_storage_prune_days
    )
    deadline = (now if now is not None else time.time()) - cutoff_days * 86400

    storage = _resolve_storage_dir()
    if not storage.exists():
        result = PruneResult(0, 0, str(storage))
        _logger.info(
            "batch.storage.pruned",
            deleted_count=0,
            bytes_freed=0,
            storage_dir=str(storage),
            older_than_days=cutoff_days,
        )
        return result

    deleted = 0
    bytes_freed = 0
    for csv_file in storage.glob("*.csv"):
        try:
            stat = csv_file.stat()
        except OSError:
            continue
        if stat.st_mtime < deadline:
            try:
                bytes_freed += stat.st_size
                csv_file.unlink()
                deleted += 1
            except OSError:
                # File was removed between stat and unlink — fine.
                pass

    result = PruneResult(deleted, bytes_freed, str(storage))
    _logger.info(
        "batch.storage.pruned",
        deleted_count=deleted,
        bytes_freed=bytes_freed,
        storage_dir=str(storage),
        older_than_days=cutoff_days,
    )
    return result


async def prune_batch_storage_job() -> None:
    """APScheduler wrapper — passes no arguments, swallows exceptions.

    Operational policy: a single failed prune should not crash the
    scheduler. The structlog event will be missing on failure, which
    is the alerting signal.
    """

    try:
        prune_batch_storage()
    except Exception:  # noqa: BLE001
        _logger.error("batch.storage.prune_failed", exc_info=True)
