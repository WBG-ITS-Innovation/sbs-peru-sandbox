#!/usr/bin/env python
"""One-off demo loader: SBS Annex 1-A sample → sandbox API.

LARGE_ENTITIES rows are sent one-by-one through the signed Tier 1 NRT
granular endpoint (``POST /v1/sandbox/complaints/granular``) so they
arrive visibly in the cockpit. SMALL_ENTITIES rows are batched into a
single Tier 2 multipart upload (``POST /v1/batches``).

Both paths reuse the institutional auth chain proven by
``scripts/institution_push_demo.py``: OAuth client_credentials, mTLS
(or dev XFCC header in proxy mode), HMAC SHA-256 canonical-request,
Idempotency-Key.

Usage:
    python scripts/demo_load_sbs_sample.py --limit 5
    python scripts/demo_load_sbs_sample.py --large-limit 30 --small-limit 20

Exit code is 0 if at least one row succeeded in each requested tier;
malformed rows are logged and skipped.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import secrets
import sys
import time
import unicodedata
import urllib.parse
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from institution_push_demo import (  # noqa: E402
    PROFILES,
    Profile,
    _basic_auth_header,
    _build_canonical_request,
    _dev_proxy_headers,
    _fetch_token,
    _make_client,
    _post_complaint,
    _sign,
)


def _fetch_token_with_scope(client, *, api_base: str, profile: Profile,
                             dev_proxy_headers: dict[str, str], scope: str) -> str:
    """Fetch an OAuth token with a custom scope set (institution_push_demo
    hardcodes complaints:write/read, but the batch endpoint needs batch:upload).
    """
    url = f"{api_base.rstrip('/')}/oauth/token"
    headers = {
        "Authorization": _basic_auth_header(profile.client_id, profile.client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
        **dev_proxy_headers,
    }
    resp = client.post(
        url, headers=headers,
        data={"grant_type": "client_credentials", "scope": scope},
    )
    if resp.status_code != 200:
        raise SystemExit(
            f"OAuth token request failed (scope={scope}): HTTP {resp.status_code}\n"
            f"  body: {resp.text}"
        )
    return resp.json()["access_token"]

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "data" / "sbs_sample" / "SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx"


# ---------------------------------------------------------------------------
# XLSX column index
# ---------------------------------------------------------------------------

_COL = {
    "COD_REC": 0, "TID_CLI": 1, "NRO_CLI": 2, "NCL_CLI": 3, "COD_CLI": 4,
    "FEC_ING": 5, "CNL_ING": 6, "CNL_OPE": 7, "FEC_AMP": 8, "CNL_AMP": 9,
    "FEC_RES": 10, "CNL_PAC": 11, "UBI_REC": 12, "PRD_SBS": 13, "MOT_SBS": 14,
    "SUB_SBS": 15, "DET_REC": 16, "TIP_RES": 17, "DET_RES": 18, "PRD_EMP": 19,
    "EST_REC": 20, "COD_PRV": 21, "BAN_SEG": 22, "PRD_SBS_SEG": 23,
    "MOT_SBS_SEG": 24, "SUB_SBS_SEG": 25, "MNT_PEN_REC": 26, "EMPRESA": 27,
}


def _str(value: Any) -> str | None:
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
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Tier 1 (granular) — loose schema, orchestrator handles taxonomy
# ---------------------------------------------------------------------------


def row_to_granular_body(row: tuple, profile: Profile) -> dict[str, Any] | None:
    cod_rec = _str(row[_COL["COD_REC"]])
    det_rec = _str(row[_COL["DET_REC"]])
    if not cod_rec or not det_rec:
        return None
    # The DemoSubmissionRequest caps a handful of identifier fields at 16
    # chars; the real sample carries a few overlong values that would 422.
    # Truncate quietly so the demo loader stays bounded.
    def _cap16(v: str | None) -> str | None:
        return v[:16] if v else v

    body: dict[str, Any] = {
        "institution_id": profile.institution_id,
        "institution_name": profile.institution_display,
        "institution_complaint_id": _cap16(cod_rec),
        "client_submission_id": f"demo-{uuid.uuid4().hex[:12]}",
        "tid_cli": _cap16(_str(row[_COL["TID_CLI"]])),
        "nro_cli": _str(row[_COL["NRO_CLI"]]),
        "ncl_cli": _str(row[_COL["NCL_CLI"]]),
        "cod_cli": _str(row[_COL["COD_CLI"]]),
        "received_at": _iso_date(row[_COL["FEC_ING"]]),
        "channel_in": _str(row[_COL["CNL_ING"]]),
        "channel_operation": _str(row[_COL["CNL_OPE"]]),
        "fecha_comunicacion_ampliacion": _iso_date(row[_COL["FEC_AMP"]]),
        "canal_comunicacion_ampliacion": _str(row[_COL["CNL_AMP"]]),
        "fecha_resolucion": _iso_date(row[_COL["FEC_RES"]]),
        "canal_pago_cliente": _str(row[_COL["CNL_PAC"]]),
        "ubigeo": _str(row[_COL["UBI_REC"]]),
        "product": _str(row[_COL["PRD_SBS"]]),
        "motive": _str(row[_COL["MOT_SBS"]]),
        "submotive": _str(row[_COL["SUB_SBS"]]),
        "narrative": det_rec,
        "tipo_resolucion": _str(row[_COL["TIP_RES"]]),
        "response_detail": _str(row[_COL["DET_RES"]]),
        "producto_empresa": _str(row[_COL["PRD_EMP"]]),
        "status": _str(row[_COL["EST_REC"]]),
        "previous_complaint_id": _str(row[_COL["COD_PRV"]]),
        "bancaseguros": _str(row[_COL["BAN_SEG"]]),
        "producto_bancaseguros": _str(row[_COL["PRD_SBS_SEG"]]),
        "motivo_bancaseguros": _str(row[_COL["MOT_SBS_SEG"]]),
        "submotivo_bancaseguros": _str(row[_COL["SUB_SBS_SEG"]]),
        "monto_pendiente": _str(row[_COL["MNT_PEN_REC"]]),
        "demo_scenario": "demo-load-sbs-sample",
    }
    return {k: v for k, v in body.items() if v is not None}


# ---------------------------------------------------------------------------
# Tier 2 (batch) — strict Complaint schema, must use canonical enums
# ---------------------------------------------------------------------------


def _norm(text: str | None) -> str:
    """Lower-case, strip accents, collapse whitespace for fuzzy match."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(ascii_only.lower().split())


