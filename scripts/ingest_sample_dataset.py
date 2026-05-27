#!/usr/bin/env python
"""Ingest the real SBS Annex 1-A sample into the sandbox API.

P11 demo-ready overlay. Drives ``POST /v1/sandbox/complaints/granular``
with the same auth chain ``institution_push_demo.py`` already proves
(OAuth + mTLS / dev-XFCC + HMAC + Idempotency-Key), but the payload is
sourced from the real-shape spreadsheet the SBS team shared:

    data/sbs_sample/SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx

Two sheets, 100 rows each, deliberately inconsistent surface forms:

  LARGE_ENTITIES  Banco1 / Banco2 — mixed-case taxonomy, 8-digit DNI
                  → Tier 1 institution (BANCO_DEMO_001 / SBS-001234)
  SMALL_ENTITIES  Banco3 / Banco4 / Caja… — ALL-CAPS taxonomy, 12-digit ID
                  → Tier 2 institution (COOPAC_DEMO_002 / SBS-005678)

The point of the dataset is the taxonomy-harmonization story: the same
logical value (e.g. ``pagina_web``) arrives as ``"Página web de la
empresa"`` from Banco1 and ``"PAG. WEB DE LA EMPRESA"`` from Banco3.
The sandbox endpoint runs the taxonomy-normalization step (P11
demo-ready overlay) so both submissions converge on the same canonical
code. Rows with surface forms the dictionary does not recognise are
accepted with ``flag_unknown_taxonomy=true`` rather than rejected.

PII safety: every printed trace masks DNI / phone / email / account /
proper-name tokens before stdout. Raw values are sent on the wire —
the endpoint expects them; the SBS side redacts them on receipt.

This script is sandbox infrastructure. The institution data is real
but synthetic-shaped; the wire-level connection, auth, redaction, DQ,
audit, and SSE behaviour is real.
"""

from __future__ import annotations

import argparse
import datetime as dt
import secrets
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Reuse the auth-chain helpers from the existing institution sender so
# this script does not duplicate OAuth / HMAC / mTLS logic.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from institution_push_demo import (  # noqa: E402
    PROFILES,
    Profile,
    _dev_proxy_headers,
    _fetch_token,
    _make_client,
    _post_complaint,
    mask_json_for_print,
    mask_pii,
)

# Lazy import openpyxl below to give a clearer error message if the
# venv doesn't have it.
DEFAULT_SOURCE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "sbs_sample"
    / "SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx"
)


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------


# Order matches the xlsx header row. The script accesses cells by index
# so a column re-ordering in the source file would break this — adjust
# the indices below if the spreadsheet schema drifts.
_COL_INDEX = {
    "COD_REC": 0,
    "TID_CLI": 1,
    "NRO_CLI": 2,
    "NCL_CLI": 3,
    "COD_CLI": 4,
    "FEC_ING": 5,
    "CNL_ING": 6,
    "CNL_OPE": 7,
    "FEC_AMP": 8,
    "CNL_AMP": 9,
    "FEC_RES": 10,
    "CNL_PAC": 11,
    "UBI_REC": 12,
    "PRD_SBS": 13,
    "MOT_SBS": 14,
    "SUB_SBS": 15,
    "DET_REC": 16,
    "TIP_RES": 17,
    "DET_RES": 18,
    "PRD_EMP": 19,
    "EST_REC": 20,
    "COD_PRV": 21,
    "BAN_SEG": 22,
    "PRD_SBS_SEG": 23,
    "MOT_SBS_SEG": 24,
    "SUB_SBS_SEG": 25,
    "MNT_PEN_REC": 26,
    "EMPRESA": 27,
}


# Map EMPRESA → (profile-name, sheet-tier). Banco1/Banco2 are the
# LARGE_ENTITIES Tier 1 stand-ins; Banco3/Banco4/Caja* are the
# SMALL_ENTITIES Tier 2 stand-ins. Unknown EMPRESA values fall back to
# the per-sheet default.
_EMPRESA_TO_PROFILE: dict[str, str] = {
    "banco1": "banco-tier1",
    "banco2": "banco-tier1",
    "banco3": "coopac-tier2",
    "banco4": "coopac-tier2",
}


def _empresa_to_profile(empresa: str | None, sheet_default: str) -> str:
    if not empresa:
        return sheet_default
    key = empresa.strip().lower()
    if key in _EMPRESA_TO_PROFILE:
        return _EMPRESA_TO_PROFILE[key]
    if key.startswith("caja") or key.startswith("financiera") or key.startswith(
        "coopac"
    ):
        return "coopac-tier2"
    return sheet_default


