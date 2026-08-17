# SPDX-License-Identifier: Apache-2.0
"""Serve the canonical OpenAPI YAML at ``/v1/openapi.yaml``.

ADR 0027 made the YAML the canonical contract. ADR 0028 turns off FastAPI's
auto-generated ``/openapi.json``, ``/docs``, ``/redoc`` to prevent silent
drift; the only contract artifact reachable from a running app is the
hand-curated YAML served here.
"""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from sbs_api.config import get_settings

router = APIRouter(tags=["Meta"])


def _canonical_path() -> pathlib.Path:
    settings = get_settings()
    p = pathlib.Path(settings.canonical_openapi_path)
    if not p.is_absolute():
        # Project root = parents of this file's package: api/sbs_api → api → root
        root = pathlib.Path(__file__).resolve().parents[3]
        p = root / p
    return p


@router.get("/openapi.yaml", response_class=PlainTextResponse, include_in_schema=False)
async def serve_canonical_openapi() -> PlainTextResponse:
    path = _canonical_path()
    if not path.is_file():
        raise HTTPException(status_code=500, detail="canonical openapi not found")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="application/yaml",
    )
