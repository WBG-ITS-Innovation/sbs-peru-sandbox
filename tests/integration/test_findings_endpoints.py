# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the WS4 findings endpoints.

Covers list + detail + draft-save + send-to-approvals + role scoping
on the SSE route. All gated on a Postgres testcontainer via
pytestmark_db; the assertions exercise the contracts the WS4
non-droppables call out (BERT confidence numeric, XGBoost features
present, audit row written on edit + send-to-approvals).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import pytestmark_db
from tests.integration._sse_probe import open_sse_head_only

pytestmark = pytestmark_db


# Demo-only token for the internal API; never used outside tests.
SHARED_VAL = "sandbox-findings-test-fedcba9876543210"  # pragma: allowlist secret


@pytest.fixture
async def app_with_secret(app_settings, monkeypatch, db_schema):
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED_VAL)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app
    from sbs_api.db.session import reset_engine_for_test

    await reset_engine_for_test()
    fresh = get_settings()
    application = create_app(settings=fresh)
    try:
        yield application
    finally:
        await reset_engine_for_test()
        get_settings.cache_clear()


async def _seed_headline_agent_run(test_database_url: str) -> str:
    """Insert one classifier-success row on BCO-2026-000001 so the
    findings list / detail have something to surface. Returns the
    agent_run id."""

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.agent_run import AgentRun

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    run_id = "test-classifier-1"
    async with SessionMaker() as session:
        session.add(
            AgentRun(
                id=run_id,
                complaint_id="BCO-2026-000001",
                agent_name="classifier",
                agent_version="classifier-0.4.0",
                started_at=datetime.now(tz=timezone.utc),
                ended_at=datetime.now(tz=timezone.utc),
                status="success",
                tool_calls=[
                    {
                        "tool_name": "bert_classifier",
                        "tool_version": "bert_classifier-1.4.0",
                        "started_at": "2026-05-22T13:00:00+00:00",
                        "ended_at": "2026-05-22T13:00:01+00:00",
                        "input": {"text": "x", "locale": "es-PE", "max_tokens": 512},
                        "output": {
                            "label": "undisclosed-fees-credit",
                            "confidence": 0.87,
                            "top_k": [
                                {"label": "undisclosed-fees-credit", "confidence": 0.87},
                                {"label": "misselling", "confidence": 0.08},
                                {"label": "billing-dispute", "confidence": 0.05},
                            ],
                            "model_version": "beto-onnx-2026.04",
                        },
                        "status": "success",
                        "error": None,
                    },
                    {
                        "tool_name": "xgboost_ranker",
                        "tool_version": "xgboost_ranker-0.9.2",
                        "started_at": "2026-05-22T13:00:01+00:00",
                        "ended_at": "2026-05-22T13:00:02+00:00",
                        "input": {
                            "complaint_id": "BCO-2026-000001",
                            "features": {"narrative_mentions_fee_undisclosed": 1},
                        },
                        "output": {
                            "score": 0.78,
                            "rank_band": "high",
                            "feature_contributions": [
                                {
                                    "feature_name": "narrative_mentions_fee_undisclosed",
                                    "contribution": 0.27,
                                    "direction": "positive",
                                },
                            ],
                            "model_version": "xgb-ranker-2026.03",
                        },
                        "status": "success",
                        "error": None,
                    },
                ],
                final_output={
                    "classification": "undisclosed-fees-credit",
                    "confidence": 0.87,
                    "sub_patterns": [],
                },
                error=None,
            )
        )
        await session.commit()
    await engine.dispose()
    return run_id


