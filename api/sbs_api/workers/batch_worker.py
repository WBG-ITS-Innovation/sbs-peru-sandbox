"""arq batch processing worker (ADR 0034).

``process_batch`` drains pending Tier 2 batches: reads the CSV from
disk, validates each row through the *same* Pydantic Anexo 1-A model
as the Tier 1 endpoint (the proportional-treatment claim is a code-
identity invariant, asserted by ``tests/test_batch_validation_uses_tier_1_models.py``),
INSERTs accepted rows into ``complaints`` with ``source='batch'``, and
records per-row failures in ``batch_row_rejections``.

State machine: ``pending`` → ``processing`` → ``complete`` | ``failed``.
Once terminal, the row does not change.

Retry policy: arq's max_tries handles transient infrastructure failures
(Postgres connection drop, etc.) with exponential backoff. The 5th
attempt failure transitions the batch to ``failed`` with a structlog
``batch.processing.dead_letter`` event.

Workstream D extends this module with ``deliver_webhook``.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arq.connections import RedisSettings
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from sbs_api.config import get_settings
from sbs_api.db.models.batch import BatchRecord
from sbs_api.db.models.batch_row_rejection import BatchRowRejection
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.session import get_sessionmaker
from sbs_api.models.anexo_1a import Complaint
from sbs_api.observability.logging import get_logger
from sbs_api.workers.arq_pool import _redis_settings_from_url

_logger = get_logger(__name__)

# ADR 0034 §retry-policy: arq retries on raised exceptions with
# exponential backoff. 5 attempts total over ~7 minutes; on dead-letter
# the worker sets batch.status='failed' so the institution can poll.
_MAX_TRIES = 5

# Excerpt cap for the raw CSV row stored on rejection.
_EXCERPT_MAX_CHARS = 500


def _resolve_csv_path(stored_file_path: str) -> Path:
    """Map ``batch.file_path`` (stored as a basename) onto the local FS.

    The route handler stores the basename (e.g. ``batch_xxx.csv``) so the
    API host and the worker container can mount the same data directory
    at different absolute paths. The full path is constructed from
    :class:`Settings.batch_storage_path`.

    Backwards-compatible: if the stored value already contains a
    directory component (legacy rows written before this commit), it is
    used as-is.
    """

    p = Path(stored_file_path)
    if p.is_absolute() or p.parent != Path("."):
        return p
    settings = get_settings()
    storage = Path(settings.batch_storage_path)
    if not storage.is_absolute():
        # Resolve relative to the repo root (api/sbs_api/workers/batch_worker.py
        # → repo root is parents[3]).
        storage = Path(__file__).resolve().parents[3] / settings.batch_storage_path
    return storage / stored_file_path


# ---------------------------------------------------------------------------
# Validation helper (shared with Tier 1)
# ---------------------------------------------------------------------------


# Code-identity test in tests/test_batch_validation_uses_tier_1_models.py
# imports this attribute and asserts it is the *exact same class object* as
# the Tier 1 endpoint's submission model uses. The assertion is identity
# (`is`), not equivalence, so a future refactor that introduces a parallel
# validation path is detected at test time, not at production-data time.
TIER_1_COMPLAINT_MODEL = Complaint


def _normalise_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    """CSV-empty-cell-as-null + drop unknown fields up front.

    csv.DictReader yields empty strings for missing values; Pydantic with
    ``Optional[str]`` + a non-empty pattern rejects ``""`` even on
    nullable fields. The cleanest fix is to honour the CSV convention
    that empty cells mean *missing*, so the worker re-keys empty
    strings to ``None`` before validation.
    """

    return {k: (None if v == "" else v) for k, v in row.items()}


def _validate_row(
    row: dict[str, Any],
) -> tuple[Complaint | None, list[dict[str, str]]]:
    """Return (Complaint, []) on success or (None, errors) on failure.

    ``errors`` is a list of {field, rule, message} dicts shaped like
    :class:`ProblemFieldError` so the rejection rows in the DB and the
    Tier 1 RFC 9457 envelope render the same field-error shape.
    """

    try:
        complaint = TIER_1_COMPLAINT_MODEL.model_validate(
            _normalise_csv_row(row)
        )
        return complaint, []
    except ValidationError as exc:
        errors: list[dict[str, str]] = []
        for err in exc.errors():
            field = ".".join(str(p) for p in err["loc"])
            errors.append(
                {
                    "field": field,
                    "rule": err["type"],
                    "message": err["msg"],
                }
            )
        return None, errors


def _row_to_excerpt(raw_row: dict[str, Any]) -> str:
    """Truncate the row's repr so the debugging breadcrumb is bounded."""

    txt = json.dumps(raw_row, ensure_ascii=False)
    if len(txt) > _EXCERPT_MAX_CHARS:
        return txt[: _EXCERPT_MAX_CHARS - 1] + "…"
    return txt


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


