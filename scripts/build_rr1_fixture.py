#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Generate the RR1 reglamento-de-reclamos fixture — fully synthetic.

Output:  app/src/lib/rr1-2025.json

This script *generates*. It reads no workbook and needs no external
data: a fresh clone can reproduce the committed fixture byte-for-byte
with ``python scripts/build_rr1_fixture.py``. That is deliberate. An
earlier version of this script extracted real SBS supervisory
statistics from a workbook shared under a private arrangement, and
committed the extract — month-by-month complaint volumes attributed to
named, real, regulated Peruvian entities. Publishing that was not the
project's to do. Nothing derived from that workbook survives here.

Determinism follows the house convention of
``scripts/generate-synthetic-corpus.py`` (ADR 0036): a ``--seed`` and a
fixed generation anchor, so the same inputs give byte-identical output
on any machine.

What is invented here, and what is not:

* **Institution labels are invented.** Every entity in the Empresa
  sheet is a fictional institution in the same spaced style as the
  ``scripts/dev-seed.sql`` demo institutions (``Banco Nuevo Horizonte
  del Perú``), keeping the leading segment keyword that
  ``peer_risk.cohorts`` derives a segment from. Zero real financial
  institutions are named. ``tests/cleanup/test_no_real_entities.py``
  enforces this.
* **Every count is invented.** Volumes come from a seeded Pareto-shaped
  draw over an invented grand total. They are not, and are not derived
  from, any real complaint statistic.
* **Dimension labels for Producto and Motivo are the regulatory
  code-list vocabulary** of the RR1 report — the product categories and
  complaint motives named in the reglamento de reclamos. These are
  category names, not data: the point of the page is that a supervisor
  recognises the SUCAVE layout, which requires the real vocabulary.
  No volume attaches to them here that came from anywhere but this
  script.

The three sheets keep the shape the page renders: a row label, twelve
monthly counts, and a Total general. Empresa additionally keeps the
workbook's hierarchy — five segment heading rows, each an exact
month-wise subtotal of the entity rows beneath it.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "app" / "src" / "lib" / "rr1-2025.json"

# Fixed anchor so regeneration is byte-stable. Bump deliberately, never
# from the wall clock — a moving timestamp makes the fixture churn in
# every diff and breaks the "same seed, same bytes" guarantee.
GENERATED_AT = "2026-08-14T00:00:00+00:00"
DEFAULT_SEED = 2026

MONTHS = ["Ene-25", "Feb-25", "Mar-25", "Abr-25", "May-25", "Jun-25",
          "Jul-25", "Ago-25", "Set-25", "Oct-25", "Nov-25", "Dic-25"]

# Invented annual volume for the whole reporting universe. Round by
# design — a suspiciously precise grand total invites the reader to
# believe it was measured.
GRAND_TOTAL = 2_650_000

# Seasonal curve, twelve relative weights. Mild and made up: a dip over
# the southern-hemisphere summer holidays, a rise into the last quarter.
SEASONAL = (0.97, 0.88, 0.95, 0.93, 1.00, 1.01,
            1.04, 1.05, 1.06, 1.09, 0.99, 1.03)

# Rows below this annual volume are apportioned sparsely instead — a
# handful of months reporting, the rest blank. The report looks like
# this at the bottom of every table, and the workbench has to keep
# telling a blank month apart from a month that reported zero.
SPARSE_BELOW = 40


# ---------------------------------------------------------------------------
# Fictional institutions
# ---------------------------------------------------------------------------
#
# Spaced, readable, and plainly invented — two-word compounds that no
# real brand uses. The leading keyword (Banco / Financiera / Caja) is
# load-bearing: peer_risk.cohorts derives the segment from it, and the
# Empresa sheet's heading rows are the same segment classes the
# reglamento reports on. The first name in the Banco and Financiera
# segments is the corresponding dev-seed.sql demo institution, so the
# RR1 page and the rest of the sandbox name the same fiction.

