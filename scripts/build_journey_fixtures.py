#!/usr/bin/env python
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


def _cell(v):
    if v is None:
        return None
    if isinstance(v, (dt.datetime,)):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, str):
        # Normalize the _x000D_ artifacts from Word-paste cells.
        s = v.replace("_x000D_", " ").replace("\r", " ").replace("\n", " ").strip()
        return " ".join(s.split()) or None
    return v


def row_to_dict(row, sheet_name: str) -> dict:
    raw = dict(zip(COLS, [_cell(c) for c in row]))
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
        row_to_dict(r, "LARGE_ENTITIES")
        for i, r in enumerate(wb["LARGE_ENTITIES"].iter_rows(values_only=True))
        if i > 0 and any(c is not None for c in r)
    ]
    small = [
        row_to_dict(r, "SMALL_ENTITIES")
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
        if len(interleaved) >= 30:
            break

    # Keep only rows with a narrative — the email "body" must be non-empty.
    usable = [r for r in interleaved if r.get("DET_REC")][:20]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(usable, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(usable)} rows → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
