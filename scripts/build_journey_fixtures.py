#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Extract SBS sample XLSX rows into a JSON fixture for the demo-journey page.

Runs offline before the demo. Output:
    app/src/lib/journey-emails.json — 20 rows, mixed LARGE_ENTITIES /
    SMALL_ENTITIES, in a shape the Next.js page can render directly.

The point is to avoid pulling openpyxl / xlsx-parser into the Node runtime.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "data" / "sbs_sample" / "SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx"
OUT = REPO / "app" / "src" / "lib" / "journey-emails.json"

COLS = [
    "COD_REC", "TID_CLI", "NRO_CLI", "NCL_CLI", "COD_CLI", "FEC_ING",
    "CNL_ING", "CNL_OPE", "FEC_AMP", "CNL_AMP", "FEC_RES", "CNL_PAC",
    "UBI_REC", "PRD_SBS", "MOT_SBS", "SUB_SBS", "DET_REC", "TIP_RES",
    "DET_RES", "PRD_EMP", "EST_REC", "COD_PRV", "BAN_SEG", "PRD_SBS_SEG",
    "MOT_SBS_SEG", "SUB_SBS_SEG", "MNT_PEN_REC", "EMPRESA",
]


_FAKE_NAMES = [
    "Carlos Rodríguez Mendoza", "María Pérez Quispe", "Juan Quispe Huamán",
    "Lucía Vásquez Torres", "Pedro Castillo Núñez", "Ana Flores Romero",
    "Roberto Mendoza Silva", "Patricia Salazar Vega", "Luis Gutiérrez Paz",
    "Carmen Ríos Aliaga", "Diego Vargas Espinoza", "Sofía Cabrera Yupanqui",
    "Jorge Aliaga Cordero", "Rosa Huamaní Velásquez", "Andrés Bravo Loayza",
    "Elena Cárdenas Tello", "Miguel Zambrano Pino", "Daniela Pacheco Reyes",
    "Fernando Sánchez León", "Mariana Ortiz Cárdenas",
]
_FAKE_LOCATIONS = [
    "Lima Centro", "Miraflores", "San Isidro", "Surco", "Arequipa",
    "Trujillo", "Cusco", "Piura", "Chiclayo", "Iquitos",
]
_FAKE_ORGS = [
    "BANCO_DEMO_001", "Atención al Cliente", "Defensoría del Cliente",
    "Caja Arequipa", "Caja Cusco", "COOPAC_DEMO_002",
]
_FAKE_ADDRESSES = [
    "Av. Larco 1010", "Jr. de la Unión 543", "Av. Brasil 2200",
    "Calle Las Begonias 415", "Av. Javier Prado 1280",
]
_FAKE_ENTITIES = ["BANCO_DEMO_001", "BCP", "Interbank", "BBVA", "Scotiabank"]


def _unredact(text: str, seed_idx: int) -> str:
    """Replace SBS-style PII placeholders with deterministic fake values.

    The XLSX rows arrive pre-redacted (the SBS sample is sanitised before
    sharing). For the demo we want the FI side to *show* raw-looking PII
    so the SBS receive step has something to redact. The substitutions
    are stable per row index so the demo is reproducible.
    """

    import re

    def _pick(pool, salt):
        return pool[(seed_idx * 131 + salt) % len(pool)]

    def _fake_dni(salt):
        n = (seed_idx * 7919 + salt * 17 + 11111111) % 90000000 + 10000000
        return f"{n:08d}"

    def _fake_phone(salt):
        n = (seed_idx * 4093 + salt * 31) % 9000000 + 1000000
        return f"+51 9{n // 10000:03d} {n // 10 % 1000:03d} {n % 10:01d}"

    def _fake_ruc(salt):
        n = (seed_idx * 1009 + salt * 23 + 20100000000) % 89999999999 + 10000000000
        return str(n)

    def _fake_email(salt):
        name = _pick(_FAKE_NAMES, salt).split()[0].lower()
        return f"{name}.{_fake_dni(salt + 1)[:4]}@example.com"

    def _fake_numbers(salt):
        return str((seed_idx * 7 + salt) % 10000)

    repls = [
        (r"<PERSON>",              lambda i: _pick(_FAKE_NAMES, i)),
        (r"<PE_DNI>",              lambda i: f"DNI {_fake_dni(i)}"),
        (r"<PE_PHONE>",            lambda i: _fake_phone(i)),
        (r"<PE_RUC>",              lambda i: f"RUC {_fake_ruc(i)}"),
        (r"<EMAIL_ADDRESS>",       lambda i: _fake_email(i)),
        (r"<PE_ADDRESS>",          lambda i: _pick(_FAKE_ADDRESSES, i)),
        (r"<PE_FINANCIAL_ENTITY>", lambda i: _pick(_FAKE_ENTITIES, i)),
        (r"<ORGANIZATION>",        lambda i: _pick(_FAKE_ORGS, i)),
        (r"<LOCATION>",            lambda i: _pick(_FAKE_LOCATIONS, i)),
        (r"<NUMBERS>",             lambda i: _fake_numbers(i)),
    ]
    out = text
    for pattern, fn in repls:
        counter = [0]

        def _sub(_m, _counter=counter, _fn=fn):
            _counter[0] += 1
            return _fn(_counter[0])

        out = re.sub(pattern, _sub, out)
    return out


def _cell(v, seed_idx: int = 0, unredact: bool = False):
    if v is None:
        return None
    if isinstance(v, (dt.datetime,)):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, str):
        # Normalize the _x000D_ artifacts from Word-paste cells.
        s = v.replace("_x000D_", " ").replace("\r", " ").replace("\n", " ").strip()
        s = " ".join(s.split()) or None
        if s and unredact:
            s = _unredact(s, seed_idx)
        return s
    return v


def row_to_dict(row, sheet_name: str, seed_idx: int) -> dict:
    # FI side sees raw PII (real names, DNIs, phones). The XLSX rows
    # arrive pre-redacted from the SBS sample share; _unredact substitutes
    # deterministic fake values for the placeholders so the demo can show
    # the SBS receive step doing real PII redaction work.
    raw = dict(zip(COLS, [_cell(c, seed_idx=seed_idx, unredact=True) for c in row]))
    raw["__sheet"] = sheet_name
    raw["__institution"] = (
        "BANCO_DEMO_001" if sheet_name == "LARGE_ENTITIES" else "COOPAC_DEMO_002"
    )
    raw["__institution_id"] = (
        "SBS-001234" if sheet_name == "LARGE_ENTITIES" else "SBS-005678"
    )
    return raw


def main() -> int:
    wb = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
    large = [
        row_to_dict(r, "LARGE_ENTITIES", seed_idx=i)
        for i, r in enumerate(wb["LARGE_ENTITIES"].iter_rows(values_only=True))
        if i > 0 and any(c is not None for c in r)
    ]
    small = [
        row_to_dict(r, "SMALL_ENTITIES", seed_idx=1000 + i)
        for i, r in enumerate(wb["SMALL_ENTITIES"].iter_rows(values_only=True))
        if i > 0 and any(c is not None for c in r)
    ]
    wb.close()

    # Interleave so the inbox visibly mixes the two institutions.
    interleaved: list[dict] = []
    for i in range(max(len(large), len(small))):
        if i < len(large):
            interleaved.append(large[i])
        if i < len(small):
            interleaved.append(small[i])

    # Keep only rows with a narrative — the email "body" must be non-empty.
    # Cap at 80 so the live ingestion ticker has plenty of material.
    usable = [r for r in interleaved if r.get("DET_REC")][:80]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(usable, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(usable)} rows → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
