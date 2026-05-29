#!/usr/bin/env python
"""Supervisor-side enrichment of seeded complaints (aggregate-dashboard slice 1).

Runs AFTER the synthetic corpus has been ingested through the Tier-2 batch
worker. Walks the ``complaints`` table and back-fills the supervisor-side /
derived fields the aggregate dashboard groups by:

* ``submotivo`` / ``submotivo_2`` — finer motive levels.
* ``topic``                       — trend / topic tag.
* ``resolution_status`` / ``estado_reclamo`` / ``tipo_resolucion`` /
  ``fecha_resolucion`` — synthetic resolution outcome.

IMPORTANT — these are SYNTHETIC stand-ins. In production:
  - submotivo / submotivo_2 / topic are produced by a BERT + regex
    classifier reading the redacted narrative;
  - the resolution fields arrive from the institution over time (the real
    Anexo 1-A FEC_RES / TIP_RES / EST_REC columns).
This script does NOT touch the institutional Anexo 1-A submission contract,
the batch worker, or its code-identity invariant. It only UPDATEs rows that
already exist.

Determinism: every value is a pure function of ``(seed, complaint_id)`` via a
per-complaint ``random.Random`` stream, so re-running is stable and the order
rows are visited does not matter. Re-running overwrites the prior enrichment
with identical values (idempotent). The only wall-clock dependence is the
"resolved date cannot be in the future" rule; pass ``--today`` for a fully
byte-stable run.

Usage::

    SBS_API_DATABASE_URL=postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev \\  # pragma: allowlist secret
        uv run python scripts/enrich_complaints.py --seed 2026

    # Restrict to the batch-ingested corpus (leave live/demo rows untouched):
    uv run python scripts/enrich_complaints.py --seed 2026 --source batch
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Make sbs_api importable (mirrors scripts/seed_demo.py).
ROOT = Path(__file__).resolve().parent.parent
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import select  # noqa: E402

from sbs_api.db.models.complaint import ComplaintRecord  # noqa: E402
from sbs_api.db.session import get_sessionmaker  # noqa: E402

# ---------------------------------------------------------------------------
# SYNTHETIC vocabularies — keyed by MotivoCode enum value (uppercase string).
# In production a BERT + regex classifier replaces every map below.
# ---------------------------------------------------------------------------

SUBMOTIVOS: dict[str, list[str]] = {
    "COBRO_INDEBIDO": [
        "comisión de mantenimiento",
        "cargo por transferencia",
        "seguro no solicitado",
        "comisión por uso de cajero",
        "membresía de tarjeta",
    ],
    "OPERACION_NO_RECONOCIDA": [
        "consumo no reconocido",
        "retiro en cajero",
        "compra online",
        "cargo recurrente no reconocido",
        "transferencia no autorizada",
    ],
    "DEMORA_ATENCION": [
        "demora en reverso",
        "demora en respuesta de reclamo",
        "demora en bloqueo de tarjeta",
        "demora en desembolso",
    ],
    "INCUMPLIMIENTO_CONTRATO": [
        "tasa distinta a la pactada",
        "condición no informada",
        "incumplimiento de promoción",
        "cláusula no aplicada",
    ],
    "CALIDAD_SERVICIO": [
        "trato inadecuado",
        "información contradictoria",
        "canal no disponible",
        "espera excesiva en agencia",
    ],
    "INFORMACION_INCORRECTA": [
        "estado de cuenta erróneo",
        "saldo incorrecto",
        "información de tasa incorrecta",
    ],
    "PUBLICIDAD_ENGANOSA": [
        "promoción no cumplida",
        "cero comisiones no respetado",
        "beneficio no otorgado",
    ],
    "OTRO": ["otro motivo", "no clasificado"],
}

# Optional second level — clustered descriptive phrases (full sentences, the
# kind a clustering model would surface). Each motivo has a SMALL pool, so the
# same phrase is REUSED across many complaints (deterministically by
# complaint_id) — clusters, not unique-per-row. A real clustering / classifier
# step replaces these maps in production. Empty list ⇒ submotivo_2 stays NULL.
SUBMOTIVOS_2: dict[str, list[str]] = {
    "COBRO_INDEBIDO": [
        "Cobro de comisión de mantenimiento no informada al momento de la apertura de la cuenta",
        "Cargo recurrente por un servicio que el cliente afirma haber cancelado previamente",
        "Comisión por operación en cajero de otra red aplicada sin aviso previo al cliente",
        "Cobro de seguro asociado al producto que el cliente declara no haber contratado",
        "Membresía anual de tarjeta cargada pese a la promoción de exoneración vigente",
    ],
    "OPERACION_NO_RECONOCIDA": [
        "Consumo con tarjeta en comercio del extranjero que el titular no reconoce",
        "Retiro en cajero automático realizado fuera del horario habitual del cliente",
        "Compra por internet no reconocida posterior a un posible robo de datos",
        "Transferencia interbancaria no autorizada hacia la cuenta de un tercero desconocido",
    ],
    "DEMORA_ATENCION": [
        "Reclamo sin respuesta tras superar el plazo regulatorio de quince días hábiles",
        "Demora en la reversión del cargo pese a reiterados requerimientos del cliente",
        "Bloqueo de tarjeta solicitado por fraude que no se ejecutó a tiempo",
        "Solicitud de desembolso de crédito aprobado que permanece pendiente varias semanas",
    ],
    "INCUMPLIMIENTO_CONTRATO": [
        "Tasa de interés aplicada distinta a la pactada en el contrato firmado",
        "Cláusula de penalidad aplicada de forma retroactiva sin comunicación previa al cliente",
        "Beneficio ofrecido durante la contratación que la entidad finalmente no otorgó",
    ],
    "CALIDAD_SERVICIO": [
        "Trato inadecuado del personal de la agencia durante la atención del reclamo",
        "Información contradictoria entregada por distintos canales sobre el mismo caso",
        "Canal digital no disponible de forma reiterada al intentar gestionar el producto",
    ],
    "INFORMACION_INCORRECTA": [
        "Estado de cuenta con un saldo que no coincide con los movimientos reales",
        "Información de tasa o comisión en la app distinta a la del contrato",
        "Reporte a central de riesgo con datos que el cliente considera erróneos",
    ],
    "PUBLICIDAD_ENGANOSA": [
        "Promoción de cero comisiones difundida que no se respetó al activar el producto",
        "Oferta de tasa preferencial que no se aplicó al formalizar el crédito",
    ],
    "OTRO": [
        "Caso sin categoría definida que requiere revisión manual del analista",
    ],
    # Freeform motivo codes present in the demo data (lowercase, not in the enum).
    "transacciones_no_procesadas": [
        "Operación que figura como exitosa pero cuyo monto fue descontado sin completarse",
        "Transferencia que salió de la cuenta y nunca llegó al destinatario indicado",
        "Pago en comercio rechazado en pantalla pero igualmente cargado a la cuenta",
        "Retiro por cajero no entregado pese a registrarse como operación realizada",
    ],
    "error_datos_usuario": [
        "Datos personales del cliente registrados con errores que impiden la gestión",
        "Información de contacto desactualizada que bloquea la atención del reclamo",
    ],
    "cobros_indebidos": [
        "Cobro de comisión no informada al momento de la apertura del producto",
        "Cargo recurrente por un servicio que el cliente afirma haber dado de baja",
    ],
}

TOPICS: dict[str, list[str]] = {
    "COBRO_INDEBIDO": ["comisiones ocultas", "cargos recurrentes", "seguros atados"],
    "OPERACION_NO_RECONOCIDA": ["tarjeta clonada", "fraude por phishing", "banca por internet"],
    "DEMORA_ATENCION": ["backlog de reclamos", "fallas app", "tiempos de respuesta"],
    "INCUMPLIMIENTO_CONTRATO": ["tasas y condiciones", "letra pequeña"],
    "CALIDAD_SERVICIO": ["atención en agencia", "soporte digital"],
    "INFORMACION_INCORRECTA": ["errores en estado de cuenta", "fallas app"],
    "PUBLICIDAD_ENGANOSA": ["publicidad de tarjetas", "promociones"],
    "OTRO": ["varios"],
}

# Fraction of complaints whose submotivo_2 is populated (rest stay NULL).
SUBMOTIVO_2_PRESENT_PROB = 0.55

# ---------------------------------------------------------------------------
# SYNTHETIC resolution-outcome distribution.
# tipo_resolucion mirrors the real Anexo 1-A TIP_RES convention
# (favor_usuario / favor_entidad), plus solucion_parcial for texture.
# ---------------------------------------------------------------------------

# Baseline P(favor_usuario | resolved) per motivo. Consumer-protection
# motivos (undue charges, unrecognised operations) skew toward the user.
FAVOR_USUARIO_BASE: dict[str, float] = {
    "COBRO_INDEBIDO": 0.72,
    "OPERACION_NO_RECONOCIDA": 0.68,
    "INFORMACION_INCORRECTA": 0.50,
    "DEMORA_ATENCION": 0.52,
    "PUBLICIDAD_ENGANOSA": 0.55,
    "INCUMPLIMIENTO_CONTRATO": 0.46,
    "CALIDAD_SERVICIO": 0.40,
    "OTRO": 0.45,
}
FAVOR_USUARIO_DEFAULT = 0.50

# Per-institution multiplier on the favor_usuario probability. FINANCIERA
# (SBS-009012) resolves noticeably worse for consumers than its peers — the
# red-flag story the dashboard should surface.
INSTITUTION_OUTCOME_MODIFIER: dict[str, float] = {
    "SBS-001234": 1.00,  # BANCO_DEMO_001
    "SBS-005678": 0.95,  # COOPAC_DEMO_002
    "SBS-009012": 0.55,  # FINANCIERA_DEMO_003 — worse-resolving outlier
}
INSTITUTION_OUTCOME_DEFAULT = 1.0

# Share of complaints that never reach a resolution (stuck pendiente).
# Combined with the "can't resolve in the future" rule below (which adds the
# in-flight cases), total resolution_status=pendiente lands ~20%, inside the
# realistic 15–25% band with headroom for the real corpus's motivo mix.
UNRESOLVED_BASE = 0.10

# Resolution lag (days) when a complaint does resolve. Triangular, mode ~7.
LAG_MIN_DAYS = 3
LAG_MODE_DAYS = 7
LAG_MAX_DAYS = 21

# A complaint counts as "recently received" (→ en_proceso when unresolved)
# if received within this many days of `today`.
RECENT_WINDOW_DAYS = 30


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def _resolution_outcome(rng: random.Random, motivo: str, institution_id: str) -> str:
    base = FAVOR_USUARIO_BASE.get(motivo, FAVOR_USUARIO_DEFAULT)
    modifier = INSTITUTION_OUTCOME_MODIFIER.get(
        institution_id, INSTITUTION_OUTCOME_DEFAULT
    )
    p_user = _clamp(base * modifier, 0.05, 0.95)
    r = rng.random()
    if r < p_user:
        return "favor_usuario"
    # Of the remaining (non-user) mass: 75% favor_entidad, 25% partial.
    remaining = 1.0 - p_user
    if r < p_user + 0.75 * remaining:
        return "favor_entidad"
    return "solucion_parcial"


def _enrich_one(
    record: ComplaintRecord, *, seed: int, today: date
) -> None:
    """Mutate ``record`` in place with deterministic synthetic enrichment."""

    rng = random.Random(f"{seed}:{record.complaint_id}".encode("utf-8"))
    motivo = record.motivo_code

    # 1) submotivo / submotivo_2 / topic. Draw order is fixed for determinism.
    submotivos = SUBMOTIVOS.get(motivo, SUBMOTIVOS["OTRO"])
    record.submotivo = rng.choice(submotivos)

    sub2_pool = SUBMOTIVOS_2.get(motivo, [])
    if sub2_pool and rng.random() < SUBMOTIVO_2_PRESENT_PROB:
        record.submotivo_2 = rng.choice(sub2_pool)
    else:
        record.submotivo_2 = None

    topics = TOPICS.get(motivo, TOPICS["OTRO"])
    record.topic = rng.choice(topics)

    # 2) resolution outcome. Draw all rolls unconditionally so the RNG stream
    #    position is stable regardless of which branch is taken.
    will_resolve = rng.random() >= UNRESOLVED_BASE
    lag_days = int(rng.triangular(LAG_MIN_DAYS, LAG_MAX_DAYS, LAG_MODE_DAYS))
    outcome = _resolution_outcome(rng, motivo, record.institution_id)

    resolved_date = record.received_date + timedelta(days=lag_days)
    is_recent = (today - record.received_date).days <= RECENT_WINDOW_DAYS

    if will_resolve and resolved_date <= today:
        # Resolved: outcome + a resolution date strictly after receipt.
        record.resolution_status = "atendido"
        record.estado_reclamo = "atendido"
        record.tipo_resolucion = outcome
        record.fecha_resolucion = resolved_date
    elif will_resolve:
        # Would resolve, but the resolution date is still in the future →
        # the case is in flight. No fabricated outcome.
        record.resolution_status = "pendiente"
        record.estado_reclamo = "en_proceso"
        record.tipo_resolucion = None
        record.fecha_resolucion = None
    else:
        # Stuck / not yet acted on. Recent ones read as en_proceso; older
        # ones as pendiente. No fabricated outcome.
        record.resolution_status = "pendiente"
        record.estado_reclamo = "en_proceso" if is_recent else "pendiente"
        record.tipo_resolucion = None
        record.fecha_resolucion = None


async def enrich(*, seed: int, today: date, source: str | None) -> dict[str, Counter]:
    sessionmaker = get_sessionmaker()
    stats: dict[str, Counter] = {
        "resolution_status": Counter(),
        "estado_reclamo": Counter(),
        "tipo_resolucion": Counter(),
        "by_institution_resolved": Counter(),
    }
    total = 0

    async with sessionmaker() as session:
        async with session.begin():
            stmt = select(ComplaintRecord)
            if source is not None:
                stmt = stmt.where(ComplaintRecord.source == source)
            result = await session.execute(stmt)
            for record in result.scalars():
                _enrich_one(record, seed=seed, today=today)
                total += 1
                stats["resolution_status"][record.resolution_status] += 1
                stats["estado_reclamo"][record.estado_reclamo or "—"] += 1
                stats["tipo_resolucion"][record.tipo_resolucion or "NULL"] += 1
                if record.tipo_resolucion == "favor_usuario":
                    stats["by_institution_resolved"][record.institution_id] += 1
            # session.begin() block commits on exit.

    stats["_total"] = Counter({"complaints": total})
    return stats


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="Deterministic seed. Must match the corpus seed (default 2026).",
    )
    p.add_argument(
        "--today",
        type=str,
        default=None,
        help=(
            "Anchor 'today' for the resolved-not-in-the-future rule "
            "(YYYY-MM-DD). Defaults to the UTC wall-clock date. Pass it for "
            "a fully byte-stable run."
        ),
    )
    p.add_argument(
        "--source",
        type=str,
        default=None,
        help=(
            "Optional complaints.source filter (e.g. 'batch'). Default: "
            "enrich every complaint regardless of source."
        ),
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    today = (
        date.fromisoformat(args.today)
        if args.today is not None
        else datetime.now(timezone.utc).date()
    )
    stats = asyncio.run(enrich(seed=args.seed, today=today, source=args.source))

    total = stats["_total"]["complaints"]
    print(f"enrich_complaints: updated {total} complaints (seed={args.seed}, today={today})")
    if total == 0:
        print("  (no rows matched — did the corpus ingest run first?)")
        return 0
    pend = stats["resolution_status"].get("pendiente", 0)
    print(f"  resolution_status: {dict(stats['resolution_status'])}")
    print(f"    → pendiente share: {pend / total:.1%} (target 15–25%)")
    print(f"  estado_reclamo:    {dict(stats['estado_reclamo'])}")
    print(f"  tipo_resolucion:   {dict(stats['tipo_resolucion'])}")
    print(f"  favor_usuario count by institution: {dict(stats['by_institution_resolved'])}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
