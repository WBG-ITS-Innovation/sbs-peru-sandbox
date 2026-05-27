#!/usr/bin/env python
"""Print JSON aggregates for the demo cockpit charts.

Three views:
  - hourly_24h: list of {hour, count} for the last 24 hours
  - by_channel: list of {channel, count, pct} (canonicalised, top 6)
  - top_motivos: list of {motivo, count} (top 5)

Output is a single JSON object on stdout. Reads database from
SBS_API_DATABASE_URL_SYNC env var; falls back to the docker-compose
default. Called from /app/api/journey/stats route handler.
"""

from __future__ import annotations

import json
import os
import sys

import psycopg

DSN = os.environ.get(
    "SBS_API_DATABASE_URL_SYNC",
    "postgresql://sbs:sbs@localhost:5432/sbs_dev",  # pragma: allowlist secret
).replace("+asyncpg", "")


# Canonicalisation: merge mixed-case forms so the donut chart isn't
# fragmented across "WEB" / "web" / "pagina_web".
def _canon_channel(raw: str | None) -> str:
    if not raw:
        return "OTRO"
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
    "transacciones_no_procesadas": "Transacciones no procesadas",
    "INCUMPLIMIENTO_CONTRATO": "Incumplimiento de contrato",
    "DEMORA_ATENCION": "Demora en atención",
    "CALIDAD_SERVICIO": "Calidad de servicio",
    "INFORMACION_INCORRECTA": "Información incorrecta",
    "PUBLICIDAD_ENGANOSA": "Publicidad engañosa",
}


def main() -> int:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        # 24-hour hourly histogram.
        cur.execute(
            """
            SELECT to_char(date_trunc('hour', received_at), 'HH24:00') AS hour,
                   COUNT(*) AS c
            FROM complaints
            WHERE received_at > now() - interval '24 hours'
            GROUP BY 1
            ORDER BY 1
            """
        )
        hourly = [{"hour": r[0], "count": int(r[1])} for r in cur.fetchall()]

        # Channels (canonicalised).
        cur.execute(
            "SELECT channel, COUNT(*) FROM complaints GROUP BY channel"
        )
        bucket: dict[str, int] = {}
        for raw, n in cur.fetchall():
            bucket[_canon_channel(raw)] = bucket.get(_canon_channel(raw), 0) + int(n)
        total = sum(bucket.values()) or 1
        by_channel = sorted(
            (
                {"channel": k, "count": v, "pct": round(100 * v / total, 1)}
                for k, v in bucket.items()
            ),
            key=lambda x: x["count"],
            reverse=True,
        )[:6]

        # Top motivos this week (canonicalised by display label).
        cur.execute(
            """
            SELECT motivo_code, COUNT(*) FROM complaints
            WHERE received_at > now() - interval '7 days'
            GROUP BY motivo_code
            ORDER BY COUNT(*) DESC
            LIMIT 10
            """
        )
        motivo_bucket: dict[str, int] = {}
        for code, n in cur.fetchall():
            label = _MOTIVO_LABEL.get(code, code)
            motivo_bucket[label] = motivo_bucket.get(label, 0) + int(n)
        top_motivos = sorted(
            ({"motivo": k, "count": v} for k, v in motivo_bucket.items()),
            key=lambda x: x["count"],
            reverse=True,
        )[:5]

    print(json.dumps({
        "hourly_24h": hourly,
        "by_channel": by_channel,
        "top_motivos": top_motivos,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