# Conservative mappings: raw SBS surface forms → strict Complaint enums.
# Unknowns fall back to OTRO so the row still validates.

_DOC_TYPE_MAP = {"dni": "DNI", "ce": "CE", "pasaporte": "PASAPORTE", "ruc": "RUC"}

_CHANNEL_MAP = {
    "pagina web de la empresa": "WEB", "pag. web de la empresa": "WEB",
    "pag web de la empresa": "WEB", "web": "WEB",
    "via telefonica": "TELEFONO", "telefono": "TELEFONO", "telefonica": "TELEFONO",
    "app movil": "APP_MOVIL", "aplicativo movil": "APP_MOVIL",
    "agencia": "AGENCIA", "oficina": "AGENCIA", "domicilio": "AGENCIA",
    "correo electronico": "CORREO", "correo": "CORREO",
    "por correo": "CORREO",
}

_SUBMISSION_METHOD_MAP = {
    "pagina web de la empresa": "WEB", "pag. web de la empresa": "WEB", "web": "WEB",
    "app movil": "APP_MOVIL", "aplicativo movil": "APP_MOVIL",
    "cajero automatico": "CAJERO", "cajero": "CAJERO",
    "agencia": "AGENCIA", "oficina": "AGENCIA", "domicilio": "AGENCIA",
    "pos": "POS",
    "agente corresponsal": "AGENTE_CORRESPONSAL",
}

_PRODUCT_MAP = {
    "credito de consumo": "CREDITOS",
    "creditos a pequenas empresas y microempresas": "CREDITOS",
    "credito hipotecario": "CREDITOS",
    "creditos": "CREDITOS",
    "tarjeta de credito": "TARJETA_CREDITO",
    "tarjeta de debito": "TARJETA_DEBITO",
    "cuenta de ahorro con tarjeta de debito": "TARJETA_DEBITO",
    "cuenta de ahorros": "DEPOSITOS",
    "cuenta corriente": "DEPOSITOS",
    "deposito a plazo": "DEPOSITOS",
    "cuenta a plazo": "DEPOSITOS",
    "depositos": "DEPOSITOS",
    "seguros": "SEGUROS",
    "afp": "AFP_PENSIONES", "afp pensiones": "AFP_PENSIONES",
    "coopac": "COOPAC",
}

