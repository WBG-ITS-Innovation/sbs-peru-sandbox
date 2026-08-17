#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Richer cockpit aggregates for the SUCAVE-style insights board.

Returns a single JSON object with:
    - kpis: counters (24h volume, anomalies, institutions active)
    - by_institution: top-10 institutions by 7-day volume
    - by_product: top-10 products
    - by_motivo: top-10 motivos
    - by_channel: channel distribution
    - by_severity: severity mix
    - by_source: tier-1 NRT vs tier-2 batch mix
    - hourly_24h: per-hour bar chart
    - daily_30d: per-day bar chart for the last 30 days
    - granular: small list of complaint records for the granular explorer
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import psycopg


DSN = os.environ.get(
    "SBS_API_DATABASE_URL_SYNC",
    "postgresql://sbs:sbs@localhost:5432/sbs_dev",  # pragma: allowlist secret
).replace("+asyncpg", "")


def _canon_channel(raw: str | None) -> str:
    if not raw:
        return "Otro"
    s = raw.strip().lower()
    if "web" in s or "pagina" in s:
        return "Página web"
    if "tele" in s:
        return "Vía telefónica"
    if "app" in s or "movil" in s:
        return "Aplicativo móvil"
    if "oficina" in s or "agencia" in s or "domicilio" in s:
        return "Oficina"
    if "correo" in s:
        return "Correo electrónico"
    return "Otro"


_MOTIVO_LABEL = {
    "COBRO_INDEBIDO": "Cobros indebidos",
    "cobros_indebidos": "Cobros indebidos",
    "OPERACION_NO_RECONOCIDA": "Operación no reconocida",
    "operaciones_no_reconocidas": "Operación no reconocida",
    "transacciones_no_procesadas": "Transacciones no procesadas",
    "INCUMPLIMIENTO_CONTRATO": "Incumplimiento de contrato",
    "DEMORA_ATENCION": "Demora en atención",
    "disconformidad_no_atencion": "Demora en atención",
    "CALIDAD_SERVICIO": "Calidad de servicio",
    "INFORMACION_INCORRECTA": "Información insuficiente",
    "informacion_insuficiente": "Información insuficiente",
    "PUBLICIDAD_ENGANOSA": "Publicidad engañosa",
    "error_datos_usuario": "Error datos usuario",
    "problemas_cajeros": "Problemas con cajeros",
    "incumplimiento_clausulas": "Incumplimiento de cláusulas",
}


_INST_LABEL = {
    "SBS-001234": "BANCO_DEMO_001",
    "SBS-005678": "COOPAC_DEMO_002",
    "SBS-009012": "FINANCIERA_DEMO_003",
}


def main() -> int:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        out: dict[str, Any] = {}

        # KPIs
        cur.execute("SELECT COUNT(*) FROM complaints WHERE received_at > now() - interval '24 hours'")
        complaints_24h = int(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(DISTINCT institution_id) FROM complaints "
            "WHERE received_at > now() - interval '7 days'"
        )
        active_inst = int(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM agent_runs WHERE agent_name='investigation' "
            "AND final_output->'anomaly'->>'composite_score' IS NOT NULL "
            "AND (final_output->'anomaly'->>'composite_score')::float >= 0.70"
        )
        anomalies_active = int(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM complaints WHERE received_at > now() - interval '7 days'"
        )
        complaints_7d = int(cur.fetchone()[0])
        out["kpis"] = {
            "complaints_24h": complaints_24h,
            "complaints_7d": complaints_7d,
            "active_institutions": active_inst,
            "anomalies_active": anomalies_active,
        }

        # By institution (top 10, last 7d)
        cur.execute(
            "SELECT institution_id, COUNT(*) FROM complaints "
            "WHERE received_at > now() - interval '7 days' "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
        )
        out["by_institution"] = [
            {
                "institution_id": r[0],
                "label": _INST_LABEL.get(r[0], r[0]),
                "count": int(r[1]),
            }
            for r in cur.fetchall()
        ]

        # By product
        cur.execute(
            "SELECT product_category, COUNT(*) FROM complaints "
            "WHERE received_at > now() - interval '7 days' "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
        )
        out["by_product"] = [
            {"product": (r[0] or "—"), "count": int(r[1])} for r in cur.fetchall()
        ]

        # By motivo (display labels)
        cur.execute(
            "SELECT motivo_code, COUNT(*) FROM complaints "
            "WHERE received_at > now() - interval '7 days' "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 20"
        )
        m: dict[str, int] = {}
        for code, n in cur.fetchall():
            label = _MOTIVO_LABEL.get(code, code or "—")
            m[label] = m.get(label, 0) + int(n)
        out["by_motivo"] = sorted(
            ({"motivo": k, "count": v} for k, v in m.items()),
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        # By channel
        cur.execute("SELECT channel, COUNT(*) FROM complaints GROUP BY channel")
        ch: dict[str, int] = {}
        for raw, n in cur.fetchall():
            label = _canon_channel(raw)
            ch[label] = ch.get(label, 0) + int(n)
        total = sum(ch.values()) or 1
        out["by_channel"] = sorted(
            (
                {"channel": k, "count": v, "pct": round(100 * v / total, 1)}
                for k, v in ch.items()
            ),
            key=lambda x: x["count"],
            reverse=True,
        )

        # By severity
        cur.execute("SELECT COALESCE(severity, 'MEDIUM'), COUNT(*) FROM complaints GROUP BY 1")
        out["by_severity"] = [
            {"severity": r[0], "count": int(r[1])} for r in cur.fetchall()
        ]

        # By source (Tier 1 NRT vs Tier 2 batch)
        cur.execute("SELECT COALESCE(source, 'unknown'), COUNT(*) FROM complaints GROUP BY 1")
        out["by_source"] = [
            {"source": r[0], "count": int(r[1])} for r in cur.fetchall()
        ]

        # Hourly histogram (24h)
        cur.execute(
            "SELECT to_char(date_trunc('hour', received_at), 'HH24:00') AS h, "
            "COUNT(*) FROM complaints "
            "WHERE received_at > now() - interval '24 hours' "
            "GROUP BY 1 ORDER BY 1"
        )
        out["hourly_24h"] = [
            {"hour": r[0], "count": int(r[1])} for r in cur.fetchall()
        ]

        # Daily histogram (30d)
        cur.execute(
            "SELECT to_char(date_trunc('day', received_at), 'MM-DD') AS d, "
            "COUNT(*) FROM complaints "
            "WHERE received_at > now() - interval '30 days' "
            "GROUP BY 1 ORDER BY 1"
        )
        out["daily_30d"] = [
            {"day": r[0], "count": int(r[1])} for r in cur.fetchall()
        ]

        # Granular records for the explorer
        cur.execute(
            "SELECT complaint_id, institution_id, motivo_code, product_category, "
            "       channel, COALESCE(severity, 'MEDIUM'), "
            "       to_char(received_at, 'YYYY-MM-DD HH24:MI') "
            "FROM complaints "
            "WHERE received_at > now() - interval '7 days' "
            "ORDER BY received_at DESC LIMIT 200"
        )
        out["granular"] = [
            {
                "complaint_id": r[0],
                "institution": _INST_LABEL.get(r[1], r[1]),
                "motivo": _MOTIVO_LABEL.get(r[2], r[2] or "—"),
                "product": r[3] or "—",
                "channel": _canon_channel(r[4]),
                "severity": r[5],
                "received_at": r[6],
            }
            for r in cur.fetchall()
        ]

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
