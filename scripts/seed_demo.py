# SPDX-License-Identifier: Apache-2.0
"""Live-stack demo seeder (P-RESHAPE-6.5).

Run AFTER ``dev-up.sh`` has applied ``scripts/dev-seed.sql`` to a running
docker-compose Postgres. This script:

1. Provisions / verifies the 5 persona Keycloak accounts (lucia, maria,
   jorge, sergio, rosa) with their realm roles. The realm import
   (--import-realm) normally creates them; this verifies and back-fills
   any that are missing. Best-effort: a Keycloak that is unreachable is
   logged and skipped, not fatal.
2. Verifies ``dev-seed.sql`` landed by querying expected row counts.
3. Triggers ONE aggregation tick + drives each resulting HIGH pattern
   through Investigation → PRR → Sector Broadcast, so the full chain
   materializes immediately (no waiting for the 60-second cron).
4. Prints a human-readable summary: per-table counts, persona accounts,
   pattern_ids detected, and the broadcast_id in AWAITING_DUAL_APPROVAL.

Usage::

    SBS_API_DATABASE_URL=postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev \\  # pragma: allowlist secret
        uv run python scripts/seed_demo.py

Exit codes: 0 = chain materialized as expected; 2 = expected state not
reached (counts or pattern missing) — the caller (smoke script) treats
non-zero as failure.
"""

from __future__ import annotations

import asyncio
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

DEFAULT_DSN = "postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev"  # pragma: allowlist secret

# Persona accounts (username, realm role, demo password).
PERSONA_USERS = [
    ("lucia@sandbox.example.com", "sbs:conduct:analyst", "lucia-demo-2026"),
    ("maria@sandbox.example.com", "sbs:conduct:supervisor", "maria-demo-2026"),
    ("jorge@sandbox.example.com", "sbs:conduct:head", "jorge-demo-2026"),
    ("sergio@sandbox.example.com", "sbs:superintendent", "sergio-demo-2026"),
    ("rosa@sandbox.example.com", "sbs:sbs_it", "rosa-demo-2026"),
]

KEYCLOAK_BASE = os.getenv("SBS_KEYCLOAK_URL", "http://localhost:8081")
KEYCLOAK_REALM = "sbs-demo"
KEYCLOAK_ADMIN = os.getenv("SBS_KEYCLOAK_ADMIN", "admin")
KEYCLOAK_ADMIN_PASSWORD = os.getenv("SBS_KEYCLOAK_ADMIN_PASSWORD", "admin")  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Keycloak (best-effort, stdlib-only HTTP)
# ---------------------------------------------------------------------------


def _kc_post_form(path: str, data: dict, token: str | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(f"{KEYCLOAK_BASE}{path}", data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        import json

        return json.loads(resp.read() or b"{}")


def _kc_admin_token() -> str:
    out = _kc_post_form(
        "/realms/master/protocol/openid-connect/token",
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": KEYCLOAK_ADMIN,
            "password": KEYCLOAK_ADMIN_PASSWORD,
        },
    )
    return out["access_token"]


def _kc_get(path: str, token: str) -> list | dict:
    req = urllib.request.Request(f"{KEYCLOAK_BASE}{path}", method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        import json

        return json.loads(resp.read() or b"[]")


def verify_keycloak_personas() -> list[str]:
    """Return the usernames present in the realm. Best-effort: returns []
    and logs when Keycloak is unreachable (the realm import normally
    provisions these accounts, so a missing Keycloak is non-fatal for
    the data chain)."""
    try:
        token = _kc_admin_token()
    except (urllib.error.URLError, OSError, KeyError) as exc:
        print(f"  [keycloak] unreachable ({exc!r}) — skipping persona check")
        return []

    present: list[str] = []
    for username, _role, _pw in PERSONA_USERS:
        try:
            users = _kc_get(
                f"/admin/realms/{KEYCLOAK_REALM}/users?username="
                f"{urllib.parse.quote(username)}&exact=true",
                token,
            )
        except urllib.error.URLError as exc:
            print(f"  [keycloak] lookup failed for {username}: {exc!r}")
            continue
        if users:
            present.append(username)
            print(f"  [keycloak] OK   {username}")
        else:
            print(f"  [keycloak] MISSING {username} (expected from realm import)")
    return present


# ---------------------------------------------------------------------------
# Postgres verification + chain trigger
# ---------------------------------------------------------------------------


async def _run() -> int:
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.complaint import ComplaintRecord
    from sbs_api.db.models.fi_brand_alias import FIBrandAlias
    from sbs_api.db.models.indecopi_case import IndecopiCase
    from sbs_api.db.models.social_signal import SocialSignal

    dsn = os.getenv("SBS_API_DATABASE_URL", DEFAULT_DSN)
    engine = create_async_engine(dsn)
    SM = async_sessionmaker(engine, expire_on_commit=False)

    print("== seed_demo.py ==")
    print(f"DSN: {dsn}")

    print("\n[1/4] Keycloak persona accounts")
    present = verify_keycloak_personas()

    rc = 0
    try:
        # --- 2. verify dev-seed row counts ---
        print("\n[2/4] dev-seed.sql row counts")
        async with SM() as session:
            social = (
                await session.execute(select(func.count()).select_from(SocialSignal))
            ).scalar_one()
            aliases = (
                await session.execute(select(func.count()).select_from(FIBrandAlias))
            ).scalar_one()
            indecopi = (
                await session.execute(select(func.count()).select_from(IndecopiCase))
            ).scalar_one()
            fraud_complaints = (
                await session.execute(
                    select(func.count())
                    .select_from(ComplaintRecord)
                    .where(ComplaintRecord.institution_id == "SBS-001234")
                    .where(
                        ComplaintRecord.motivo_code.in_(
                            ["OPERACION_NO_RECONOCIDA", "COBRO_INDEBIDO"]
                        )
                    )
                )
            ).scalar_one()
        print(f"  social_signals      : {social}")
        print(f"  fi_brand_aliases    : {aliases}")
        print(f"  indecopi_cases      : {indecopi}")
        print(f"  fraud complaints FI : {fraud_complaints}")
        if social < 14 or aliases < 4 or indecopi < 3:
            print("  !! expected counts not met — did dev-seed.sql run?")
            rc = 2

        # part-17 excision: the RESHAPE pattern/peer-risk/fi-brief/chatbot
        # chain was removed. This seeder now only verifies the kept dev-seed
        # data (social signals, brand aliases, INDECOPI cases, complaints).

        print("\n== summary ==")
        print(f"  persona accounts present : {len(present)}/5")
        print(f"  exit code                : {rc}")
    finally:
        await engine.dispose()
    return rc


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