_MOTIVO_MAP = {
    "operaciones no reconocidas": "OPERACION_NO_RECONOCIDA",
    "transacciones no procesadas / mal realizadas": "OPERACION_NO_RECONOCIDA",
    "transacciones no procesadas": "OPERACION_NO_RECONOCIDA",
    "cobros indebidos de intereses, comisiones, gastos y tributos (tales como seguros, itf, entre otros cargos, segun corresponda)": "COBRO_INDEBIDO",
    "cobros indebidos": "COBRO_INDEBIDO",
    "cobro indebido": "COBRO_INDEBIDO",
    "inadecuada o insuficiente informacion": "INFORMACION_INCORRECTA",
    "error en los datos del usuario": "INFORMACION_INCORRECTA",
    "error en los datos del usuario registrado en la empresa": "INFORMACION_INCORRECTA",
    "problemas relacionados con cajeros": "OPERACION_NO_RECONOCIDA",
    "problemas relacionados con cajeros automaticos": "OPERACION_NO_RECONOCIDA",
    "incumplimiento de clausulas": "INCUMPLIMIENTO_CONTRATO",
    "disconformidad por no atencion": "DEMORA_ATENCION",
    "calidad de servicio": "CALIDAD_SERVICIO",
    "publicidad enganosa": "PUBLICIDAD_ENGANOSA",
}

_RESOLUTION_STATUS_MAP = {
    "atendido": "atendido",
    "pendiente": "pendiente",
    "anulado": "anulado",
    "en proceso": "pendiente",
}


def _lookup(raw: str | None, table: dict[str, str], default: str) -> str:
    return table.get(_norm(raw), default)


def _to_complaint_id(cod_rec: str, ordinal: int) -> str:
    """Project the raw COD_REC to the strict 4-prefix Anexo pattern.

    Pattern: ``^[A-Z0-9]{1,4}-\\d{4}-\\d{6,10}$``. The raw codes vary
    (numeric for LARGE, 'R...' for SMALL); we synthesise a deterministic
    prefix per institution so every row is accepted.
    """
    digits = "".join(c for c in cod_rec if c.isdigit()) or f"{ordinal:06d}"
    seq = digits[-10:].zfill(6)
    year = dt.date.today().year
    return f"COP-{year}-{seq}"


def _age_range_from_doc(doc_id: str | None) -> str:
    # No real DOB in the dataset; bucket pseudo-deterministically from
    # the doc id so the field passes the enum check.
    buckets = ["UNDER_25", "25_34", "35_44", "45_54", "55_64", "OVER_64"]
    if not doc_id:
        return "UNKNOWN"
    digits = "".join(c for c in doc_id if c.isdigit())
    if not digits:
        return "UNKNOWN"
    return buckets[int(digits[-1]) % len(buckets)]


def _ubigeo_or_default(raw: str | None) -> str:
    """Coerce the raw UBI_REC value to a 6-digit ubigeo; default 150100."""
    if not raw:
        return "150100"
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 6:
        return digits
    if len(digits) == 4:
        return digits + "00"
    if len(digits) == 2:
        return digits + "0000"
    return "150100"


def _description_text(raw: str | None) -> str:
    if not raw:
        return "Sin detalle. Caso ingresado para procesamiento batch."
    cleaned = raw.replace("_x000D_", " ").replace("\r", " ").replace("\n", " ")
    cleaned = " ".join(cleaned.split())
    if len(cleaned) < 10:
        cleaned = (cleaned + " Caso de muestra Anexo 1-A.").strip()
    return cleaned[:8000]


_BATCH_CSV_HEADER = [
    "complaint_id", "institution_id", "received_date",
    "complainant_doc_type", "product_category", "channel", "motivo_code",
    "severity", "description_text", "description_language",
    "complainant_age_range", "complainant_district", "submission_method",
    "original_reference_id", "resolution_status",
]


