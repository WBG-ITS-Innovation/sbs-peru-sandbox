# SPDX-License-Identifier: Apache-2.0
"""P10 ↔ P12 integration gate.

Validates the ``agent_run`` JSON Schema (the contract documented at
``docs/schemas/agent_run.md``) is itself well-formed, validates a
canonical positive example per status plus a few targeted negatives,
AND — gated on a live Postgres testcontainer being available —
validates every seeded row inserted by ``scripts/seed_demo_narrative.py``
against that schema. The live-stack test is the integration gate:
when Prompt 12 replaces seeded rows with live agent output, the same
test runs against live rows. As long as it stays green, the supervisor
UI does not break at the P10→P12 cutover.
"""

from __future__ import annotations

import json
import pathlib
import uuid

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from tests.conftest import pytestmark_db

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "docs" / "schemas" / "agent_run.schema.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# Repo-wide complaint-id pattern: ^[A-Z0-9]{1,4}-\d{4}-\d{6,10}$
# Used as a stable test fixture so the schema's pattern constraint is exercised.
TEST_COMPLAINT_ID = "BCP-2026-001234"


def _bert_success_call() -> dict:
    return {
        "tool_name": "bert_classifier",
        "tool_version": "bert_classifier-1.4.0",
        "started_at": "2026-05-22T13:00:00+00:00",
        "ended_at": "2026-05-22T13:00:01+00:00",
        "input": {
            "text": "Reclamo por comisión por mantenimiento no informada.",
            "locale": "es-PE",
            "max_tokens": 512,
        },
        "output": {
            "label": "undisclosed-fees-credit",
            "confidence": 0.87,
            "top_k": [
                {"label": "undisclosed-fees-credit", "confidence": 0.87},
                {"label": "misselling", "confidence": 0.08},
                {"label": "billing-dispute", "confidence": 0.03},
            ],
            "model_version": "beto-onnx-2026.04",
        },
        "status": "success",
        "error": None,
    }


def _xgboost_success_call() -> dict:
    return {
        "tool_name": "xgboost_ranker",
        "tool_version": "xgboost_ranker-0.9.2",
        "started_at": "2026-05-22T13:00:01+00:00",
        "ended_at": "2026-05-22T13:00:02+00:00",
        "input": {
            "complaint_id": TEST_COMPLAINT_ID,
            "features": {
                "institution_size_band": 3,
                "vulnerable_consumer_flag": 1,
                "prior_findings_180d": 2,
                "narrative_length": 412,
            },
        },
        "output": {
            "score": 0.72,
            "rank_band": "high",
            "feature_contributions": [
                {
                    "feature_name": "vulnerable_consumer_flag",
                    "contribution": 0.21,
                    "direction": "positive",
                },
                {
                    "feature_name": "prior_findings_180d",
                    "contribution": 0.18,
                    "direction": "positive",
                },
            ],
            "model_version": "xgb-ranker-2026.03",
        },
        "status": "success",
        "error": None,
    }


def _canonical_success_run() -> dict:
    return {
        "id": _new_uuid(),
        "complaint_id": TEST_COMPLAINT_ID,
        "agent_name": "classifier",
        "agent_version": "classifier-0.4.0",
        "started_at": "2026-05-22T13:00:00+00:00",
        "ended_at": "2026-05-22T13:00:03+00:00",
        "status": "success",
        "tool_calls": [_bert_success_call(), _xgboost_success_call()],
        "final_output": {
            "classification": "undisclosed-fees-credit",
            "confidence": 0.87,
            "rank_band": "high",
        },
        "error": None,
    }


def test_json_schema_is_valid_draft_2020_12(schema: dict) -> None:
    """The schema document itself must validate against the Draft 2020-12 meta-schema."""

    Draft202012Validator.check_schema(schema)


def test_canonical_success_run_validates(
    validator: Draft202012Validator,
) -> None:
    validator.validate(_canonical_success_run())


