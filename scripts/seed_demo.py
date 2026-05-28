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
    ("lucia@sbs.gob.pe", "sbs:conduct:analyst", "lucia-demo-2026"),
    ("maria@sbs.gob.pe", "sbs:conduct:supervisor", "maria-demo-2026"),
    ("jorge@sbs.gob.pe", "sbs:conduct:head", "jorge-demo-2026"),
    ("sergio@sbs.gob.pe", "sbs:superintendent", "sergio-demo-2026"),
    ("rosa@sbs.gob.pe", "sbs:sbs_it", "rosa-demo-2026"),
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


async def _seed_chatbot_sample(session) -> None:
    """Seed one Jorge chatbot session answering 'show me the
    BANCO_DEMO_001 fraud emergence' — grounded in the real fraud pattern
    just materialized, so the demo opens with a working example.

    Idempotent: keyed on a fixed session_id."""
    import uuid as _uuid
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from sqlalchemy import select as _select

    from sbs_api.agents.insight_chatbot_tools import dispatch_tool
    from sbs_api.db.models.chatbot_session import ChatbotMessage, ChatbotSession
    from sbs_api.db.models.pattern_detection import PatternDetection

    sample_session_id = "demo-jorge-fraud-chatbot"
    existing = (
        await session.execute(
            _select(ChatbotSession).where(
                ChatbotSession.session_id == sample_session_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        print("  sample session already present — skipping")
        return

    fraud = (
        await session.execute(
            _select(PatternDetection)
            .where(PatternDetection.pattern_type == "FRAUD_EMERGENCE")
            .where(PatternDetection.severity_band == "HIGH")
            .limit(1)
        )
    ).scalar_one_or_none()
    if fraud is None:
        print("  no fraud pattern to ground the sample on — skipping")
        return

    now = _dt.now(tz=_tz.utc)
    session.add(
        ChatbotSession(
            session_id=sample_session_id,
            user_id="jorge@sbs.gob.pe",
            persona="sbs:conduct:head",
            started_at=now,
            last_activity_at=now,
            message_count=2,
        )
    )
    # Ground the assistant answer in a real tool result for a real citation.
    result = await dispatch_tool(
        session,
        name="query_patterns",
        params={
            "institution_code": "SBS-001234",
            "pattern_type": "FRAUD_EMERGENCE",
        },
        permitted=["query_patterns"],
        aggregate_only=False,
    )
    session.add(
        ChatbotMessage(
            message_id=str(_uuid.uuid4()),
            session_id=sample_session_id,
            role="user",
            content="Muéstrame la emergencia de fraude de BANCO_DEMO_001.",
        )
    )
    session.add(
        ChatbotMessage(
            message_id=str(_uuid.uuid4()),
            session_id=sample_session_id,
            role="assistant",
            content=(
                "Se detectó un patrón FRAUD_EMERGENCE de severidad HIGH para "
                "BANCO_DEMO_001, originado por señales de redes sociales, "
                "reclamos e INDECOPI. Se generó una alerta sectorial para la "
                "cohorte de pares (pendiente de doble aprobación)."
            ),
            citations={"items": [result.citation()]},
            model_id="qwen2.5-14b-onprem",
            model_provider="onprem",
        )
    )
    print(f"  seeded sample session {sample_session_id} citing {fraud.pattern_id}")


async def _seed_agent_runs_and_tasks(session) -> None:
    """Seed agent_runs across all six agents (P-RESHAPE-8.5) so the unified
    monitoring endpoint returns meaningful data, plus a couple of sample
    tasks for the inbox/outbox. One run is left ``in_progress`` so a card
    shows RUNNING during the demo."""
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from sbs_api.db.models.agent_run import AgentRun
    from sbs_api.db.models.complaint import ComplaintRecord
    from sbs_api.db.models.persona_task import PersonaTask

    cid = (
        await session.execute(select(ComplaintRecord.complaint_id).limit(1))
    ).scalar_one_or_none()
    if cid is None:
        print("  !! no complaint to attach agent_runs to — skipping")
        return

    now = datetime.now(tz=timezone.utc)
    model = {"model_id": "qwen2.5-14b-onprem", "model_provider": "on_prem"}
    # (agent_name, [(minutes_ago, duration_ms, status)])
    plan = {
        "divalevale": [(20, 210, "success"), (180, 240, "success"), (600, 320, "partial")],
        "triage": [(15, 180, "success"), (90, 160, "success"), (300, 900, "success")],
        "investigation": [(5, 0, "in_progress"), (240, 1800, "success")],
        "issue-resurface": [(120, 2200, "success"), (700, 2600, "partial")],
        "peer-risk-radar": [(60, 3100, "success"), (480, 2900, "success")],
        "sector-broadcast": [(140, 1500, "success"), (520, 1700, "failed")],
        "insight-chatbot": [(10, 640, "success"), (45, 720, "success")],
    }
    count = 0
    for name, runs in plan.items():
        for mins, dur_ms, status in runs:
            started = now - timedelta(minutes=mins)
            ended = None if status == "in_progress" else started + timedelta(
                milliseconds=dur_ms
            )
            session.add(
                AgentRun(
                    id=str(_uuid.uuid4()),
                    complaint_id=cid,
                    agent_name=name,
                    agent_version=f"{name}-0.1.0",
                    started_at=started,
                    ended_at=ended,
                    status=status,
                    tool_calls=[],
                    final_output=None if status == "in_progress" else dict(model),
                    error=None,
                )
            )
            count += 1

    # Sample tasks for the inbox/outbox demo.
    session.add(
        PersonaTask(
            task_id=str(_uuid.uuid4()),
            created_by_user_id="sergio",
            created_by_persona="sbs:superintendent",
            assigned_to_user_id=None,
            assigned_to_persona="sbs:conduct:head",
            task_type="DEEPER_LOOK",
            ref_type="PATTERN",
            ref_id="demo-pattern-1",
            rationale="Profundizar en el patrón de fraude emergente del sector.",
            state="OPEN",
        )
    )
    session.add(
        PersonaTask(
            task_id=str(_uuid.uuid4()),
            created_by_user_id="maria",
            created_by_persona="sbs:conduct:supervisor",
            assigned_to_user_id="lucia",
            assigned_to_persona="sbs:conduct:analyst",
            task_type="PATTERN_DELEGATION",
            ref_type="FINDING",
            ref_id="demo-finding-1",
            rationale="Revisa este patrón a nivel de reclamos individuales.",
            state="OPEN",
        )
    )
    print(f"  seeded {count} agent_runs (1 in_progress) + 2 sample tasks")


# ---------------------------------------------------------------------------
# Postgres verification + chain trigger
# ---------------------------------------------------------------------------


async def _run() -> int:
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.aggregation.tick import run_aggregation_tick
    from sbs_api.agents.orchestrator import run_investigation_from_pattern
    from sbs_api.db.models.complaint import ComplaintRecord
    from sbs_api.db.models.fi_brand_alias import FIBrandAlias
    from sbs_api.db.models.indecopi_case import IndecopiCase
    from sbs_api.db.models.pattern_detection import PatternDetection
    from sbs_api.db.models.sector_broadcast import SectorBroadcast
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

        # --- 3. trigger one tick + drive HIGH patterns through the chain ---
        print("\n[3/4] aggregation tick + chain")
        async with SM() as session:
            tick = await run_aggregation_tick(session)
            await session.commit()
        print(
            f"  tick: {tick.candidates_evaluated} candidates, "
            f"{tick.rows_inserted} inserted, {len(tick.high_pattern_ids)} HIGH"
        )
        async with SM() as session:
            for pid in tick.high_pattern_ids:
                await run_investigation_from_pattern(session, pattern_id=pid)
            await session.commit()

        # --- 3b. seed a sample chatbot session for Jorge ---
        # So the live demo has a working chatbot example without typing.
        print("\n[3b/4] sample chatbot session (Jorge)")
        async with SM() as session:
            await _seed_chatbot_sample(session)
            await session.commit()

        # --- 3c. agent_runs across all six agents + sample tasks ---
        print("\n[3c/4] agent_runs + sample tasks (unified monitoring)")
        async with SM() as session:
            await _seed_agent_runs_and_tasks(session)
            await session.commit()

        # --- 4. summary ---
        print("\n[4/4] materialized state")
        async with SM() as session:
            fraud_patterns = (
                await session.execute(
                    select(PatternDetection).where(
                        PatternDetection.pattern_type == "FRAUD_EMERGENCE"
                    )
                )
            ).scalars().all()
            broadcasts = (
                await session.execute(select(SectorBroadcast))
            ).scalars().all()

        for p in fraud_patterns:
            print(
                f"  FRAUD_EMERGENCE pattern {p.pattern_id} "
                f"band={p.severity_band} fi={p.institution_code}"
            )
        for b in broadcasts:
            print(
                f"  SectorBroadcast {b.broadcast_id} status={b.status} "
                f"targets={len(b.target_fi_codes)}"
            )

        high_fraud = [p for p in fraud_patterns if p.severity_band == "HIGH"]
        awaiting = [b for b in broadcasts if b.status == "AWAITING_DUAL_APPROVAL"]
        if not high_fraud:
            print("  !! no HIGH FRAUD_EMERGENCE pattern materialized")
            rc = 2
        if not awaiting:
            print("  !! no SectorBroadcast in AWAITING_DUAL_APPROVAL")
            rc = 2

        print("\n== summary ==")
        print(f"  persona accounts present : {len(present)}/5")
        print(f"  FRAUD_EMERGENCE HIGH     : {len(high_fraud)}")
        print(
            f"  broadcast awaiting approval: "
            f"{awaiting[0].broadcast_id if awaiting else 'NONE'}"
        )
        print(f"  exit code                : {rc}")
    finally:
        await engine.dispose()
    return rc


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