@pytest.mark.asyncio
async def test_findings_list_returns_seeded_complaints_for_analyst(
    app_with_secret, test_database_url
):
    await _seed_headline_agent_run(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/findings?use_defaults=false",
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:analyst",
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    ids = [i["complaint_id"] for i in body["items"]]
    assert "BCO-2026-000001" in ids
    # Confidence must be numeric, not bucketed.
    item = next(i for i in body["items"] if i["complaint_id"] == "BCO-2026-000001")
    assert isinstance(item["confidence"], float)
    assert item["classification"] == "undisclosed-fees-credit"


@pytest.mark.asyncio
async def test_findings_detail_returns_all_panel_fields(
    app_with_secret, test_database_url
):
    await _seed_headline_agent_run(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/findings/BCO-2026-000001",
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:analyst",
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    # Five-panel non-droppables: complaint + classification + features +
    # agent_runs + (current_narrative or agent_drafted_narrative).
    assert body["complaint"]["complaint_id"] == "BCO-2026-000001"
    assert body["classification"]["confidence"] == 0.87
    assert body["features"]["feature_contributions"][0]["feature_name"] == (
        "narrative_mentions_fee_undisclosed"
    )
    assert len(body["agent_runs"]) >= 1


@pytest.mark.asyncio
async def test_findings_detail_404_when_complaint_not_found(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/findings/NOPE-2026-000999",
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:analyst",
            },
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_draft_save_writes_draft_row_and_audit_row(
    app_with_secret, test_database_url
):
    """Edit + save → complaint_narrative_drafts row + audit_events row.
    Non-droppable contract for WS5 trust."""

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.audit_event import AuditEvent
    from sbs_api.db.models.complaint_narrative_draft import ComplaintNarrativeDraft

    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/internal/findings/BCO-2026-000001/draft",
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:analyst",
            },
            json={
                "after_text": "Edited narrative with the fee mention.",
                "actor_id": "analyst@sandbox.example.com",
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["id"], int)
    assert isinstance(body["audit_event_id"], int)

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        drafts = (
            await session.execute(
                select(ComplaintNarrativeDraft).where(
                    ComplaintNarrativeDraft.complaint_id == "BCO-2026-000001"
                )
            )
        ).scalars().all()
        audits = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "edit-draft-narrative")
            )
        ).scalars().all()
    await engine.dispose()

    assert len(drafts) == 1
    assert drafts[0].created_by == "analyst@sandbox.example.com"
    assert drafts[0].after_text == "Edited narrative with the fee mention."
    assert len(audits) == 1
    assert audits[0].meta.get("complaint_id") == "BCO-2026-000001"
    assert "before_excerpt" in (audits[0].diff or {})
    assert "after_excerpt" in (audits[0].diff or {})


@pytest.mark.asyncio
async def test_send_to_approvals_writes_row_and_is_idempotent(
    app_with_secret, test_database_url
):
    """First call creates a pending row; second call returns the same
    row with idempotent_replay=true."""

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.pending_approval import PendingApproval

    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/v1/internal/findings/BCO-2026-000001/send-to-approvals",
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:analyst",
            },
            json={"severity": "high", "actor_id": "analyst@sandbox.example.com"},
        )
        second = await client.post(
            "/v1/internal/findings/BCO-2026-000001/send-to-approvals",
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:analyst",
            },
            json={"severity": "high", "actor_id": "analyst@sandbox.example.com"},
        )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True
    assert first.json()["id"] == second.json()["id"]

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        rows = (
            await session.execute(
                select(PendingApproval).where(
                    PendingApproval.complaint_id == "BCO-2026-000001"
                )
            )
        ).scalars().all()
    await engine.dispose()
    assert len(rows) == 1
    assert rows[0].status == "pending"
    assert rows[0].severity == "high"


@pytest.mark.asyncio
async def test_sse_approvals_topic_rejects_supervisor_role(app_with_secret):
    """ADR 0040 §D7: approvals topic restricted to analyst + head; the
    supervisor scope alone receives 403."""

    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(
        transport=transport, base_url="http://test", timeout=2.0
    ) as client:
        response = await client.get(
            "/v1/internal/sse/approvals",
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:supervisor",
            },
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sse_approvals_topic_allows_head_role(app_with_secret):
    """The same approvals endpoint accepts head — minimum proof that
    the role check is permissive when the scope matches.

    Uses the ASGI head-only probe so we read headers without blocking
    on the SSE body (which by design never ends).
    """

    status, headers = await open_sse_head_only(
        app_with_secret,
        "/v1/internal/sse/approvals",
        {
            "Authorization": f"Bearer {SHARED_VAL}",
            "X-SBS-Role": "sbs:conduct:head",
        },
    )
    assert status == 200
    assert b"text/event-stream" in headers.get(b"content-type", b"")


@pytest.mark.asyncio
async def test_sse_unknown_topic_returns_404(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/sse/bogus",
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:head",
            },
        )
    assert response.status_code == 404
