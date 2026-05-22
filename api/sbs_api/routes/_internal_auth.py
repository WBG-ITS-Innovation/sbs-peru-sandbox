"""Shared internal-API authentication dependency.

Used by every ``/v1/internal/*`` route — same shared-secret model as
ADR 0040 §D8's audit endpoint (the Next.js server holds the secret;
FastAPI verifies it on every internal call). Returns 404 when the
secret is not configured at all so a misconfigured deployment does
not expose the internal surface.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException

from sbs_api.config import Settings, get_settings


def verify_internal_secret(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.internal_api_secret
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    presented = authorization[len("Bearer ") :]
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