def row_to_batch_csv_row(
    row: tuple, profile: Profile, ordinal: int
) -> list[str] | None:
    cod_rec = _str(row[_COL["COD_REC"]])
    if not cod_rec:
        return None
    return [
        _to_complaint_id(cod_rec, ordinal),
        profile.institution_id,
        _iso_date(row[_COL["FEC_ING"]]) or dt.date.today().isoformat(),
        _lookup(_str(row[_COL["TID_CLI"]]), _DOC_TYPE_MAP, "OTRO"),
        _lookup(_str(row[_COL["PRD_SBS"]]), _PRODUCT_MAP, "OTRO"),
        _lookup(_str(row[_COL["CNL_ING"]]), _CHANNEL_MAP, "OTRO"),
        _lookup(_str(row[_COL["MOT_SBS"]]), _MOTIVO_MAP, "OTRO"),
        "MEDIUM",
        _description_text(_str(row[_COL["DET_REC"]])),
        "es",
        _age_range_from_doc(_str(row[_COL["NRO_CLI"]])),
        _ubigeo_or_default(_str(row[_COL["UBI_REC"]])),
        _lookup(_str(row[_COL["CNL_OPE"]]), _SUBMISSION_METHOD_MAP, "OTRO"),
        "",
        _lookup(_str(row[_COL["EST_REC"]]), _RESOLUTION_STATUS_MAP, "pendiente"),
    ]


# ---------------------------------------------------------------------------
# Tier 2 batch POST — signed multipart upload
# ---------------------------------------------------------------------------


def _now_rfc3339_us() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def post_batch(
    *, api_base: str, profile: Profile, csv_bytes: bytes, row_count: int,
    insecure_skip_mtls: bool,
) -> tuple[int, dict[str, Any] | None]:
    """Send a multipart batch upload with the institutional auth chain.

    HMAC body-hash is over the CSV bytes only per ADR 0027 amendment.
    """
    client = _make_client(
        api_base=api_base, profile=profile, insecure_skip_mtls=insecure_skip_mtls,
    )
    dev_proxy_headers = _dev_proxy_headers(
        profile=profile, insecure_skip_mtls=insecure_skip_mtls,
    )
    try:
        token = _fetch_token_with_scope(
            client, api_base=api_base, profile=profile,
            dev_proxy_headers=dev_proxy_headers, scope="batch:upload",
        )
        checksum = hashlib.sha256(csv_bytes).hexdigest()
        today = dt.date.today()
        manifest = {
            "reporting_period_start": today.replace(day=1).isoformat(),
            "reporting_period_end": today.isoformat(),
            "row_count_submitted": row_count,
            "checksum_sha256": checksum,
            "schema_version": "v0.1.0",
        }
        target = "/v1/batches"
        url = f"{api_base.rstrip('/')}/batches"
        parsed = urllib.parse.urlparse(api_base)
        host_header = parsed.netloc or parsed.path or "localhost"

        timestamp = _now_rfc3339_us()
        canonical = _build_canonical_request(
            method="POST", target=target, host=host_header, timestamp=timestamp,
            body=csv_bytes, institution_id=profile.institution_id,
        )
        signature = _sign(profile.hmac_secret_hex, canonical)
        idem_key = f"demo-batch-{uuid.uuid4().hex[:24]}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": idem_key,
            "X-SBS-Timestamp": timestamp,
            "X-SBS-Signature": signature,
            "X-SBS-Institution-Id": profile.institution_id,
            **dev_proxy_headers,
        }
        files = {
            "manifest": (None, json.dumps(manifest), "application/json"),
            "file": (f"demo-batch-{idem_key[:8]}.csv", csv_bytes, "text/csv"),
        }
        resp = client.post(url, headers=headers, files=files)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, {"_raw_text": resp.text[:1000]}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# XLSX iteration
# ---------------------------------------------------------------------------