async def process_batch(ctx: dict[str, Any], batch_id: str) -> dict[str, Any]:
    """Drive a single batch from ``pending`` to a terminal state.

    Returns a small summary dict useful for tests (and for arq's own
    job result store, though we don't rely on it).
    """

    job_try = ctx.get("job_try", 1) if ctx else 1
    sessionmaker = get_sessionmaker()

    # Phase 1 — load + transition to processing.
    async with sessionmaker() as session:
        async with session.begin():
            stmt = select(BatchRecord).where(BatchRecord.batch_id == batch_id)
            result = await session.execute(stmt)
            batch: BatchRecord | None = result.scalar_one_or_none()
            if batch is None:
                _logger.error(
                    "batch.processing.not_found", batch_id=batch_id
                )
                return {"batch_id": batch_id, "status": "not_found"}

            if batch.status not in {"pending", "processing"}:
                # Re-driven after terminal — no-op.
                _logger.info(
                    "batch.processing.skipped_terminal",
                    batch_id=batch_id,
                    status=batch.status,
                )
                return {
                    "batch_id": batch_id,
                    "status": batch.status,
                    "row_count_accepted": batch.row_count_accepted,
                    "row_count_rejected": batch.row_count_rejected,
                }

            batch.status = "processing"
            file_path = batch.file_path
            institution_id = batch.institution_id

    if file_path is None:
        await _mark_failed(batch_id, reason="batch.file_path is null")
        return {"batch_id": batch_id, "status": "failed"}

    csv_path = _resolve_csv_path(file_path)
    if not csv_path.exists():
        await _mark_failed(
            batch_id, reason=f"CSV file not found at {csv_path}"
        )
        return {"batch_id": batch_id, "status": "failed"}

    # Phase 2 — process rows.
    try:
        accepted = 0
        rejected = 0
        raw_bytes = csv_path.read_bytes()
        reader = csv.DictReader(
            io.StringIO(raw_bytes.decode("utf-8"))
        )

        async with sessionmaker() as session:
            async with session.begin():
                for row_index, row in enumerate(reader):
                    complaint, errors = _validate_row(row)
                    if complaint is not None:
                        record = ComplaintRecord(
                            complaint_id=complaint.complaint_id,
                            institution_id=complaint.institution_id,
                            received_date=complaint.received_date,
                            complainant_doc_type=complaint.complainant_doc_type,
                            product_category=complaint.product_category,
                            channel=complaint.channel,
                            motivo_code=complaint.motivo_code,
                            severity=complaint.severity,
                            description_text=complaint.description_text,
                            description_language=complaint.description_language,
                            complainant_age_range=complaint.complainant_age_range,
                            complainant_district=complaint.complainant_district,
                            submission_method=complaint.submission_method,
                            original_reference_id=complaint.original_reference_id,
                            resolution_status=complaint.resolution_status,
                            source="batch",
                        )
                        session.add(record)
                        try:
                            await session.flush()
                            accepted += 1
                        except Exception as flush_exc:  # noqa: BLE001
                            # Likely a duplicate complaint_id (UNIQUE
                            # constraint) — treated as a row rejection
                            # so the cross-batch dedup gap named in the
                            # spec §2 NOT-in-scope item is gracefully
                            # handled. Roll back this row and continue.
                            await session.rollback()
                            await session.begin()
                            session.add(
                                BatchRowRejection(
                                    batch_id=batch_id,
                                    row_index=row_index,
                                    field="complaint_id",
                                    rule="duplicate",
                                    message=(
                                        "complaint_id already exists; "
                                        f"{type(flush_exc).__name__}: "
                                        f"{flush_exc}"
                                    ),
                                    raw_row_excerpt=_row_to_excerpt(row),
                                )
                            )
                            rejected += 1
                    else:
                        for err in errors:
                            session.add(
                                BatchRowRejection(
                                    batch_id=batch_id,
                                    row_index=row_index,
                                    field=err["field"],
                                    rule=err["rule"],
                                    message=err["message"],
                                    raw_row_excerpt=_row_to_excerpt(row),
                                )
                            )
                        rejected += 1

                # Update batch counts + terminal state.
                stmt = select(BatchRecord).where(
                    BatchRecord.batch_id == batch_id
                )
                result = await session.execute(stmt)
                final_batch = result.scalar_one()
                final_batch.row_count_accepted = accepted
                final_batch.row_count_rejected = rejected
                final_batch.status = "complete"
                final_batch.completed_at = datetime.now(timezone.utc)

        _logger.info(
            "batch.processing.completed",
            batch_id=batch_id,
            institution_id=institution_id,
            row_count_accepted=accepted,
            row_count_rejected=rejected,
            job_try=job_try,
        )

        # Workstream D enqueues the outbound webhook here.
        try:
            from sbs_api.workers.arq_pool import enqueue_job

            await enqueue_job(
                "deliver_webhook_for_batch",
                batch_id,
                "batch.complete" if rejected == 0 else "batch.complete_with_errors",
            )
        except Exception:  # noqa: BLE001
            # Webhook delivery is the convenience layer; missing it is
            # not a batch-processing failure. The status endpoint is
            # the correctness layer.
            _logger.warning(
                "batch.webhook.enqueue_failed",
                batch_id=batch_id,
                exc_info=True,
            )

        return {
            "batch_id": batch_id,
            "status": "complete",
            "row_count_accepted": accepted,
            "row_count_rejected": rejected,
        }

    except OperationalError as exc:
        # Transient DB-side failure — re-raise so arq retries with
        # exponential backoff. The decision to dead-letter is made on
        # the final attempt below.
        _logger.warning(
            "batch.processing.transient_error",
            batch_id=batch_id,
            job_try=job_try,
            error=str(exc),
        )
        if job_try >= _MAX_TRIES:
            await _mark_failed(
                batch_id, reason=f"max retries exhausted: {exc}"
            )
            _logger.error(
                "batch.processing.dead_letter",
                batch_id=batch_id,
                job_try=job_try,
                error=str(exc),
            )
            return {"batch_id": batch_id, "status": "failed"}
        raise
    except Exception as exc:  # noqa: BLE001
        # Non-transient — fail immediately. arq will not retry an
        # unhandled exception by default unless we re-raise; we don't.
        await _mark_failed(batch_id, reason=f"{type(exc).__name__}: {exc}")
        _logger.error(
            "batch.processing.failed",
            batch_id=batch_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return {"batch_id": batch_id, "status": "failed"}


async def _mark_failed(batch_id: str, *, reason: str) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        async with session.begin():
            stmt = select(BatchRecord).where(
                BatchRecord.batch_id == batch_id
            )
            result = await session.execute(stmt)
            batch = result.scalar_one_or_none()
            if batch is None:
                return
            batch.status = "failed"
            batch.failure_reason = reason[:2000]
            batch.completed_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# arq WorkerSettings
# ---------------------------------------------------------------------------


class WorkerSettings:
    """arq picks up this class with ``arq sbs_api.workers.batch_worker.WorkerSettings``.

    Functions registered: ``process_batch``. Workstream D adds
    ``deliver_webhook_for_batch``.
    """

    functions = [process_batch]
    max_tries = _MAX_TRIES
    # arq default retry-with-exponential-backoff: 1s, 2s, 4s, 8s, 16s
    # (powers of 2) — sufficient for sandbox transient errors.

    @staticmethod
    def redis_settings() -> RedisSettings:
        settings = get_settings()
        return _redis_settings_from_url(settings.redis_url)
