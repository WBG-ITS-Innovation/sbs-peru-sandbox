#!/usr/bin/env python
"""Extract the RR1 reglamento de reclamos workbook into a JSON fixture.

Source:  data/sbs_sample/Copy of RR1_2025_values.xlsx
Output:  app/src/lib/rr1-2025.json

Three sheets — Empresa, Producto, Motivo — with the same month-columns
shape: a row label (entity / product / motivo) followed by 12 monthly
counts and a Total general column. The fixture preserves the row order
from the workbook so the supervisor recognises the layout from SUCAVE.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "data" / "sbs_sample" / "Copy of RR1_2025_values.xlsx"
OUT = REPO / "app" / "src" / "lib" / "rr1-2025.json"

MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
          "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]


def _to_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _norm_month_header(v) -> str | None:
    if isinstance(v, (dt.datetime, dt.date)):
        return f"{MONTHS[v.month - 1]}-{v.year % 100:02d}"
    if isinstance(v, str):
        s = v.strip()
        if s.startswith(("Ene", "Feb", "Mar", "Abr", "May", "Jun",
                         "Jul", "Ago", "Set", "Oct", "Nov", "Dic")):
            return s.replace("-", "-")
    return None


def extract_sheet(ws) -> dict:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"label_col": "", "months": [], "rows": []}
    header = rows[0]
    label_col = str(header[0]) if header[0] else ""
    months: list[str] = []
    month_indices: list[int] = []
    for i, h in enumerate(header[1:], start=1):
        m = _norm_month_header(h)
        if m:
            months.append(m)
            month_indices.append(i)
    data_rows = []
    for r in rows[1:]:
        if not r or r[0] is None:
            continue
        label = str(r[0]).strip()
        if not label or label.startswith(("Total general", "*")):
            continue
        values = [_to_int(r[i]) for i in month_indices]
        if all(v in (None, 0) for v in values):
            continue
        total = sum(v for v in values if v is not None)
        data_rows.append({
            "label": label[:80],
            "values": values,
            "total": total,
        })
    return {
        "label_col": label_col,
        "months": months,
        "rows": data_rows,
    }


def main() -> int:
    wb = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
    out = {
        "source": "RR1_2025_values.xlsx",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sheets": {
            "Empresa": extract_sheet(wb["Empresa"]),
            "Producto": extract_sheet(wb["Producto"]),
            "Motivo": extract_sheet(wb["Motivo"]),
        },
    }
    wb.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT}")
    for k, sh in out["sheets"].items():
        print(f"  {k}: {len(sh['rows'])} rows × {len(sh['months'])} months")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
