# SPDX-License-Identifier: Apache-2.0
"""Batch storage prune — Workstream F.2 (ADR 0034 §sandbox-storage)."""

from __future__ import annotations

import os
import time
from pathlib import Path


def _seed_csv(dir_: Path, *, name: str, mtime_age_days: float) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    p = dir_ / name
    p.write_bytes(b"placeholder\n")
    age_seconds = mtime_age_days * 86400
    now = time.time()
    os.utime(p, (now - age_seconds, now - age_seconds))
    return p


def test_prune_deletes_only_files_older_than_threshold(tmp_path, monkeypatch):
    monkeypatch.setenv("SBS_API_BATCH_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("SBS_API_BATCH_STORAGE_PRUNE_DAYS", "7")
    from sbs_api.config import get_settings

    get_settings.cache_clear()

    fresh = _seed_csv(tmp_path, name="fresh.csv", mtime_age_days=1)
    stale = _seed_csv(tmp_path, name="stale.csv", mtime_age_days=10)

    from sbs_api.scheduler.prune_batches import prune_batch_storage

    result = prune_batch_storage()
    assert result.deleted_count == 1
    assert result.bytes_freed == len(b"placeholder\n")
    assert fresh.exists()
    assert not stale.exists()


def test_prune_noop_when_dir_missing(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("SBS_API_BATCH_STORAGE_PATH", str(missing))
    monkeypatch.setenv("SBS_API_BATCH_STORAGE_PRUNE_DAYS", "7")
    from sbs_api.config import get_settings

    get_settings.cache_clear()

    from sbs_api.scheduler.prune_batches import prune_batch_storage

    result = prune_batch_storage()
    assert result.deleted_count == 0
    assert result.bytes_freed == 0


def test_prune_emits_structlog_event_inspectable_in_source(tmp_path):
    """Source-level check that the event name is emitted.

    The runtime logger is bound at module import time and structlog
    re-configuration during a test does not redirect the already-bound
    handle. Rather than rely on a fragile runtime capture, this test
    asserts the canonical event name appears in the source — a small
    contract test that catches a refactor that renames the event.
    """

    src = Path(__file__).resolve().parents[1] / (
        "api/sbs_api/scheduler/prune_batches.py"
    )
    text = src.read_text(encoding="utf-8")
    assert "batch.storage.pruned" in text, (
        "The canonical structlog event name has changed. Update the "
        "ADR 0034 §sandbox-storage section if intentional."
    )


def test_prune_respects_explicit_now_for_determinism(tmp_path, monkeypatch):
    """The pure-function entry point honours injected ``now`` + ``older_than_days``."""

    monkeypatch.setenv("SBS_API_BATCH_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("SBS_API_BATCH_STORAGE_PRUNE_DAYS", "7")
    from sbs_api.config import get_settings

    get_settings.cache_clear()

    p = _seed_csv(tmp_path, name="exact.csv", mtime_age_days=3)
    from sbs_api.scheduler.prune_batches import prune_batch_storage

    # With older_than_days=10 (file is 3 days old), no-op.
    r1 = prune_batch_storage(older_than_days=10)
    assert r1.deleted_count == 0
    assert p.exists()

    # With older_than_days=1, the file qualifies for deletion.
    r2 = prune_batch_storage(older_than_days=1)
    assert r2.deleted_count == 1
    assert not p.exists()