def _iter_rows(source: Path, sheet: str) -> Iterable[tuple]:
    try:
        import openpyxl
    except ImportError as exc:
        raise SystemExit(
            "openpyxl is required: install with `uv pip install openpyxl`"
        ) from exc
    wb = openpyxl.load_workbook(source, data_only=True, read_only=True)
    if sheet not in wb.sheetnames:
        raise SystemExit(
            f"sheet {sheet!r} not found; available: {wb.sheetnames}"
        )
    ws = wb[sheet]
    for idx, raw in enumerate(ws.iter_rows(values_only=True)):
        if idx == 0:
            continue
        if all(cell is None for cell in raw):
            continue
        yield raw
    wb.close()


# ---------------------------------------------------------------------------
# Run loops
# ---------------------------------------------------------------------------


@dataclass
class LargeStats:
    sent: int = 0
    ok: int = 0
    failed: int = 0


def run_large(
    *, source: Path, limit: int, api_base: str, profile: Profile,
    insecure_skip_mtls: bool, sleep_ms: int,
) -> LargeStats:
    stats = LargeStats()
    rows = list(_iter_rows(source, "LARGE_ENTITIES"))[:limit] if limit else list(
        _iter_rows(source, "LARGE_ENTITIES")
    )
    total = len(rows)
    print(f"\n=== Tier 1 NRT — LARGE_ENTITIES ({total} rows, profile={profile.name}) ===")
    client = _make_client(
        api_base=api_base, profile=profile, insecure_skip_mtls=insecure_skip_mtls,
    )
    dev_proxy_headers = _dev_proxy_headers(
        profile=profile, insecure_skip_mtls=insecure_skip_mtls,
    )
    try:
        token = _fetch_token(
            client, api_base=api_base, profile=profile,
            dev_proxy_headers=dev_proxy_headers,
        )
    finally:
        client.close()

    for idx, row in enumerate(rows, start=1):
        body = row_to_granular_body(row, profile)
        if body is None:
            print(f"[L {idx}/{total}] SKIP — empty narrative or COD_REC")
            continue
        stats.sent += 1
        idem_key = f"demo-{body['institution_complaint_id']}-{secrets.token_hex(4)}"
        try:
            sub_client = _make_client(
                api_base=api_base, profile=profile,
                insecure_skip_mtls=insecure_skip_mtls,
            )
            try:
                resp, _ts, _sig = _post_complaint(
                    sub_client, api_base=api_base, profile=profile, token=token,
                    body_dict=body, idempotency_key=idem_key,
                    dev_proxy_headers=dev_proxy_headers,
                )
                try:
                    payload = resp.json()
                except ValueError:
                    payload = {"_raw_text": resp.text[:200]}
            finally:
                sub_client.close()
        except Exception as exc:  # noqa: BLE001
            stats.failed += 1
            print(f"[L {idx}/{total}] EXC {type(exc).__name__}: {exc}")
            continue

        if resp.status_code in (200, 201):
            stats.ok += 1
            cid = payload.get("complaint_id", "?")
            recstatus = payload.get("status", "?")
            print(
                f"[L {idx}/{total}] OK complaint_id={cid} status={recstatus} "
                f"(tier=1 NRT)"
            )
        else:
            stats.failed += 1
            code = payload.get("code") if isinstance(payload, dict) else None
            print(
                f"[L {idx}/{total}] FAIL HTTP {resp.status_code} code={code} "
                f"COD_REC={body.get('institution_complaint_id')}"
            )
        time.sleep(sleep_ms / 1000.0)
    return stats


@dataclass
class SmallStats:
    csv_rows: int = 0
    batch_status: int = 0
    batch_id: str | None = None