BANCOS: tuple[str, ...] = (
    "Banco Nuevo Horizonte del Perú",
    "Banco Altiplano Sur",
    "Banco Aurora Andina",
    "Banco Cielo Abierto",
    "Banco Cumbre Blanca",
    "Banco del Valle Sereno",
    "Banco Faro del Pacífico",
    "Banco Flor de Retama",
    "Banco Herradura Real",
    "Banco Inti Wasi",
    "Banco Laguna Azul",
    "Banco Manantial Norte",
    "Banco Pampa Verde",
    "Banco Puente Nuevo",
    "Banco Quinua Dorada",
    "Banco Sol de Enero",
    "Banco Tierra Firme",
    "Banco Viento Norte",
)

FINANCIERAS: tuple[str, ...] = (
    "Financiera Surandina del Perú",
    "Financiera Cielo Claro",
    "Financiera Espiga Norte",
    "Financiera Kantu Andina",
    "Financiera Molle Verde",
    "Financiera Puna Alta",
    "Financiera Rumi Wasi",
)

CAJAS_MUNICIPALES: tuple[str, ...] = (
    "Caja Municipal Aurora",
    "Caja Municipal Buen Retiro",
    "Caja Municipal Cumbre Alta",
    "Caja Municipal Ladera Verde",
    "Caja Municipal Manantial",
    "Caja Municipal Pampa Nueva",
    "Caja Municipal Puerto Claro",
    "Caja Municipal Quinta Sur",
    "Caja Municipal Río Sereno",
    "Caja Municipal Valle Alto",
    "Caja Municipal Vista Alegre",
)

CAJAS_RURALES: tuple[str, ...] = (
    "Caja Rural Alto Molino",
    "Caja Rural Cañaveral",
    "Caja Rural Chacra Verde",
    "Caja Rural Sembrador",
    "Caja Rural Tierra Nueva",
)

EMPRESAS_CREDITO: tuple[str, ...] = (
    "Empresa de Crédito Buen Camino",
    "Empresa de Crédito Crece Norte",
    "Empresa de Crédito Kuska",
    "Empresa de Crédito Progreso Sur",
)

# (heading label, share of GRAND_TOTAL, entity names, spread, micro).
#
# The share split is invented but Pareto-shaped: banks carry almost all
# the volume, credit companies a rounding error. ``spread`` is the
# volume ratio between the segment leader and its smallest ranked
# member — the knob that decides how concentrated the segment looks.
# ``micro`` is how many of the segment's entities barely report at all;
# they are handed a two-figure annual volume and a mostly-blank row
# instead of a place on the ranked curve.
SEGMENTS: tuple[tuple[str, float, tuple[str, ...], float, int], ...] = (
    ("Banco",              0.900, BANCOS,            4000.0, 0),
    ("Financiera",         0.060, FINANCIERAS,        900.0, 0),
    ("Caja municipal",     0.015, CAJAS_MUNICIPALES,   60.0, 1),
    ("Caja rural",         0.020, CAJAS_RURALES,      200.0, 2),
    ("Empresa de Crédito", 0.005, EMPRESAS_CREDITO,    40.0, 2),
)

# All fictional institution labels, for the cleanup gate to assert
# against — every Empresa entity row must be one of these.
ALL_FICTIONAL_INSTITUTIONS: tuple[str, ...] = (
    BANCOS + FINANCIERAS + CAJAS_MUNICIPALES + CAJAS_RURALES + EMPRESAS_CREDITO
)


# ---------------------------------------------------------------------------
# Regulatory dimension vocabularies
# ---------------------------------------------------------------------------
#
# The product categories and complaint motives of the RR1 report. These
# are the reglamento's code-list — category names a supervisor reads off
# the SUCAVE report, carried at the 80-character width the page's table
# column was laid out for. They label the generated volumes; they are
# not themselves data.