def _str(value: Any) -> str | None:
    """Coerce an xlsx cell value to a trimmed string, or None when empty."""

    if value is None:
        return None
    if isinstance(value, str):
        out = value.strip()
        return out or None
    if isinstance(value, (int, float)):
        return f"{value}"
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value).strip() or None


def _iso_date(value: Any) -> str | None:
    """Return an ISO 8601 date (no time) from a cell, or None."""

    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return None
    # Try YYYY-MM-DD or DD/MM/YYYY heuristics.
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s


@dataclass
class RowPayload:
    """One xlsx row mapped to a sandbox submission body + profile."""

    profile_name: str
    body: dict[str, Any]
    empresa: str
    cod_rec: str


def row_to_payload(row: tuple, sheet_default_profile: str) -> RowPayload | None:
    """Map an xlsx row to a DemoSubmissionRequest body + institution profile.

    Returns ``None`` when the row is unusable (no narrative / no
    institution complaint id). The caller logs and skips.
    """

    cod_rec = _str(row[_COL_INDEX["COD_REC"]])
    det_rec = _str(row[_COL_INDEX["DET_REC"]])
    empresa = _str(row[_COL_INDEX["EMPRESA"]]) or ""
    if not cod_rec or not det_rec:
        return None

    profile_name = _empresa_to_profile(empresa, sheet_default_profile)
    profile = PROFILES[profile_name]

    body: dict[str, Any] = {
        "institution_id": profile.institution_id,
        "institution_name": profile.institution_display,
        "institution_complaint_id": cod_rec,
        "client_submission_id": f"ingest-{uuid.uuid4().hex[:12]}",
        "tid_cli": _str(row[_COL_INDEX["TID_CLI"]]),
        "nro_cli": _str(row[_COL_INDEX["NRO_CLI"]]),
        "ncl_cli": _str(row[_COL_INDEX["NCL_CLI"]]),
        "cod_cli": _str(row[_COL_INDEX["COD_CLI"]]),
        "received_at": _iso_date(row[_COL_INDEX["FEC_ING"]]),
        "channel_in": _str(row[_COL_INDEX["CNL_ING"]]),
        "channel_operation": _str(row[_COL_INDEX["CNL_OPE"]]),
        "fecha_comunicacion_ampliacion": _iso_date(row[_COL_INDEX["FEC_AMP"]]),
        "canal_comunicacion_ampliacion": _str(row[_COL_INDEX["CNL_AMP"]]),
        "fecha_resolucion": _iso_date(row[_COL_INDEX["FEC_RES"]]),
        "canal_pago_cliente": _str(row[_COL_INDEX["CNL_PAC"]]),
        "ubigeo": _str(row[_COL_INDEX["UBI_REC"]]),
        "product": _str(row[_COL_INDEX["PRD_SBS"]]),
        "motive": _str(row[_COL_INDEX["MOT_SBS"]]),
        "submotive": _str(row[_COL_INDEX["SUB_SBS"]]),
        "narrative": det_rec,
        "tipo_resolucion": _str(row[_COL_INDEX["TIP_RES"]]),
        "response_detail": _str(row[_COL_INDEX["DET_RES"]]),
        "producto_empresa": _str(row[_COL_INDEX["PRD_EMP"]]),
        "status": _str(row[_COL_INDEX["EST_REC"]]),
        "previous_complaint_id": _str(row[_COL_INDEX["COD_PRV"]]),
        "bancaseguros": _str(row[_COL_INDEX["BAN_SEG"]]),
        "producto_bancaseguros": _str(row[_COL_INDEX["PRD_SBS_SEG"]]),
        "motivo_bancaseguros": _str(row[_COL_INDEX["MOT_SBS_SEG"]]),
        "submotivo_bancaseguros": _str(row[_COL_INDEX["SUB_SBS_SEG"]]),
        "monto_pendiente": _str(row[_COL_INDEX["MNT_PEN_REC"]]),
        "demo_scenario": "real-sample-ingestion",
        # Optional supervisor severity isn't carried in the xlsx; let
        # the orchestrator default to MEDIUM.
    }
    return RowPayload(
        profile_name=profile_name,
        body={k: v for k, v in body.items() if v is not None},
        empresa=empresa,
        cod_rec=cod_rec,
    )


# ---------------------------------------------------------------------------
# Submission loop
# ---------------------------------------------------------------------------


@dataclass
class SubmissionResult:
    cod_rec: str
    empresa: str
    profile_name: str
    status_code: int
    body: dict[str, Any] | None
    error: str | None = None

    @property
    def receipt_status(self) -> str | None:
        return self.body.get("status") if isinstance(self.body, dict) else None

    @property
    def complaint_id(self) -> str | None:
        return (
            self.body.get("complaint_id") if isinstance(self.body, dict) else None
        )


