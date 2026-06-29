#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Print the N most-recent complaints + their agent processing state.

Used by /app/api/journey/recent to feed the live cockpit + processing
pages without an API roundtrip.

Output: JSON list, newest first:
    [{
        "complaint_id": "BCO-2026-...",
        "institution_id": "SBS-001234",
        "received_at": "2026-...",
        "motivo_code": "...",
        "product_category": "...",
        "narrative_preview": "first 120 chars",
        "agents": {"triage": "success", "investigation": "success", ...},
        "anomaly_score": 0.74 | null,
        "classification": "..." | null,
    }, ...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg


DSN = os.environ.get(
    "SBS_API_DATABASE_URL_SYNC",
    "postgresql://sbs:sbs@localhost:5432/sbs_dev",  # pragma: allowlist secret
).replace("+asyncpg", "")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args()

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.complaint_id, c.institution_id, c.received_at,
                   c.motivo_code, c.product_category,
                   substr(c.description_text, 1, 160) AS preview
            FROM complaints c
            WHERE c.complaint_id LIKE 'BCO-2026-%%' OR c.complaint_id LIKE 'COP-2026-%%'
            ORDER BY c.received_at DESC
            LIMIT %s
            """,
            (args.limit,),
        )
        complaints = [
            {
                "complaint_id": r[0],
                "institution_id": r[1],
                "received_at": r[2].isoformat(timespec="seconds") if r[2] else None,
                "motivo_code": r[3],
                "product_category": r[4],
                "narrative_preview": r[5],
            }
            for r in cur.fetchall()
        ]
        if not complaints:
            print(json.dumps([]))
            return 0
        ids = [c["complaint_id"] for c in complaints]
        placeholders = ",".join(["%s"] * len(ids))
        cur.execute(
            f"""
            SELECT complaint_id, agent_name, status, started_at, ended_at,
                   final_output
            FROM agent_runs
            WHERE complaint_id IN ({placeholders})
            ORDER BY started_at
            """,
            ids,
        )
        per_complaint: dict[str, dict] = {cid: {"agents": {}} for cid in ids}  # noqa: F841
        for cid, agent, status, started, ended, final_output in cur.fetchall():
            per_complaint[cid]["agents"][agent] = {
                "status": status,
                "started_at": started.isoformat(timespec="seconds") if started else None,
                "ended_at": ended.isoformat(timespec="seconds") if ended else None,
            }
            if agent == "investigation" and final_output:
                an = (final_output.get("anomaly") or {}) if isinstance(final_output, dict) else {}
                if an.get("composite_score") is not None:
                    per_complaint[cid]["anomaly_score"] = an["composite_score"]
            if agent == "triage" and final_output:
                cls = (final_output.get("classification") or {}) if isinstance(final_output, dict) else {}
                if cls.get("label"):
                    per_complaint[cid]["classification"] = {
                        "label": cls["label"],
                        "confidence": cls.get("confidence"),
                    }
        for c in complaints:
            extras = per_complaint[c["complaint_id"]]
            c.update(extras)

    print(json.dumps(complaints, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