PRODUCTO_LABELS: tuple[str, ...] = (
    'Cuenta de ahorro con tarjeta de débito',
    'Tarjeta de crédito',
    'Transferencias de fondos (interbancarias o intrabancario)',
    'Crédito de consumo',
    'Banca - Seguros (seguros vendidos en canales del sistema financiero)',
    'Atención al público',
    'Cuenta de ahorro sin tarjeta de débito',
    'Otras operaciones, servicios y/o productos (detallar en Reporte de Reclamo N° RR',
    'Cuenta corriente',
    'Servicios varios (cambios, cobranzas, pagos judiciales, pago de planillas, entre',
    'Créditos a pequeñas empresas y microempresas',
    'Crédito hipotecario para vivienda',
    'Seguro de protección de tarjeta (crédito o débito)',
    'Vida individual',
    'Pago de servicios',
    'Transferencias de fondos al extranjero',
    'Cuenta a plazo',
    'Misceláneos',
    'Vehículos',
    'Cuenta CTS',
    'Remesas',
    'Giros',
    'Desgravamen',
    'Multiseguros',
    'Servicio de recaudación',
    'Domiciliario',
    'Títulos valores (cheques, pagarés, entre otros)',
    'Dinero electrónico',
    'Otras garantías (reales y personales)',
    'Inversiones (fondos mutuos, entre otros)',
    'Renta particular',
    'Crédito corporativo, a grandes empresas y a medianas empresas',
    'Microseguros',
    'Carta fianza / fianzas',
    'Asistencia médica',
    'Seguro de Bancos (BBB)',
    'Arrendamiento financiero (leasing)',
    'Arbitraje (compraventa de valores financieros)',
    'Robo y asalto',
    'Accidentes personales',
    'Factoring y/o descuento',
    'Fideicomiso',
    'SOAT',
    'Custodia de valores',
    'Cajas de seguridad',
    'Vida grupo particular',
    'CREDIS',
    'Incendio',
    'Terremoto',
    'Sepelio',
    'Todo riesgo equipo electrónico',
)

MOTIVO_LABELS: tuple[str, ...] = (
    'Operaciones no reconocidas sin abono temporal',
    'Transacciones no procesadas / mal realizadas',
    'Cobros indebidos de intereses, comisiones, gastos y tributos (tales como seguros',
    'Operaciones no reconocidas con abono temporal',
    'Problemas relacionados con cajeros automáticos',
    'Fallas del sistema informático que dificultan operaciones y servicios',
    'Inadecuada o insuficiente información sobre operaciones, productos y servicios',
    'Incumplimiento de claúsulas de los contratos, pólizas, condiciones, acuerdos',
    'Inadecuada atención al usuario - Problemas en la calidad del servicio',
    'Problemas referidos a programas de lealtad',
    'Demoras o incumplimientos de envío de correspondencia',
    'Retenciones indebidas (incluye retenciones judiciales o de cobranza coactiva)',
    'Modificación indebida de las tasas de interés, comisiones u otras condiciones pa',
    'Problemas presentados con la tarjeta de crédito o débito',
    'Errores en la compra-venta de moneda extranjera y aplicación de tipo de cambio',
    'Disconformidad por notificaciones dirigidas a terceras personas',
    'Contratación o cargo indebido de seguros',
    'Reporte indebido en la central de riesgos',
    'Problemas relacionados con el pago anticipado del crédito',
    'No está conforme con las condiciones de la póliza (entre otros: monto de prima, ',
    'Disconformidad con la renovación de la póliza de seguros',
    'Resolución de contrato',
    'Publicidad engañosa o información que induce al error',
    'Problemas relacionados con la página web de la empresa',
    'Error en los datos del usuario registrado en la empresa',
    'Modificaciones contractuales del crédito - Insatisfacción sobre nuevas condicion',
    'Indebida contratación',
    'Otros motivos (detallar en Reporte de Reclamo N° RR2)',
    'Inadecuada o insuficiente información sobre el seguro contratado',
    'Disconformidad con liquidación de deudas vendidas a empresas vinculadas o empres',
    'Entrega de billetes falsos',
    'Errores en la cobranza de primas',
    'Difusión de información sin autorización del usuario',
    'Problemas relacionados a cajeros corresponsales',
    'Modificaciones contractuales del crédito - Otros motivos',
    'Problemas relacionados a garantías',
    'Demora en la rectificación de la información reportada en la central de riesgos',
    'Incumplimiento en la resolución de la póliza de seguros',
    'Liquidaciones erradas de intereses en cuentas de ahorro o depósitos a plazo fijo',
    'Problemas con cheques',
    'Rechazo en la atención del siniestro',
    'Cancelación indebida de la póliza de seguros',
    'Incumplimiento en el plazo de atención de los siniestros y/o coberturas',
    'Modificaciones contractuales del crédito - Insatisfacción por falta de entrega o',
    'Inadecuada asesoría para la gestión de la indemnización del siniestro',
    'Inadecuada asesoría al potencial contratante de seguros y durante la vigencia de',
    'Modif. contractuales del crédito - Insatisfac. por inadecuada información sobre ',
    'Modificaciones contractuales del crédito - Insatisfacción por \xa0problemas para ef',
    'No recibió la póliza, certificado de seguro, endoso o cobertura provisional',
    'Problemas relacionados a programas estatales de crédito para fomento',
    'Incumplimiento del secreto bancario',
    'Demora o incumplimiento en la devolución de documentos valorados / títulos valor',
    'Inadecuada ejecución de garantías otorgadas por la entidad',
    'No está conforme con el monto de la indemnización, valoración del daño, reparaci',
    'Indebida capitalización de intereses moratorios',
    'Exceso de tasas de interés sobre las tasas máximas establecidas por el BCRP',
    'Cierre indebido de cuentas corrientes por girar cheques sin fondos',
    'Deficiencias en el transporte y/o custodia de numerario',
    'Problemas y/o demoras en el otorgamiento y pago de pensión por la aseguradora',
    'No está conforme con el diagnóstico médico (auditor interno de la empresa de seg',
)