def test_partial_run_with_bert_timeout_validates(
    validator: Draft202012Validator,
) -> None:
    """Seeded example 1: BERT timeout → regex fallback → partial run."""

    bert_timeout = {
        "tool_name": "bert_classifier",
        "tool_version": "bert_classifier-1.4.0",
        "started_at": "2026-05-22T13:00:00+00:00",
        "ended_at": "2026-05-22T13:00:05+00:00",
        "input": {
            "text": "Texto del reclamo del cliente.",
            "locale": "es-PE",
            "max_tokens": 512,
        },
        "output": None,
        "status": "timeout",
        "error": {
            "code": "BERT_TIMEOUT",
            "message": "Inference exceeded 5s budget.",
        },
    }
    regex_fallback = {
        "tool_name": "regex_taxonomy",
        "tool_version": "regex_taxonomy-2026.04",
        "started_at": "2026-05-22T13:00:05+00:00",
        "ended_at": "2026-05-22T13:00:05+00:00",
        "input": {
            "text": "Texto del reclamo del cliente.",
            "taxonomy_version": "anexo-1a-2025.12",
        },
        "output": {
            "matches": [
                {
                    "pattern_id": "ANX1A-FEE-MAINT-001",
                    "label": "undisclosed-fees-credit",
                    "span": [12, 42],
                    "matched_text": "comisión por mantenimiento",
                }
            ],
            "taxonomy_version": "anexo-1a-2025.12",
        },
        "status": "success",
        "error": None,
    }
    run = {
        "id": _new_uuid(),
        "complaint_id": TEST_COMPLAINT_ID,
        "agent_name": "classifier",
        "agent_version": "classifier-0.4.0",
        "started_at": "2026-05-22T13:00:00+00:00",
        "ended_at": "2026-05-22T13:00:05+00:00",
        "status": "partial",
        "tool_calls": [bert_timeout, regex_fallback],
        "final_output": {
            "classification": "undisclosed-fees-credit",
            "confidence_degraded": True,
        },
        "error": {
            "code": "BERT_TIMEOUT",
            "message": "Primary classifier timed out; regex fallback used.",
            "tool_name": "bert_classifier",
        },
    }
    validator.validate(run)


def test_failed_anonymizer_run_validates(
    validator: Draft202012Validator,
) -> None:
    """Seeded example 3: anonymizer failure → no downstream tool runs → failed run."""

    anonymizer_failure = {
        "tool_name": "anonymizer",
        "tool_version": "anonymizer-1.2.0",
        "started_at": "2026-05-22T13:00:00+00:00",
        "ended_at": "2026-05-22T13:00:01+00:00",
        "input": {
            "text": "Narrativa con PII.",
            "policy_version": "pii-2026.03",
        },
        "output": None,
        "status": "failed",
        "error": {
            "code": "ANONYMIZER_INTERNAL_ERROR",
            "message": "Anonymizer crashed; downstream tools blocked.",
        },
    }
    run = {
        "id": _new_uuid(),
        "complaint_id": TEST_COMPLAINT_ID,
        "agent_name": "classifier",
        "agent_version": "classifier-0.4.0",
        "started_at": "2026-05-22T13:00:00+00:00",
        "ended_at": "2026-05-22T13:00:01+00:00",
        "status": "failed",
        "tool_calls": [anonymizer_failure],
        "final_output": None,
        "error": {
            "code": "ANONYMIZER_INTERNAL_ERROR",
            "message": "Run aborted: anonymizer could not produce safe input.",
            "tool_name": "anonymizer",
        },
    }
    validator.validate(run)


def test_invalid_status_is_rejected(
    validator: Draft202012Validator,
) -> None:
    run = _canonical_success_run()
    run["status"] = "succeeded"  # Not in enum.
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(run)


def test_success_run_with_null_final_output_is_rejected(
    validator: Draft202012Validator,
) -> None:
    """status=success requires final_output to be a non-null object."""

    run = _canonical_success_run()
    run["final_output"] = None
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(run)


def test_bert_call_with_wrong_locale_is_rejected(
    validator: Draft202012Validator,
) -> None:
    run = _canonical_success_run()
    run["tool_calls"][0]["input"]["locale"] = "en-US"  # Schema pins locale to es-PE.
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(run)


