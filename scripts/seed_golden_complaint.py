#!/usr/bin/env python
"""Seed a 'golden complaint' for the 2026-05-27 SBS demo.

Picks the most recent live-ingestion-orchestrator complaint and inserts
three synthetic agent_runs (triage, investigation, synthesis) carrying
the locked demo invariants:

    composite_score = 0.74    (threshold = 0.70)
    classification  = undisclosed-fees-credit, confidence=0.87
    top feature     = narrative_mentions_fee_undisclosed, +0.27

The draft narrative DELIBERATELY omits "comisión por mantenimiento"
which is the storyline the supervisor catches the agent on.

Writes the chosen complaint_id to:
    app/src/lib/golden-complaint.json

so the Next.js app can read it without a DB round-trip. Idempotent —
re-running replaces the seeded rows for the same complaint_id.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Json

REPO = Path(__file__).resolve().parent.parent
OUT_JSON = REPO / "app" / "src" / "lib" / "golden-complaint.json"

DSN = os.environ.get(
    "SBS_API_DATABASE_URL_SYNC",
    "postgresql://sbs:sbs@localhost:5432/sbs_dev",  # pragma: allowlist secret
).replace("+asyncpg", "")


TRIAGE_OUTPUT = {
    "classification": {
        "label": "undisclosed-fees-credit",
        "confidence": 0.87,
        "model_id": "bert-classifier-0.1.0",
        "alternatives": [
            {"label": "operations-not-recognized", "confidence": 0.06},
            {"label": "service-quality", "confidence": 0.04},
        ],
    },
    "severity_recommendation": "HIGH",
}


INVESTIGATION_OUTPUT = {
    "feature_attribution": [
        {"name": "narrative_mentions_fee_undisclosed", "contribution": 0.27},
        {"name": "product_is_credit_or_card", "contribution": 0.18},
        {"name": "institution_recent_complaint_rate", "contribution": 0.14},
        {"name": "channel_is_app_movil", "contribution": 0.09},
        {"name": "amount_below_median_for_class", "contribution": -0.05},
    ],
    "feature_model_id": "xgboost-ranker-0.1.0",
    "anomaly": {
        "composite_score": 0.74,
        "threshold": 0.70,
        "contributors": [
            {"signal": "fee_disclosure_gap", "weight": 0.42},
            {"signal": "institution_rate_above_peer_p95", "weight": 0.21},
            {"signal": "complaint_text_pattern_match", "weight": 0.11},
        ],
        "model_id": "anomaly-detector-0.1.0",
    },
    "similar_complaints": [
        {"complaint_id": "BCO-2026-4427703", "similarity": 0.91},
        {"complaint_id": "BCO-2026-8925657", "similarity": 0.88},
        {"complaint_id": "BCO-2026-7677429", "similarity": 0.84},
    ],
    "draft_narrative": {
        "text": (
            "El reclamo del cliente describe un cargo no reconocido de "
            "S/ 700 en la tarjeta de crédito. La revisión preliminar indica "
            "que la entidad procesó la operación dentro de los parámetros "
            "del contrato y que no se identificaron cargos atípicos "
            "atribuibles a la entidad. Se recomienda dar respuesta "
            "favorable a la entidad y cerrar el caso sin observaciones "
            "adicionales."
        ),
        "model_id": "narrative-drafter-0.1.0",
    },
}


SYNTHESIS_OUTPUT = {
    "executive_summary": {
        "text": (
            "Anomalía compuesta 0.74 (umbral 0.70). El borrador del "
            "agente narra el caso como un cargo no reconocido y propone "
            "cerrar a favor de la entidad. La narrativa omite la "
            "comisión por mantenimiento, que es el patrón observado por "
            "la SBS en quejas similares contra esta entidad. Recomendamos "
            "que la supervisora revise la versión final antes de aprobar."
        ),
        "key_points": [
            "Anomalía 0.74 > umbral 0.70",
            "Borrador omite término clave: comisión por mantenimiento",
            "Patrón coincide con 3 reclamos similares (>0.84 similitud)",
            "Recomendación del agente contradice la evidencia agregada",
        ],
        "audience": "supervisor",
        "model_id": "synthesis-0.1.0",
    }
}


def _tool_call(name: str, output: dict, started_at: datetime,
               input_payload: dict | None = None, model_id: str | None = None) -> dict:
    return {
        "tool_name": name,
        "started_at": started_at.isoformat(timespec="milliseconds"),
        "ended_at": (started_at + timedelta(milliseconds=180)).isoformat(timespec="milliseconds"),
        "status": "success",
        "input": input_payload or {},
        "output": {**output, "model_version": model_id} if model_id else output,
    }


def _pick_golden(cur) -> str:
    cur.execute(
        """
        SELECT c.complaint_id
        FROM complaints c
        JOIN agent_runs r ON r.complaint_id = c.complaint_id
        WHERE c.complaint_id LIKE 'BCO-2026-%%'
          AND r.agent_name = 'live-ingestion-orchestrator'
        ORDER BY r.started_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit("no live-ingestion-orchestrator complaint to seed")
    return row[0]