# ---------------------------------------------------------------------------
# Volume generation
# ---------------------------------------------------------------------------


def _ranked_shares(n: int, spread: float, rng: random.Random) -> list[float]:
    """Normalised shares over ``n`` ranks, jittered, summing to 1.

    Geometric rather than Zipf. A power law cannot hit both of the
    things that make a complaints table look like a complaints table —
    a leader holding a third of the volume *and* four orders of
    magnitude between the leader and the smallest reporter. Geometric
    decay takes ``spread`` (the leader-to-smallest ratio) directly and
    gets both.

    The jitter is multiplicative and mild, so rank ordering usually
    survives it. The curve should not look like it came off a formula.
    """
    if n == 1:
        return [1.0]
    ratio = spread ** (-1.0 / (n - 1))
    raw = [(ratio ** i) * rng.uniform(0.78, 1.28) for i in range(n)]
    scale = sum(raw)
    return [r / scale for r in raw]


def _spread_over_months(total: int, rng: random.Random) -> list[int]:
    """Split an annual total across twelve months, summing exactly.

    Seasonal curve plus per-month noise, allocated by largest remainder
    so no count is lost or invented in the rounding.
    """
    weights = [s * rng.uniform(0.88, 1.12) for s in SEASONAL]
    scale = sum(weights)
    exact = [total * w / scale for w in weights]
    floors = [int(e) for e in exact]
    shortfall = total - sum(floors)
    # Hand the remaining units to the months with the largest fractional
    # parts — standard largest-remainder apportionment.
    order = sorted(range(12), key=lambda i: exact[i] - floors[i], reverse=True)
    for i in order[:shortfall]:
        floors[i] += 1
    return floors


def _sparse_over_months(total: int, rng: random.Random) -> list[int | None]:
    """Apportion a two-figure annual total across a few months.

    Most months come back blank. The ones that report share the total
    between them, and one of them landing on zero is a legitimate
    outcome — a month that reported nothing is not the same fact as a
    month that did not report, and the workbench renders them
    differently.
    """
    reporting = min(12, max(1, round(total ** 0.6)))
    picked = sorted(rng.sample(range(12), reporting))
    weights = [rng.random() + 0.05 for _ in picked]
    scale = sum(weights)
    exact = [total * w / scale for w in weights]
    counts = [int(e) for e in exact]
    order = sorted(range(reporting), key=lambda i: exact[i] - counts[i],
                   reverse=True)
    for i in order[:total - sum(counts)]:
        counts[i] += 1
    values: list[int | None] = [None] * 12
    for month, count in zip(picked, counts):
        values[month] = count
    return values


def _row(label: str, target: int, rng: random.Random) -> dict:
    """One fixture row: label, twelve months, total equal to their sum."""
    if target < SPARSE_BELOW:
        values: list[int | None] = _sparse_over_months(target, rng)
    else:
        values = list(_spread_over_months(target, rng))
    return {
        "label": label,
        "values": values,
        "total": sum(v for v in values if v is not None),
    }