def test_bare_local_datetime_without_timezone_is_rejected(
    validator: Draft202012Validator,
) -> None:
    """The doc says bare local datetimes are invalid; the pattern enforces it."""

    run = _canonical_success_run()
    run["started_at"] = "2026-05-22T13:00:00"  # No timezone designator.
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(run)


def test_invalid_complaint_id_format_is_rejected(
    validator: Draft202012Validator,
) -> None:
    """A bare UUID does not match the SBS complaint-id pattern."""

    run = _canonical_success_run()
    run["complaint_id"] = _new_uuid()  # UUID, not BCP-2026-... pattern.
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(run)


# ---------------------------------------------------------------------------
# Live-stack DB test — the P10↔P12 integration gate.
#
# Spins up the schema, calls the WS0b seed (which writes six runs including
# the three required partial-failure traces), reads every row back, and
# validates each against the JSON Schema. When Prompt 12 replaces the seed
# with live agent output, the same query + validation runs against live
# rows. As long as this stays green, the supervisor UI does not break at
# the cutover.
# ---------------------------------------------------------------------------


@pytestmark_db
async def test_seeded_rows_validate_against_schema_against_live_db(
    test_database_url: str,
    db_schema,
    validator: Draft202012Validator,
) -> None:
    """Seed agent_runs against the testcontainer DB and validate every row."""

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.agent_run import AgentRun

    # Import via scripts/ which conftest.py adds to sys.path.
    from seed_demo_narrative import seed_agent_runs  # type: ignore[import-not-found]

    complaint_ids = ["BCO-2026-000001", "BCO-2026-000002", "BCO-2026-000003"]
    engine = create_async_engine(test_database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            inserted = await seed_agent_runs(
                session, complaint_ids, institution_id="SBS-001234"
            )
            await session.commit()

        async with session_maker() as session:
            result = await session.execute(select(AgentRun))
            rows = result.scalars().all()
    finally:
        await engine.dispose()

    assert inserted == 6, f"expected 6 seeded rows, got {inserted}"
    assert len(rows) == 6, f"expected 6 rows in DB, got {len(rows)}"

    statuses = sorted(row.status for row in rows)
    # Three partial-or-worse (per the schema contract's three required traces):
    # 1× partial (BERT timeout), 1× partial (XGBoost unavailable), 1× failed (anonymizer).
    assert statuses.count("partial") == 2, statuses
    assert statuses.count("failed") == 1, statuses
    assert statuses.count("success") == 3, statuses

    seeded_complaint_ids = {row.complaint_id for row in rows}
    assert seeded_complaint_ids == set(complaint_ids), seeded_complaint_ids

    # Validate every row against the JSON Schema.
    for row in rows:
        serialised = _agent_run_row_to_dict(row)
        validator.validate(serialised)


@pytestmark_db
async def test_seed_is_idempotent_against_live_db(
    test_database_url: str,
    db_schema,
) -> None:
    """Re-running the seed leaves the row count stable."""

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.agent_run import AgentRun

    from seed_demo_narrative import seed_agent_runs  # type: ignore[import-not-found]

    complaint_ids = ["BCO-2026-000001", "BCO-2026-000002", "BCO-2026-000003"]
    engine = create_async_engine(test_database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            await seed_agent_runs(session, complaint_ids, institution_id="SBS-001234")
            await session.commit()
        async with session_maker() as session:
            await seed_agent_runs(session, complaint_ids, institution_id="SBS-001234")
            await session.commit()
        async with session_maker() as session:
            result = await session.execute(select(AgentRun))
            count = len(result.scalars().all())
    finally:
        await engine.dispose()

    assert count == 6, f"expected idempotent seed to leave 6 rows, got {count}"


def _agent_run_row_to_dict(row) -> dict:
    """Convert an :class:`AgentRun` ORM row into the JSON shape the schema validates."""

    return {
        "id": row.id,
        "complaint_id": row.complaint_id,
        "agent_name": row.agent_name,
        "agent_version": row.agent_version,
        "started_at": row.started_at.isoformat(timespec="seconds"),
        "ended_at": row.ended_at.isoformat(timespec="seconds") if row.ended_at else None,
        "status": row.status,
        "tool_calls": row.tool_calls,
        "final_output": row.final_output,
        "error": row.error,
    }