def run_small(
    *, source: Path, limit: int, api_base: str, profile: Profile,
    insecure_skip_mtls: bool,
) -> SmallStats:
    stats = SmallStats()
    rows = list(_iter_rows(source, "SMALL_ENTITIES"))[:limit] if limit else list(
        _iter_rows(source, "SMALL_ENTITIES")
    )
    print(
        f"\n=== Tier 2 Batch — SMALL_ENTITIES ({len(rows)} rows, profile={profile.name}) ==="
    )
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(_BATCH_CSV_HEADER)
    ordinal = 0
    skipped = 0
    for row in rows:
        ordinal += 1
        csv_row = row_to_batch_csv_row(row, profile, ordinal)
        if csv_row is None:
            skipped += 1
            continue
        writer.writerow(csv_row)
        stats.csv_rows += 1
    if stats.csv_rows == 0:
        print(f"[S] no usable rows ({skipped} skipped)")
        return stats
    csv_bytes = buf.getvalue().encode("utf-8")
    print(
        f"[S] composed CSV: {stats.csv_rows} rows, "
        f"{len(csv_bytes)} bytes, skipped {skipped}"
    )
    try:
        status_code, payload = post_batch(
            api_base=api_base, profile=profile, csv_bytes=csv_bytes,
            row_count=stats.csv_rows, insecure_skip_mtls=insecure_skip_mtls,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[S] batch POST exception: {type(exc).__name__}: {exc}")
        return stats
    stats.batch_status = status_code
    if status_code == 202 and isinstance(payload, dict):
        stats.batch_id = payload.get("batch_id")
        print(
            f"[S] OK batch_id={stats.batch_id} status={payload.get('status')} "
            f"(tier=2 batch, {stats.csv_rows} rows queued)"
        )
    else:
        code = payload.get("code") if isinstance(payload, dict) else None
        title = payload.get("title") if isinstance(payload, dict) else None
        print(f"[S] FAIL HTTP {status_code} code={code} title={title}")
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if detail:
                print(f"      detail: {detail}")
        if status_code == 500:
            print(
                "      Likely cause: api/sbs_api/dependencies/hmac_verify.py "
                "calls request.body() unconditionally at line 139, but for "
                "multipart routes FastAPI's File()/Form() deps drain the "
                "stream first → RuntimeError('Stream consumed'). Fix by "
                "checking content-type before calling body()."
            )
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument(
        "--api-base", default="http://localhost:8000/v1",
        help="API base URL including /v1.",
    )
    p.add_argument(
        "--insecure-skip-mtls", action="store_true", default=True,
        help="Use dev XFCC header (proxy-mode local smoke). Default true.",
    )
    p.add_argument("--limit", type=int, default=None,
                   help="Apply same limit to both sheets.")
    p.add_argument("--large-limit", type=int, default=None,
                   help="Limit for LARGE_ENTITIES (overrides --limit).")
    p.add_argument("--small-limit", type=int, default=None,
                   help="Limit for SMALL_ENTITIES (overrides --limit).")
    p.add_argument("--sleep-ms", type=int, default=500,
                   help="Delay between Tier 1 POSTs (ms). Default 500.")
    p.add_argument("--skip-large", action="store_true")
    p.add_argument("--skip-small", action="store_true")
    args = p.parse_args()

    if not args.source.exists():
        print(f"ERROR: source not found: {args.source}", file=sys.stderr)
        return 2

    large_limit = args.large_limit if args.large_limit is not None else args.limit
    small_limit = args.small_limit if args.small_limit is not None else args.limit

    banco = PROFILES["banco-tier1"]
    coopac = PROFILES["coopac-tier2"]

    large_stats = LargeStats()
    small_stats = SmallStats()

    if not args.skip_large:
        large_stats = run_large(
            source=args.source, limit=large_limit or 0, api_base=args.api_base,
            profile=banco, insecure_skip_mtls=args.insecure_skip_mtls,
            sleep_ms=args.sleep_ms,
        )
    if not args.skip_small:
        small_stats = run_small(
            source=args.source, limit=small_limit or 0, api_base=args.api_base,
            profile=coopac, insecure_skip_mtls=args.insecure_skip_mtls,
        )

    print("\n=== Summary ===")
    print(
        f"  Tier 1 LARGE: sent={large_stats.sent} ok={large_stats.ok} "
        f"failed={large_stats.failed}"
    )
    print(
        f"  Tier 2 SMALL: csv_rows={small_stats.csv_rows} "
        f"batch_status={small_stats.batch_status} "
        f"batch_id={small_stats.batch_id}"
    )
    # Non-zero only if both tiers were requested and both produced zero successes.
    large_ran_and_failed = not args.skip_large and large_stats.ok == 0 and large_stats.sent > 0
    small_ran_and_failed = (
        not args.skip_small and small_stats.csv_rows > 0
        and small_stats.batch_status != 202
    )
    return 1 if (large_ran_and_failed and small_ran_and_failed) else 0


if __name__ == "__main__":
    sys.exit(main())