def submit_one(
    *,
    api_base: str,
    profile: Profile,
    body: dict[str, Any],
    insecure_skip_mtls: bool,
) -> SubmissionResult:
    """Run one OAuth → signed POST cycle for a single row.

    Each row uses a fresh Idempotency-Key so retries within a run don't
    collide with the sandbox's idempotency cache. Errors are caught and
    returned as a ``SubmissionResult`` with ``error`` set so the
    ingestion loop can continue.
    """

    cod_rec = body.get("institution_complaint_id", "?")
    empresa = body.get("institution_name", "?")
    idem_key = f"ingest-{cod_rec}-{secrets.token_hex(6)}"
    try:
        client = _make_client(
            api_base=api_base,
            profile=profile,
            insecure_skip_mtls=insecure_skip_mtls,
        )
        dev_proxy_headers = _dev_proxy_headers(
            profile=profile, insecure_skip_mtls=insecure_skip_mtls
        )
        try:
            token = _fetch_token(
                client,
                api_base=api_base,
                profile=profile,
                dev_proxy_headers=dev_proxy_headers,
            )
            resp, _ts, _sig = _post_complaint(
                client,
                api_base=api_base,
                profile=profile,
                token=token,
                body_dict=body,
                idempotency_key=idem_key,
                dev_proxy_headers=dev_proxy_headers,
            )
        finally:
            client.close()
        try:
            payload = resp.json()
        except ValueError:
            payload = {"_raw_text": resp.text[:1000]}
        return SubmissionResult(
            cod_rec=str(cod_rec),
            empresa=str(empresa),
            profile_name=profile.name,
            status_code=resp.status_code,
            body=payload,
        )
    except SystemExit as exc:
        return SubmissionResult(
            cod_rec=str(cod_rec),
            empresa=str(empresa),
            profile_name=profile.name,
            status_code=0,
            body=None,
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        return SubmissionResult(
            cod_rec=str(cod_rec),
            empresa=str(empresa),
            profile_name=profile.name,
            status_code=0,
            body=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def _iter_rows(
    source: Path, sheet: str
) -> Iterable[tuple[int, tuple]]:
    """Yield (1-based row index, cell tuple) for the named sheet."""

    try:
        import openpyxl
    except ImportError as exc:
        raise SystemExit(
            "openpyxl is required: install with `uv pip install openpyxl`"
        ) from exc

    wb = openpyxl.load_workbook(source, data_only=True, read_only=True)
    if sheet not in wb.sheetnames:
        raise SystemExit(
            f"sheet {sheet!r} not found in {source.name}; available: "
            f"{wb.sheetnames}"
        )
    ws = wb[sheet]
    for idx, raw in enumerate(ws.iter_rows(values_only=True)):
        if idx == 0:
            continue  # header
        if all(cell is None for cell in raw):
            continue
        yield idx, raw
    wb.close()


def _summary_line(result: SubmissionResult, row_idx: int, total: int) -> str:
    body = result.body or {}
    receipt_status = result.receipt_status or "<unknown>"
    if result.error:
        return (
            f"[{row_idx}/{total}] EMPRESA={result.empresa} "
            f"COD_REC={result.cod_rec} → ERROR {result.error}"
        )
    dq_errors = len((body.get("data_quality") or {}).get("errors", []))
    dq_warnings = len((body.get("data_quality") or {}).get("warnings", []))
    annex_errors = sum(
        1
        for r in (body.get("annex_1a_data_quality") or {}).get("results", [])
        if r.get("severity") == "error"
    )
    annex_warnings = sum(
        1
        for r in (body.get("annex_1a_data_quality") or {}).get("results", [])
        if r.get("severity") == "warning"
    )
    taxonomy_count = len(body.get("taxonomy_normalizations") or [])
    flag_unknown = body.get("flag_unknown_taxonomy", False)
    complaint_id = result.complaint_id or "<none>"
    return (
        f"[{row_idx}/{total}] EMPRESA={result.empresa} "
        f"COD_REC={result.cod_rec} → {complaint_id} {receipt_status} "
        f"(HTTP {result.status_code}; "
        f"dq=err {dq_errors}/warn {dq_warnings}; "
        f"annex=err {annex_errors}/warn {annex_warnings}; "
        f"taxonomy normalized {taxonomy_count}"
        f"{', unknown!' if flag_unknown else ''})"
    )


def _aggregate(results: list[SubmissionResult]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": len(results),
        "accepted": 0,
        "accepted_with_warnings": 0,
        "rejected": 0,
        "duplicate": 0,
        "error": 0,
        "by_profile": {},
    }
    for r in results:
        by_profile = summary["by_profile"].setdefault(
            r.profile_name, {"total": 0, "accepted": 0, "rejected": 0}
        )
        by_profile["total"] += 1
        if r.error or r.status_code >= 400:
            summary["error"] += 1
            continue
        status = r.receipt_status or ""
        if status == "accepted":
            summary["accepted"] += 1
            by_profile["accepted"] += 1
        elif status == "accepted_with_warnings":
            summary["accepted_with_warnings"] += 1
            by_profile["accepted"] += 1
        elif status == "rejected":
            summary["rejected"] += 1
            by_profile["rejected"] += 1
        elif status == "duplicate":
            summary["duplicate"] += 1
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest the real SBS Annex 1-A sample into the sandbox API."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Path to SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx (default: data/sbs_sample/).",
    )
    parser.add_argument(
        "--sheet",
        choices=("large", "small", "both"),
        default="both",
        help="Which sheet(s) to ingest. Default: both.",
    )
    parser.add_argument(
        "--mode",
        choices=("backfill", "live-stream"),
        required=True,
        help=(
            "backfill: send as fast as the API allows (API rate-limits). "
            "live-stream: pace submissions for visible cockpit updates."
        ),
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=0.5,
        help=(
            "Submissions per second in live-stream mode (default 0.5 = 1 every "
            "2 seconds). Ignored in backfill mode."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows per sheet (default: no limit).",
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000/v1",
        help="Base URL of the sandbox API. Default: http://localhost:8000/v1.",
    )
    parser.add_argument(
        "--insecure-skip-mtls",
        action="store_true",
        help=(
            "Skip mTLS at the TLS layer; send a dev X-Forwarded-Client-Cert "
            "header instead (passthrough for the sandbox sender). Required "
            "when the API runs in SBS_API_MTLS_MODE=proxy over plain HTTP."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-row trace output; print only the summary.",
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"ERROR: source file not found: {args.source}", file=sys.stderr)
        return 2

    sheets: list[tuple[str, str, str]] = []
    if args.sheet in ("large", "both"):
        sheets.append(("LARGE_ENTITIES", "banco-tier1", "Tier 1 NRT"))
    if args.sheet in ("small", "both"):
        sheets.append(("SMALL_ENTITIES", "coopac-tier2", "Tier 2 batch"))

    pace = 1.0 / args.rate if args.mode == "live-stream" and args.rate > 0 else 0.0
    all_results: list[SubmissionResult] = []

    for sheet_name, default_profile, tier_label in sheets:
        print(
            f"\n=== Sheet {sheet_name} ({tier_label} → default profile "
            f"{default_profile}) ===",
            flush=True,
        )
        rows = list(_iter_rows(args.source, sheet_name))
        if args.limit is not None:
            rows = rows[: args.limit]
        total = len(rows)
        for ordinal, (_row_idx, cells) in enumerate(rows, start=1):
            payload = row_to_payload(cells, default_profile)
            if payload is None:
                if not args.quiet:
                    print(
                        f"[{ordinal}/{total}] SKIP — empty narrative or "
                        "missing COD_REC",
                        flush=True,
                    )
                continue
            profile = PROFILES[payload.profile_name]

            t0 = time.monotonic()
            result = submit_one(
                api_base=args.api_base,
                profile=profile,
                body=payload.body,
                insecure_skip_mtls=args.insecure_skip_mtls,
            )
            all_results.append(result)
            if not args.quiet:
                print(_summary_line(result, ordinal, total), flush=True)
                # Print a single masked-snapshot of the response so an
                # operator can see redaction worked. Disabled in --quiet.
                if result.body and ordinal == 1:
                    masked = mask_json_for_print(
                        {
                            k: result.body.get(k)
                            for k in (
                                "complaint_id",
                                "status",
                                "redaction_policy_version",
                                "data_quality_policy_version",
                                "taxonomy_normalizations",
                                "flag_unknown_taxonomy",
                            )
                            if k in result.body
                        }
                    )
                    print(f"    preview: {masked}", flush=True)

            if pace > 0:
                elapsed = time.monotonic() - t0
                remaining = pace - elapsed
                if remaining > 0:
                    time.sleep(remaining)

    # Summary -------------------------------------------------------------
    summary = _aggregate(all_results)
    print("\n=== Summary ===")
    print(f"  total submitted : {summary['total']}")
    print(
        f"  accepted        : {summary['accepted']} "
        f"+ {summary['accepted_with_warnings']} accepted_with_warnings"
    )
    print(f"  rejected        : {summary['rejected']}")
    print(f"  duplicate       : {summary['duplicate']}")
    print(f"  errors          : {summary['error']}")
    for profile_name, counts in summary["by_profile"].items():
        print(
            f"  profile {profile_name}: total={counts['total']} "
            f"accepted={counts['accepted']} rejected={counts['rejected']}"
        )

    return 0 if summary["error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
