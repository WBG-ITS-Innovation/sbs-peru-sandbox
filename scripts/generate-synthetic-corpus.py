#!/usr/bin/env python
"""Generate the Tier-2-fidelity synthetic complaint corpus (ADR 0036).

Per-institution CSV + matching manifest JSON. Deterministic given the
``--seed`` flag so the May 25 demo regenerates byte-identical output
on any machine that has the repo + the deterministic seed.

Usage:

    uv run python scripts/generate-synthetic-corpus.py \\
        --out data/synthetic-corpus \\
        --rows-per-institution 3333 \\
        --seed 2026

    # Golden sample (committed to data/synthetic-corpus-golden/):
    uv run python scripts/generate-synthetic-corpus.py \\
        --out data/synthetic-corpus-golden \\
        --rows-per-institution 200 \\
        --seed 2026 \\
        --golden

The ``--distribution-profile`` flag defaults to ``uniform`` (Tier 2
fidelity). ``--distribution-profile pattern-cluster`` is a Prompt 11
augmentation; for now it raises NotImplementedError.

Tier 2 fidelity per ADR 0036:
- Structurally valid Anexo 1-A.
- Peruvian Spanish narratives via template substitution.
- Log-normal monetary amounts over the Peruvian banking range.
- Format-valid synthetic phone numbers (9XXXXXXXX) and document IDs
  (DNI 8-digit; RUC 11-digit with valid checksum).
- Random distribution over a 90-day window ending today.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import yaml

# Make sbs_api importable so we can pull the canonical enum values.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))

from sbs_api.models.anexo_1a import (  # noqa: E402
    Channel,
    ComplainantAgeRange,
    ComplainantDocType,
    MotivoCode,
    ProductCategory,
    ResolutionStatus,
    Severity,
    SubmissionMethod,
)

TEMPLATES_FILE = REPO_ROOT / "data" / "synthetic-corpus-templates.yaml"

# Demo institutions and their SBS-Nnnnnn ids.
INSTITUTIONS: tuple[tuple[str, str, str], ...] = (
    ("SBS-001234", "BANCO_DEMO_001",      "BCO"),
    ("SBS-005678", "COOPAC_DEMO_002",     "COP"),
    ("SBS-009012", "FINANCIERA_DEMO_003", "FIN"),
)

# INEI ubigeo subset for Lima/Callao/Arequipa (six digits each).
UBIGEOS: tuple[str, ...] = (
    "150101", "150102", "150107", "150111", "150115",
    "150133", "140101", "070101", "040101", "040106",
)

# Spanish prose channel mapping for narrative substitution.
CHANNEL_PROSE = {
    Channel.AGENCIA.value: "agencia",
    Channel.WEB.value: "la web",
    Channel.APP_MOVIL.value: "la app móvil",
    Channel.TELEFONO.value: "la línea telefónica",
    Channel.CORREO.value: "correo electrónico",
    Channel.PRESENCIAL_SBS.value: "presencial en SBS",
    Channel.OTRO.value: "otro canal",
}
PRODUCT_PROSE = {
    ProductCategory.DEPOSITOS.value: "cuenta de depósitos",
    ProductCategory.CREDITOS.value: "crédito",
    ProductCategory.TARJETA_CREDITO.value: "tarjeta de crédito",
    ProductCategory.TARJETA_DEBITO.value: "tarjeta de débito",
    ProductCategory.SEGUROS.value: "seguro",
    ProductCategory.AFP_PENSIONES.value: "fondo de pensiones",
    ProductCategory.COOPAC.value: "cuenta de cooperativa",
    ProductCategory.OTRO.value: "producto bancario",
}

# Pareto-shaped channel mix biased toward digital channels for the
# Tier-2 fidelity baseline.
CHANNEL_WEIGHTS: dict[str, float] = {
    Channel.APP_MOVIL.value: 0.35,
    Channel.WEB.value: 0.20,
    Channel.AGENCIA.value: 0.20,
    Channel.TELEFONO.value: 0.15,
    Channel.CORREO.value: 0.07,
    Channel.PRESENCIAL_SBS.value: 0.02,
    Channel.OTRO.value: 0.01,
}
PRODUCT_WEIGHTS: dict[str, float] = {
    ProductCategory.TARJETA_CREDITO.value: 0.28,
    ProductCategory.CREDITOS.value: 0.22,
    ProductCategory.DEPOSITOS.value: 0.17,
    ProductCategory.TARJETA_DEBITO.value: 0.13,
    ProductCategory.SEGUROS.value: 0.08,
    ProductCategory.AFP_PENSIONES.value: 0.07,
    ProductCategory.COOPAC.value: 0.03,
    ProductCategory.OTRO.value: 0.02,
}


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    values = list(weights.values())
    return rng.choices(keys, weights=values, k=1)[0]


def _ruc_with_valid_checksum(rng: random.Random) -> str:
    """Generate an 11-digit RUC with the Sunat module-11 checksum.

    The base 10 digits are random; the 11th is the check digit. RUCs
    start with the entity-type digit (1, 2, or 6 for legal persons).
    """

    multipliers = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    base = [rng.choice([1, 2, 6])] + [rng.randint(0, 9) for _ in range(9)]
    s = sum(d * m for d, m in zip(base, multipliers))
    check = 11 - (s % 11)
    if check == 11:
        check = 0
    elif check == 10:
        check = 1
    return "".join(str(d) for d in base) + str(check)


def _dni(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(8))


def _phone(rng: random.Random) -> str:
    return "9" + "".join(str(rng.randint(0, 9)) for _ in range(8))


def _monetary_amount(rng: random.Random) -> float:
    """Log-normal over a typical Peruvian banking complaint range.

    Mode ≈ S/ 350, long tail to ~ S/ 200,000.
    """

    mu = math.log(350)
    sigma = 1.1
    val = rng.lognormvariate(mu, sigma)
    # Clip and round to centavos.
    val = max(10.0, min(val, 200_000.0))
    return round(val, 2)


def _received_date(rng: random.Random, ref: date) -> date:
    days = rng.randint(0, 89)
    return ref - timedelta(days=days)


def _make_row(
    rng: random.Random,
    *,
    institution_id: str,
    prefix: str,
    sequence: int,
    templates: Sequence[str],
    display_name: str,
    today: date,
) -> dict[str, str]:
    product = _weighted_choice(rng, PRODUCT_WEIGHTS)
    channel = _weighted_choice(rng, CHANNEL_WEIGHTS)
    doc_type = rng.choice(
        [
            ComplainantDocType.DNI.value,
            ComplainantDocType.DNI.value,
            ComplainantDocType.CE.value,
            ComplainantDocType.RUC.value,
            ComplainantDocType.PASAPORTE.value,
        ]
    )
    motivo = rng.choice(
        [
            MotivoCode.COBRO_INDEBIDO.value,
            MotivoCode.OPERACION_NO_RECONOCIDA.value,
            MotivoCode.DEMORA_ATENCION.value,
            MotivoCode.INCUMPLIMIENTO_CONTRATO.value,
            MotivoCode.CALIDAD_SERVICIO.value,
        ]
    )
    severity = rng.choice(
        [
            Severity.LOW.value,
            Severity.MEDIUM.value,
            Severity.HIGH.value,
            Severity.HIGH.value,  # weight HIGH slightly higher
            Severity.CRITICAL.value,
        ]
    )
    age_range = rng.choice(
        [
            ComplainantAgeRange.R_25_34.value,
            ComplainantAgeRange.R_35_44.value,
            ComplainantAgeRange.R_45_54.value,
            ComplainantAgeRange.R_55_64.value,
            ComplainantAgeRange.UNDER_25.value,
            ComplainantAgeRange.OVER_64.value,
        ]
    )
    submission_method = rng.choice(
        [
            SubmissionMethod.APP_MOVIL.value,
            SubmissionMethod.WEB.value,
            SubmissionMethod.AGENCIA.value,
            SubmissionMethod.POS.value,
            SubmissionMethod.CAJERO.value,
        ]
    )

    amount = _monetary_amount(rng)
    received = _received_date(rng, today)
    narrative_template = rng.choice(list(templates))
    narrative = narrative_template.format(
        amount=f"{amount:.2f}",
        product=PRODUCT_PROSE.get(product, "producto"),
        date=received.isoformat(),
        channel=CHANNEL_PROSE.get(channel, "el canal"),
        entity=display_name,
    )

    complaint_id = f"{prefix}-{received.year:04d}-{sequence:07d}"

    return {
        "complaint_id": complaint_id,
        "institution_id": institution_id,
        "received_date": received.isoformat(),
        "complainant_doc_type": doc_type,
        "product_category": product,
        "channel": channel,
        "motivo_code": motivo,
        "severity": severity,
        "description_text": narrative,
        "description_language": "es",
        "complainant_age_range": age_range,
        "complainant_district": rng.choice(UBIGEOS),
        "submission_method": submission_method,
        "original_reference_id": "",
        "resolution_status": ResolutionStatus.PENDIENTE.value,
    }


def _write_csv(rows: list[dict[str, str]], path: Path) -> str:
    """Write deterministic CSV with proper quoting. Returns SHA-256 hex.

    Uses :mod:`csv` so narratives carrying commas are quoted correctly.
    Newline is LF (csv module's default on POSIX) and the deterministic
    dialect ensures byte-stable output across machines.
    """

    import csv

    fields = list(rows[0].keys())
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf,
        fieldnames=fields,
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    payload = buf.getvalue().encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _write_manifest(
    *,
    rows: int,
    sha256: str,
    out_path: Path,
    reporting_period_start: date,
    reporting_period_end: date,
    schema_version: str,
) -> None:
    manifest = {
        "reporting_period_start": reporting_period_start.isoformat(),
        "reporting_period_end": reporting_period_end.isoformat(),
        "row_count_submitted": rows,
        "checksum_sha256": sha256,
        "schema_version": schema_version,
    }
    out_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def generate(
    *,
    out_dir: Path,
    rows_per_institution: int,
    seed: int,
    distribution_profile: str = "uniform",
    today: date | None = None,
) -> dict[str, Any]:
    """Produce per-institution CSV + manifest in ``out_dir``."""

    if distribution_profile != "uniform":
        raise NotImplementedError(
            f"distribution_profile={distribution_profile!r} is a Prompt 11 "
            "augmentation; uniform is the only profile available today."
        )

    today = today or datetime.now(timezone.utc).date()
    period_end = today
    period_start = today - timedelta(days=89)
    schema_version = "v0.1.0"

    templates = yaml.safe_load(TEMPLATES_FILE.read_text(encoding="utf-8"))[
        "templates"
    ]

    summary: dict[str, dict[str, Any]] = {}
    for inst_idx, (institution_id, display, prefix) in enumerate(INSTITUTIONS):
        # Deterministic per-institution stream: the institution index
        # is mixed into the seed so the same flag values produce the
        # same rows on every machine.
        rng = random.Random(f"{seed}:{institution_id}".encode("utf-8"))
        rows: list[dict[str, str]] = []
        for i in range(rows_per_institution):
            rows.append(
                _make_row(
                    rng,
                    institution_id=institution_id,
                    prefix=prefix,
                    sequence=i + 1,
                    templates=templates,
                    display_name=display,
                    today=today,
                )
            )
        csv_path = out_dir / institution_id / f"{institution_id}.csv"
        manifest_path = out_dir / institution_id / f"{institution_id}.manifest.json"
        sha = _write_csv(rows, csv_path)
        _write_manifest(
            rows=len(rows),
            sha256=sha,
            out_path=manifest_path,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            schema_version=schema_version,
        )
        summary[institution_id] = {
            "csv": str(csv_path),
            "manifest": str(manifest_path),
            "sha256": sha,
            "rows": len(rows),
        }
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("data/synthetic-corpus"),
        help="Output directory (one subdir per institution).",
    )
    p.add_argument(
        "--rows-per-institution",
        type=int,
        default=3333,
        help="Rows per institution. Default 3333 (~10k total).",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="Deterministic seed. Default 2026 (the demo year).",
    )
    p.add_argument(
        "--distribution-profile",
        choices=["uniform", "pattern-cluster"],
        default="uniform",
        help="Tier 2 = uniform. pattern-cluster is a Prompt 11 hook.",
    )
    p.add_argument(
        "--golden",
        action="store_true",
        help=(
            "Convenience flag: writes 200 rows per institution to "
            "data/synthetic-corpus-golden/ with a fixed today "
            "(2026-05-20). Overrides --out, --rows-per-institution, "
            "and --today."
        ),
    )
    p.add_argument(
        "--today",
        type=str,
        default=None,
        help=(
            "Anchor the 90-day window's right edge to this ISO date "
            "(YYYY-MM-DD) instead of the wall clock. Required for "
            "byte-stable regeneration."
        ),
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.golden:
        out = REPO_ROOT / "data" / "synthetic-corpus-golden"
        rows = 200
        today = date(2026, 5, 20)
    else:
        out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
        rows = args.rows_per_institution
        today = (
            date.fromisoformat(args.today)
            if args.today is not None
            else None
        )

    summary = generate(
        out_dir=out,
        rows_per_institution=rows,
        seed=args.seed,
        distribution_profile=args.distribution_profile,
        today=today,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