def _insert_run(cur, *, complaint_id: str, agent_name: str, agent_version: str,
                 started_at: datetime, ended_at: datetime,
                 tool_calls: list, final_output: dict) -> str:
    run_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO agent_runs
            (id, complaint_id, agent_name, agent_version, started_at, ended_at,
             status, tool_calls, final_output)
        VALUES (%s, %s, %s, %s, %s, %s, 'success', %s, %s)
        """,
        (run_id, complaint_id, agent_name, agent_version, started_at, ended_at,
         Json(tool_calls), Json(final_output)),
    )
    return run_id


def main() -> int:
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            complaint_id = _pick_golden(cur)
            print(f"golden complaint: {complaint_id}")

            # Clear prior seed (idempotent re-run).
            cur.execute(
                "DELETE FROM agent_runs WHERE complaint_id = %s AND agent_name IN "
                "('triage','investigation','synthesis')",
                (complaint_id,),
            )
            print(f"  cleared {cur.rowcount} previously seeded rows")

            t0 = datetime.now(timezone.utc)
            triage_started = t0
            triage_ended = t0 + timedelta(milliseconds=410)
            inv_started = triage_ended + timedelta(milliseconds=50)
            inv_ended = inv_started + timedelta(milliseconds=820)
            syn_started = inv_ended + timedelta(milliseconds=50)
            syn_ended = syn_started + timedelta(milliseconds=540)

            triage_tools = [
                _tool_call(
                    "bert_classifier",
                    {"classification": "undisclosed-fees-credit", "confidence": 0.87},
                    triage_started,
                    input_payload={"narrative_chars": 320},
                    model_id="bert-classifier-0.1.0",
                ),
            ]
            _insert_run(
                cur, complaint_id=complaint_id,
                agent_name="triage", agent_version="0.1.0",
                started_at=triage_started, ended_at=triage_ended,
                tool_calls=triage_tools, final_output=TRIAGE_OUTPUT,
            )
            print("  inserted: triage")

            inv_tools = [
                _tool_call(
                    "rank_features",
                    {
                        "top_features": INVESTIGATION_OUTPUT["feature_attribution"],
                        "model_id": "xgboost-ranker-0.1.0",
                    },
                    inv_started,
                    input_payload={"max_features": 5},
                ),
                _tool_call(
                    "anomaly_detector",
                    INVESTIGATION_OUTPUT["anomaly"],
                    inv_started + timedelta(milliseconds=200),
                ),
                _tool_call(
                    "search_similar_complaints",
                    {"items": INVESTIGATION_OUTPUT["similar_complaints"]},
                    inv_started + timedelta(milliseconds=400),
                ),
                _tool_call(
                    "draft_narrative",
                    INVESTIGATION_OUTPUT["draft_narrative"],
                    inv_started + timedelta(milliseconds=600),
                ),
            ]
            _insert_run(
                cur, complaint_id=complaint_id,
                agent_name="investigation", agent_version="0.1.0",
                started_at=inv_started, ended_at=inv_ended,
                tool_calls=inv_tools, final_output=INVESTIGATION_OUTPUT,
            )
            print("  inserted: investigation")

            syn_tools = [
                _tool_call(
                    "compose_executive_summary",
                    SYNTHESIS_OUTPUT["executive_summary"],
                    syn_started,
                    input_payload={"audience": "supervisor"},
                ),
            ]
            _insert_run(
                cur, complaint_id=complaint_id,
                agent_name="synthesis", agent_version="0.1.0",
                started_at=syn_started, ended_at=syn_ended,
                tool_calls=syn_tools, final_output=SYNTHESIS_OUTPUT,
            )
            print("  inserted: synthesis")

            conn.commit()

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "complaint_id": complaint_id,
                "composite_score": 0.74,
                "anomaly_threshold": 0.70,
                "classification_label": "undisclosed-fees-credit",
                "classification_confidence": 0.87,
                "top_feature": {
                    "name": "narrative_mentions_fee_undisclosed",
                    "contribution": 0.27,
                },
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
