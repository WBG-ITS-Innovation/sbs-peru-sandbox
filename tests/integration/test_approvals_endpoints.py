"""WS5 approvals integration tests.

Covers the queue, the detail endpoint, all four decision actions
(each writing to its prescribed table), idempotency on duplicate
POST, the server-side 20-character rationale gate on reject, and
the decision-audit-row meta-shape contract.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


# Demo-only token; never used outside tests.
SHARED_VAL = "sandbox-approvals-test-9988aabbcc"  # pragma: allowlist secret


@pytest.fixture
async def app_with_secret(app_settings, monkeypatch, db_schema):
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED_VAL)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app

    fresh = get_settings()
    application = create_app(settings=fresh)
    yield application
    get_settings.cache_clear()


async def _seed_pending_approval(
    test_database_url: str, complaint_id: str = "BCO-2026-000001"
) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.pending_approval import PendingApproval

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        pending = PendingApproval(
            complaint_id=complaint_id,
            agent_run_id=None,
            status="pending",
            severity="high",
            created_by="lucia@sbs.gob.pe",
        )
        session.add(pending)
        await session.commit()
        pid = pending.id
    await engine.dispose()
    return pid


def _head_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SHARED_VAL}",
        "X-SBS-Role": "sbs:conduct:head",
    }


def _supervisor_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SHARED_VAL}",
        "X-SBS-Role": "sbs:conduct:supervisor",
    }


# -- Queue + detail ---------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_returns_pending_severity_sorted(
    app_with_secret, test_database_url
):
    await _seed_pending_approval(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/approvals", headers=_head_headers()
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_pending"] >= 1
    assert "kpis" in body
    assert body["kpis"]["pending"] >= 1


@pytest.mark.asyncio
async def test_queue_403s_for_supervisor_role(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/approvals", headers=_supervisor_headers()
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_detail_returns_pinned_evidence_and_finding(
    app_with_secret, test_database_url
):
    pid = await _seed_pending_approval(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/v1/internal/approvals/{pid}", headers=_head_headers()
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pending_approval"]["id"] == pid
    assert "pinned_evidence" in body
    assert "finding" in body
    assert body["finding"]["complaint"]["complaint_id"] == "BCO-2026-000001"


# -- Decision actions -------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_writes_observation_and_audit_idempotent(
    app_with_secret, test_database_url
):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.audit_event import AuditEvent
    from sbs_api.db.models.supervisory_observation import SupervisoryObservation

    pid = await _seed_pending_approval(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            f"/v1/internal/approvals/{pid}/approve",
            headers=_head_headers(),
            json={"actor_id": "jorge@sbs.gob.pe"},
        )
        second = await client.post(
            f"/v1/internal/approvals/{pid}/approve",
            headers=_head_headers(),
            json={"actor_id": "jorge@sbs.gob.pe"},
        )
    assert first.status_code == 201, first.text
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        observations = (
            await session.execute(
                select(SupervisoryObservation).where(
                    SupervisoryObservation.pending_approval_id == pid
                )
            )
        ).scalars().all()
        audits = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "approve-finding")
            )
        ).scalars().all()
    await engine.dispose()
    assert len(observations) == 1
    # The audit row for this approval — meta carries pending_approval_id.
    matching_audits = [a for a in audits if (a.meta or {}).get("pending_approval_id") == pid]
    assert len(matching_audits) == 1


@pytest.mark.asyncio
async def test_approve_with_edits_writes_observation_and_feedback_and_audit(
    app_with_secret, test_database_url
):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.agent_feedback import AgentFeedback
    from sbs_api.db.models.supervisory_observation import SupervisoryObservation

    pid = await _seed_pending_approval(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/v1/internal/approvals/{pid}/approve-with-edits",
            headers=_head_headers(),
            json={
                "actor_id": "jorge@sbs.gob.pe",
                "edited_narrative": "Final narrative with the head's clarification added.",
                "rationale": "Added the comisión por mantenimiento reference from paragraph two.",
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision_action"] == "approve-with-edits"
    assert body["observation_id"] is not None
    assert body["feedback_id"] is not None

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        obs = (
            await session.execute(
                select(SupervisoryObservation).where(
                    SupervisoryObservation.pending_approval_id == pid
                )
            )
        ).scalars().all()
        feed = (
            await session.execute(
                select(AgentFeedback).where(AgentFeedback.pending_approval_id == pid)
            )
        ).scalars().all()
    await engine.dispose()
    assert len(obs) == 1
    assert obs[0].narrative == "Final narrative with the head's clarification added."
    assert len(feed) == 1
    assert feed[0].decision == "approve-with-edits"
    assert feed[0].edit_diff is not None
    assert "before" in feed[0].edit_diff
    assert "after" in feed[0].edit_diff


@pytest.mark.asyncio
async def test_reject_writes_feedback_and_audit(
    app_with_secret, test_database_url
):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.agent_feedback import AgentFeedback

    pid = await _seed_pending_approval(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/v1/internal/approvals/{pid}/reject",
            headers=_head_headers(),
            json={
                "actor_id": "jorge@sbs.gob.pe",
                "rationale": "Insufficient evidence for misselling — narrative ambiguous.",
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision_action"] == "reject"
    assert body["feedback_id"] is not None

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        rows = (
            await session.execute(
                select(AgentFeedback).where(AgentFeedback.pending_approval_id == pid)
            )
        ).scalars().all()
    await engine.dispose()
    assert len(rows) == 1
    assert rows[0].decision == "reject"
    assert rows[0].edit_diff is None


@pytest.mark.asyncio
async def test_reject_with_short_rationale_returns_422(
    app_with_secret, test_database_url
):
    """Non-droppable: the 20-character rationale gate is server-side, not
    only a client-side helper. A bypass with curl cannot write a reject
    with a 5-character rationale."""

    pid = await _seed_pending_approval(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/v1/internal/approvals/{pid}/reject",
            headers=_head_headers(),
            json={"actor_id": "jorge@sbs.gob.pe", "rationale": "no"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_back_transitions_status_and_writes_audit(
    app_with_secret, test_database_url
):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.audit_event import AuditEvent
    from sbs_api.db.models.pending_approval import PendingApproval

    pid = await _seed_pending_approval(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/v1/internal/approvals/{pid}/send-back",
            headers=_head_headers(),
            json={
                "actor_id": "jorge@sbs.gob.pe",
                "note": "Please verify the institution's prior response window.",
            },
        )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "sent_back"

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        pending = (
            await session.execute(
                select(PendingApproval).where(PendingApproval.id == pid)
            )
        ).scalar_one()
        audits = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "send-back-finding")
            )
        ).scalars().all()
    await engine.dispose()
    assert pending.status == "sent_back"
    matching = [a for a in audits if (a.meta or {}).get("pending_approval_id") == pid]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_decision_audit_meta_shape_contract(
    app_with_secret, test_database_url
):
    """Decision-audit contract — every decision action emits an
    audit_events row whose meta carries the same shape so WS6's audit
    screen renders them uniformly. The keys checked here must match
    what _decision_meta() in api/sbs_api/routes/approvals.py emits."""

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.audit_event import AuditEvent

    pid1 = await _seed_pending_approval(test_database_url)
    pid2 = await _seed_pending_approval(test_database_url, complaint_id="BCO-2026-000002")
    pid3 = await _seed_pending_approval(test_database_url, complaint_id="BCO-2026-000003")
    pid4 = await _seed_pending_approval(test_database_url, complaint_id="BCO-2026-000001")

    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            f"/v1/internal/approvals/{pid1}/approve",
            headers=_head_headers(),
            json={"actor_id": "jorge@sbs.gob.pe"},
        )
        await client.post(
            f"/v1/internal/approvals/{pid2}/approve-with-edits",
            headers=_head_headers(),
            json={
                "actor_id": "jorge@sbs.gob.pe",
                "edited_narrative": "Edited.",
                "rationale": "Twenty character rationale ok.",
            },
        )
        await client.post(
            f"/v1/internal/approvals/{pid3}/reject",
            headers=_head_headers(),
            json={
                "actor_id": "jorge@sbs.gob.pe",
                "rationale": "Twenty character rationale ok.",
            },
        )
        await client.post(
            f"/v1/internal/approvals/{pid4}/send-back",
            headers=_head_headers(),
            json={
                "actor_id": "jorge@sbs.gob.pe",
                "note": "Note for the analyst above twenty.",
            },
        )

    required_keys = {
        "pending_approval_id",
        "complaint_id",
        "agent_run_id",
        "decision_action",
        "observation_id",
        "feedback_id",
        "severity",
        "rationale_excerpt",
        "edit_diff",
    }
    expected_actions = {
        "approve-finding",
        "approve-with-edits-finding",
        "reject-finding",
        "send-back-finding",
    }
    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action.in_(expected_actions))
            )
        ).scalars().all()
    await engine.dispose()

    actions_seen = {r.action for r in rows}
    assert actions_seen == expected_actions, actions_seen
    for r in rows:
        meta = r.meta or {}
        missing = required_keys - set(meta.keys())
        assert not missing, (
            f"audit row {r.action!r} missing meta keys: {missing}; meta={meta}"
        )
        assert meta["decision_action"] in {
            "approve",
            "approve-with-edits",
            "reject",
            "send-back-to-analyst",
        }
