"""Demo seed for the supervisor UI narrative — Prompt 10 / WS0b.

This script writes ``agent_runs`` rows that the supervisor UI's Findings
drilldown and Approvals evidence panels read from. The rows conform to
the JSON Schema contract at ``docs/schemas/agent_run.schema.json``.

Scope of this turn (WS0b):

* Seed ``agent_runs`` only. Complaint, institution, cross-source, and
  audit seeding land with their owning workstreams (WS3 cockpit, WS6
  audit). The complaints referenced here must already exist — either
  from the ``db_schema`` test fixture (three ``BCO-2026-000001..3``
  rows on ``BANCO_DEMO_001``) or from real ingestion via the API.
* Three required partial-failure traces, per the schema contract:
  BERT timeout, XGBoost unavailable, anonymizer error.
* Plus successful runs (classifier, narrative-drafter,
  cross-source-correlator) so the UI sees the happy path on Day 1.

Idempotent: re-running deletes any prior ``agent_runs`` rows for the
target ``complaint_id`` set, then inserts a fresh dataset.

Importable for tests: ``build_demo_runs`` and ``seed_agent_runs`` are
the two functions the integration test calls directly.

CLI usage::

    python scripts/seed_demo_narrative.py
    python scripts/seed_demo_narrative.py --complaint-id BCO-2026-000001 \\
                                          --complaint-id BCO-2026-000002 \\
                                          --complaint-id BCO-2026-000003
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make ``sbs_api`` importable when this script is invoked from the repo
# root (the uv workspace layout has ``api/`` as a member).
ROOT = Path(__file__).resolve().parent.parent
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _ts(dt: datetime) -> str:
    """ISO 8601 with explicit ``+00:00`` timezone — what the schema requires."""

    if dt.tzinfo is None:
        raise ValueError("anchor timestamps must be timezone-aware")
    return dt.isoformat(timespec="seconds")


def _run_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Builders for individual tool calls. Each builder returns a dict conforming
# to the ``tool_call`` shape in ``docs/schemas/agent_run.schema.json``.
# ---------------------------------------------------------------------------


def _anonymizer_success(narrative: str, start: datetime) -> dict:
    return {
        "tool_name": "anonymizer",
        "tool_version": "anonymizer-1.2.0",
        "started_at": _ts(start),
        "ended_at": _ts(start + timedelta(milliseconds=120)),
        "input": {"text": narrative, "policy_version": "pii-2026.03"},
        "output": {
            "anonymized_text": narrative,
            "redactions": [],
            "policy_version": "pii-2026.03",
        },
        "status": "success",
        "error": None,
    }


def _anonymizer_failure(narrative: str, start: datetime) -> dict:
    return {
        "tool_name": "anonymizer",
        "tool_version": "anonymizer-1.2.0",
        "started_at": _ts(start),
        "ended_at": _ts(start + timedelta(milliseconds=80)),
        "input": {"text": narrative, "policy_version": "pii-2026.03"},
        "output": None,
        "status": "failed",
        "error": {
            "code": "ANONYMIZER_INTERNAL_ERROR",
            "message": "Tokenizer raised on malformed unicode at offset 217.",
        },
    }


def _bert_success(narrative: str, start: datetime, label: str, confidence: float) -> dict:
    return {
        "tool_name": "bert_classifier",
        "tool_version": "bert_classifier-1.4.0",
        "started_at": _ts(start),
        "ended_at": _ts(start + timedelta(milliseconds=480)),
        "input": {"text": narrative, "locale": "es-PE", "max_tokens": 512},
        "output": {
            "label": label,
            "confidence": confidence,
            "top_k": [
                {"label": label, "confidence": confidence},
                {"label": "misselling", "confidence": round(1 - confidence - 0.05, 2)},
                {"label": "billing-dispute", "confidence": 0.05},
            ],
            "model_version": "beto-onnx-2026.04",
        },
        "status": "success",
        "error": None,
    }


def _bert_timeout(narrative: str, start: datetime) -> dict:
    return {
        "tool_name": "bert_classifier",
        "tool_version": "bert_classifier-1.4.0",
        "started_at": _ts(start),
        "ended_at": _ts(start + timedelta(seconds=5)),
        "input": {"text": narrative, "locale": "es-PE", "max_tokens": 512},
        "output": None,
        "status": "timeout",
        "error": {
            "code": "BERT_TIMEOUT",
            "message": "ONNX inference exceeded the 5s per-request budget.",
        },
    }


def _regex_fallback(narrative: str, start: datetime) -> dict:
    return {
        "tool_name": "regex_taxonomy",
        "tool_version": "regex_taxonomy-2026.04",
        "started_at": _ts(start),
        "ended_at": _ts(start + timedelta(milliseconds=12)),
        "input": {"text": narrative, "taxonomy_version": "anexo-1a-2025.12"},
        "output": {
            "matches": [
                {
                    "pattern_id": "ANX1A-FEE-MAINT-001",
                    "label": "undisclosed-fees-credit",
                    "span": [42, 68],
                    "matched_text": "comisión por mantenimiento",
                }
            ],
            "taxonomy_version": "anexo-1a-2025.12",
        },
        "status": "success",
        "error": None,
    }


def _xgboost_success(complaint_id: str, start: datetime) -> dict:
    """Eight named features per the WS4 directive. The highest positive
    contributor is ``narrative_mentions_fee_undisclosed`` so the SHAP
    panel tells the demo story — the model latched onto the
    comisión-por-mantenimiento sub-pattern."""

    return {
        "tool_name": "xgboost_ranker",
        "tool_version": "xgboost_ranker-0.9.2",
        "started_at": _ts(start),
        "ended_at": _ts(start + timedelta(milliseconds=90)),
        "input": {
            "complaint_id": complaint_id,
            "features": {
                "vulnerable_consumer_flag": 1,
                "prior_findings_180d": 2,
                "narrative_mentions_fee_undisclosed": 1,
                "institution_size_band": 3,
                "complaint_velocity_28d": 412,
                "narrative_length": 612,
                "cross_source_signal_count": 3,
                "regex_taxonomy_hit_count": 2,
            },
        },
        "output": {
            "score": 0.78,
            "rank_band": "high",
            "feature_contributions": [
                {
                    "feature_name": "narrative_mentions_fee_undisclosed",
                    "contribution": 0.27,
                    "direction": "positive",
                },
                {
                    "feature_name": "vulnerable_consumer_flag",
                    "contribution": 0.19,
                    "direction": "positive",
                },
                {
                    "feature_name": "prior_findings_180d",
                    "contribution": 0.16,
                    "direction": "positive",
                },
                {
                    "feature_name": "cross_source_signal_count",
                    "contribution": 0.12,
                    "direction": "positive",
                },
                {
                    "feature_name": "complaint_velocity_28d",
                    "contribution": 0.08,
                    "direction": "positive",
                },
                {
                    "feature_name": "regex_taxonomy_hit_count",
                    "contribution": 0.05,
                    "direction": "positive",
                },
                {
                    "feature_name": "institution_size_band",
                    "contribution": -0.04,
                    "direction": "negative",
                },
                {
                    "feature_name": "narrative_length",
                    "contribution": -0.06,
                    "direction": "negative",
                },
            ],
            "model_version": "xgb-ranker-2026.03",
        },
        "status": "success",
        "error": None,
    }


def _xgboost_unavailable(complaint_id: str, start: datetime) -> dict:
    return {
        "tool_name": "xgboost_ranker",
        "tool_version": "xgboost_ranker-0.9.2",
        "started_at": _ts(start),
        "ended_at": _ts(start + timedelta(milliseconds=4)),
        "input": {"complaint_id": complaint_id, "features": {}},
        "output": None,
        "status": "failed",
        "error": {
            "code": "XGBOOST_UNAVAILABLE",
            "message": "MLflow model server returned HTTP 503.",
        },
    }


def _qlik_lookup_success(institution_id: str, start: datetime) -> dict:
    return {
        "tool_name": "qlik_lookup",
        "tool_version": "qlik_lookup-saas-2025.11",
        "started_at": _ts(start),
        "ended_at": _ts(start + timedelta(milliseconds=210)),
        "input": {
            "institution_id": institution_id,
            "lookup_keys": [
                "complaint_volume_28d",
                "prior_findings_180d",
                "segment_baseline",
            ],
        },
        "output": {
            "results": {
                "complaint_volume_28d": 412,
                "prior_findings_180d": 2,
                "segment_baseline": {"median": 380, "p90": 540},
            },
            "source_version": "qlik-app-conduct-2026.05",
            "fetched_at": _ts(start + timedelta(milliseconds=205)),
        },
        "status": "success",
        "error": None,
    }


# ---------------------------------------------------------------------------
# Run builders. Each returns a dict conforming to the top-level ``agent_run``
# schema. ``complaint_ids`` is expected to contain at least three entries —
# the script enforces this so the three required partial-failure shapes
# always seed.
# ---------------------------------------------------------------------------


_NARRATIVE_PARA_2 = (
    "El cliente reporta que su tarjeta tuvo una comisión por mantenimiento "
    "no informada al momento de la apertura, con cargos recurrentes."
)


def _classifier_partial_bert_timeout(
    complaint_id: str, anchor: datetime
) -> dict:
    """Partial run #1: BERT times out, regex fallback succeeds.

    The agent produces a usable classification via the regex match (the
    "comisión por mantenimiento" sub-pattern), but flags
    ``confidence_degraded`` so the UI shows the regex-fallback indicator.
    """

    anon = _anonymizer_success(_NARRATIVE_PARA_2, anchor)
    bert = _bert_timeout(_NARRATIVE_PARA_2, anchor + timedelta(milliseconds=130))
    regex = _regex_fallback(
        _NARRATIVE_PARA_2, anchor + timedelta(seconds=5, milliseconds=140)
    )
    return {
        "id": _run_id(),
        "complaint_id": complaint_id,
        "agent_name": "classifier",
        "agent_version": "classifier-0.4.0",
        "started_at": _ts(anchor),
        "ended_at": _ts(anchor + timedelta(seconds=5, milliseconds=160)),
        "status": "partial",
        "tool_calls": [anon, bert, regex],
        "final_output": {
            "classification": "undisclosed-fees-credit",
            "confidence": 0.62,
            "sub_patterns": [
                {
                    "label": "comision-por-mantenimiento",
                    "evidence_span": [42, 68],
                }
            ],
            "confidence_degraded": True,
        },
        "error": {
            "code": "BERT_TIMEOUT",
            "message": "Primary classifier timed out; regex fallback used.",
            "tool_name": "bert_classifier",
        },
    }


def _classifier_partial_xgboost_unavailable(
    complaint_id: str, anchor: datetime
) -> dict:
    """Partial run #2: anonymizer + BERT succeed, XGBoost ranker fails.

    The classification stands; ``rank_band`` is omitted because the ranker
    could not score.
    """

    anon = _anonymizer_success(_NARRATIVE_PARA_2, anchor)
    bert = _bert_success(
        _NARRATIVE_PARA_2,
        anchor + timedelta(milliseconds=130),
        "undisclosed-fees-credit",
        0.84,
    )
    xgb = _xgboost_unavailable(
        complaint_id, anchor + timedelta(milliseconds=620)
    )
    return {
        "id": _run_id(),
        "complaint_id": complaint_id,
        "agent_name": "classifier",
        "agent_version": "classifier-0.4.0",
        "started_at": _ts(anchor),
        "ended_at": _ts(anchor + timedelta(milliseconds=640)),
        "status": "partial",
        "tool_calls": [anon, bert, xgb],
        "final_output": {
            "classification": "undisclosed-fees-credit",
            "confidence": 0.84,
            "sub_patterns": [],
            "rank_band": None,
        },
        "error": {
            "code": "XGBOOST_UNAVAILABLE",
            "message": "Ranker unreachable; classification stands without rank band.",
            "tool_name": "xgboost_ranker",
        },
    }


def _classifier_failed_anonymizer(complaint_id: str, anchor: datetime) -> dict:
    """Failed run: anonymizer errors → no downstream tool may consume narrative.

    Surfaces in the Audit screen as an operator-visible incident.
    """

    anon = _anonymizer_failure(_NARRATIVE_PARA_2, anchor)
    return {
        "id": _run_id(),
        "complaint_id": complaint_id,
        "agent_name": "classifier",
        "agent_version": "classifier-0.4.0",
        "started_at": _ts(anchor),
        "ended_at": _ts(anchor + timedelta(milliseconds=100)),
        "status": "failed",
        "tool_calls": [anon],
        "final_output": None,
        "error": {
            "code": "ANONYMIZER_INTERNAL_ERROR",
            "message": "Run aborted: anonymizer could not produce safe input.",
            "tool_name": "anonymizer",
        },
    }


def _classifier_success(complaint_id: str, anchor: datetime) -> dict:
    """Happy-path classifier run — anonymizer + BERT + XGBoost all green."""

    anon = _anonymizer_success(_NARRATIVE_PARA_2, anchor)
    bert = _bert_success(
        _NARRATIVE_PARA_2,
        anchor + timedelta(milliseconds=130),
        "undisclosed-fees-credit",
        0.87,
    )
    xgb = _xgboost_success(complaint_id, anchor + timedelta(milliseconds=620))
    return {
        "id": _run_id(),
        "complaint_id": complaint_id,
        "agent_name": "classifier",
        "agent_version": "classifier-0.4.0",
        "started_at": _ts(anchor),
        "ended_at": _ts(anchor + timedelta(milliseconds=720)),
        "status": "success",
        "tool_calls": [anon, bert, xgb],
        "final_output": {
            "classification": "undisclosed-fees-credit",
            "confidence": 0.87,
            "sub_patterns": [
                {
                    "label": "comision-por-mantenimiento",
                    "evidence_span": [42, 68],
                }
            ],
        },
        "error": None,
    }


def _cross_source_correlator_success(
    complaint_id: str, anchor: datetime, institution_id: str
) -> dict:
    """Cross-source signal fusion — the anomaly card on the cockpit."""

    qlik = _qlik_lookup_success(institution_id, anchor)
    return {
        "id": _run_id(),
        "complaint_id": complaint_id,
        "agent_name": "cross-source-correlator",
        "agent_version": "cross-source-correlator-0.2.0",
        "started_at": _ts(anchor),
        "ended_at": _ts(anchor + timedelta(milliseconds=260)),
        "status": "success",
        "tool_calls": [qlik],
        "final_output": {
            "composite_score": 0.74,
            "threshold": 0.70,
            "channel_contributions": [
                {"channel": "complaints", "value": 0.62, "contribution": 0.18},
                {"channel": "indecopi", "value": 0.55, "contribution": 0.30},
                {"channel": "social", "value": 0.41, "contribution": 0.20},
                {"channel": "plavia", "value": 0.38, "contribution": 0.06},
            ],
            "anomaly_flag": True,
        },
        "error": None,
    }


def _narrative_drafter_success(complaint_id: str, anchor: datetime) -> dict:
    """Narrative-drafter run — the analyst-editable draft on Findings.

    The drafted text deliberately omits the "comisión por mantenimiento"
    mention from paragraph two of the narrative — that is the scripted
    edit gap the Conduct Analyst fills during the demo. After her edit, the saved
    draft includes the maintenance-fee reference; the audit row carries
    before/after excerpts.
    """

    return {
        "id": _run_id(),
        "complaint_id": complaint_id,
        "agent_name": "narrative-drafter",
        "agent_version": "narrative-drafter-0.3.0",
        "started_at": _ts(anchor),
        "ended_at": _ts(anchor + timedelta(milliseconds=820)),
        "status": "success",
        "tool_calls": [],
        "final_output": {
            "draft_text": (
                "Disputa de cliente sobre comisiones de cuenta."
            ),
            "language": "es-PE",
            "evidence_refs": [],
        },
        "error": None,
    }


def build_demo_runs(
    complaint_ids: list[str],
    institution_id: str = "SBS-001234",
    anchor: datetime | None = None,
) -> list[dict]:
    """Return demo ``agent_run`` rows for the given complaint IDs.

    Six rows total, distributed so the headline complaint (cid0) is
    the demo's "clean classifier success" example with the full agent
    chain — what the Conduct Analyst drills into on the Findings page. The two
    partial-failure traces (BERT timeout, XGBoost unavailable) and the
    anonymizer-failure live on the other two complaints so the
    headline's agent-reasoning timeline reads as "everything worked":

    * complaint 0 (HEADLINE) — classifier success (with named XGBoost
      features), narrative-drafter success (missing the maintenance-
      fee mention — the scripted edit gap), cross-source-correlator
      success (anomaly_flag=true).
    * complaint 1 — classifier partial (BERT timeout + regex fallback)
      and classifier partial (XGBoost unavailable). Two illustrative
      partial-failure traces on one complaint.
    * complaint 2 — classifier failed (anonymizer error). The third
      required partial-failure shape per the JSON Schema contract.

    Status counts: 3 success + 2 partial + 1 failed = 6. The
    integration test asserts this exact distribution.
    """

    if len(complaint_ids) < 3:
        raise ValueError(
            "build_demo_runs requires at least three complaint IDs so the "
            "three partial-failure invariants can each seed."
        )
    if anchor is None:
        anchor = datetime.now(tz=timezone.utc).replace(microsecond=0)

    cid0, cid1, cid2 = complaint_ids[0], complaint_ids[1], complaint_ids[2]

    return [
        # Headline complaint — clean agent chain, narrative drafted by
        # the agent but MISSING the comisión-por-mantenimiento mention.
        _classifier_success(cid0, anchor - timedelta(hours=3)),
        _narrative_drafter_success(cid0, anchor - timedelta(hours=2)),
        _cross_source_correlator_success(
            cid0, anchor - timedelta(hours=1), institution_id
        ),
        # Second complaint — two illustrative partial-failure traces.
        _classifier_partial_bert_timeout(cid1, anchor - timedelta(hours=4)),
        _classifier_partial_xgboost_unavailable(
            cid1, anchor - timedelta(hours=2, minutes=30)
        ),
        # Third complaint — anonymizer failure, the JSON Schema
        # contract's third required partial-failure shape.
        _classifier_failed_anonymizer(cid2, anchor - timedelta(hours=4)),
    ]


# ---------------------------------------------------------------------------
# Database persistence. Imports happen inside the function so the pure
# builders above stay importable without a DB.
# ---------------------------------------------------------------------------


async def seed_agent_runs(
    session,
    complaint_ids: list[str],
    institution_id: str = "SBS-001234",
    anchor: datetime | None = None,
) -> int:
    """Idempotently insert demo ``agent_runs`` rows for the given complaints.

    Deletes any existing rows for these complaint IDs first, then inserts
    the fresh dataset. Returns the count of rows inserted.

    ``session`` is an ``AsyncSession``; the caller commits.
    """

    from datetime import datetime as _dt

    from sqlalchemy import delete

    from sbs_api.db.models.agent_run import AgentRun

    runs = build_demo_runs(complaint_ids, institution_id, anchor)

    await session.execute(
        delete(AgentRun).where(AgentRun.complaint_id.in_(complaint_ids))
    )

    session.add_all(
        [
            AgentRun(
                id=run["id"],
                complaint_id=run["complaint_id"],
                agent_name=run["agent_name"],
                agent_version=run["agent_version"],
                started_at=_dt.fromisoformat(run["started_at"]),
                ended_at=_dt.fromisoformat(run["ended_at"])
                if run["ended_at"]
                else None,
                status=run["status"],
                tool_calls=run["tool_calls"],
                final_output=run["final_output"],
                error=run["error"],
            )
            for run in runs
        ]
    )
    return len(runs)


async def _async_main(args: argparse.Namespace) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    complaint_ids = args.complaint_id or [
        "BCO-2026-000001",
        "BCO-2026-000002",
        "BCO-2026-000003",
    ]

    async with session_maker() as session:
        inserted = await seed_agent_runs(
            session,
            complaint_ids,
            institution_id=args.institution_id,
        )
        await session.commit()
    await engine.dispose()

    print(
        f"Seeded {inserted} agent_runs rows across "
        f"{len(complaint_ids)} complaints ({', '.join(complaint_ids)})."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--complaint-id",
        action="append",
        help="Repeatable. Complaint IDs to seed against. "
        "Default: BCO-2026-000001..3 (the conftest demo complaints).",
    )
    parser.add_argument(
        "--institution-id",
        default="SBS-001234",
        help="Institution for the cross-source-correlator Qlik lookup. "
        "Default: SBS-001234 (BANCO_DEMO_001).",
    )
    args = parser.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