def _dimension(labels: tuple[str, ...], spread: float,
               rng: random.Random) -> list[dict]:
    """A flat sheet — Producto or Motivo — sorted by total, descending.

    The tail reaches single digits on purpose. A long tail of categories
    used once or twice a year is a real feature of the report, and it is
    why the workbench's heatmap needs a compressed colour scale.
    """
    shares = _ranked_shares(len(labels), spread, rng)
    rows = [
        _row(label, max(1, round(GRAND_TOTAL * share)), rng)
        for label, share in zip(labels, shares)
    ]
    rows.sort(key=lambda r: r["total"], reverse=True)
    return rows


def _empresa_sheet(rng: random.Random) -> list[dict]:
    """The Empresa sheet, hierarchy intact.

    Each segment heading row is the exact month-wise sum of the entity
    rows beneath it, blanks counted as zero. The page's totals column
    and its stacked-area chart both rely on that holding, so the
    subtotal is computed from the children rather than drawn.

    Entities keep the alphabetical order the report lists them in, and
    which entity gets which rank on the volume curve is drawn — so the
    table reads like a register sorted by name rather than a ranking,
    which is what the report actually is.
    """
    rows: list[dict] = []
    for heading, share, names, spread, micro in SEGMENTS:
        segment_total = round(GRAND_TOTAL * share)
        # Who barely reports, and who sits where on the curve, are both
        # draws rather than positions in the alphabet.
        assignment = list(names)
        rng.shuffle(assignment)
        micro_names, ranked_names = assignment[:micro], assignment[micro:]
        shares = _ranked_shares(len(ranked_names), spread, rng)
        children = [
            _row(name, max(1, round(segment_total * s)), rng)
            for name, s in zip(ranked_names, shares)
        ]
        children.extend(
            _row(name, rng.randint(4, SPARSE_BELOW - 12), rng)
            for name in micro_names
        )
        children.sort(key=lambda r: names.index(r["label"]))
        subtotal = [
            sum((child["values"][m] or 0) for child in children)
            for m in range(12)
        ]
        rows.append({
            "label": heading,
            "values": subtotal,
            "total": sum(subtotal),
        })
        rows.extend(children)
    return rows


def build(seed: int, generated_at: str) -> dict:
    return {
        "source": "synthetic — generated, not extracted",
        "synthetic": True,
        "generator": "scripts/build_rr1_fixture.py",
        "seed": seed,
        "generated_at": generated_at,
        "sheets": {
            "Empresa": {
                "label_col": "Tipo Entidad y Entidad",
                "months": list(MONTHS),
                "rows": _empresa_sheet(random.Random(seed)),
            },
            "Producto": {
                "label_col": "Producto",
                "months": list(MONTHS),
                "rows": _dimension(PRODUCTO_LABELS, 1_000_000.0,
                                   random.Random(seed + 1)),
            },
            "Motivo": {
                "label_col": "Motivo",
                "months": list(MONTHS),
                "rows": _dimension(MOTIVO_LABELS, 1_500_000.0,
                                   random.Random(seed + 2)),
            },
        },
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seed", type=int, default=DEFAULT_SEED,
                   help=f"generation seed (default {DEFAULT_SEED})")
    p.add_argument("--generated-at", type=str, default=GENERATED_AT,
                   help="ISO timestamp stamped into the fixture; fixed by "
                        "default so regeneration is byte-stable")
    p.add_argument("--out", type=Path, default=OUT,
                   help="output path (default app/src/lib/rr1-2025.json)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    out = build(args.seed, args.generated_at)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"wrote {args.out}  (synthetic, seed={args.seed})")
    for name, sheet in out["sheets"].items():
        grand = (
            sum(r["total"] for r in sheet["rows"]
                if r["label"] in {s[0] for s in SEGMENTS})
            if name == "Empresa"
            else sum(r["total"] for r in sheet["rows"])
        )
        print(f"  {name}: {len(sheet['rows'])} rows × "
              f"{len(sheet['months'])} months, total {grand:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
