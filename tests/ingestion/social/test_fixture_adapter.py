"""Fixture social adapter + runner (P-RESHAPE-6).

The fixture adapter reads the 14 seeded ``social_signals_fixture`` rows;
the runner anonymizes, resolves, classifies, and persists to the live
``social_signals`` table. Idempotent on (source, source_post_id).
Twitter/Meta stubs raise without credentials.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.social_signal import SocialSignal
from sbs_api.ingestion.social.fixture_adapter import FixtureSocialAdapter
from sbs_api.ingestion.social.meta_adapter import MetaAdapter
from sbs_api.ingestion.social.runner import run_social_ingestion
from sbs_api.ingestion.social.twitter_adapter import TwitterAdapter
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_fixture_ingests_14_signals_resolved_to_banco(
    test_database_url, db_schema
):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            results = await run_social_ingestion(
                session, adapters=[FixtureSocialAdapter(session)], now=NOW
            )
            await session.commit()

            rows = (
                await session.execute(select(SocialSignal))
            ).scalars().all()
    finally:
        await engine.dispose()

    assert results[0].fetched == 14
    assert results[0].inserted == 14
    assert len(rows) == 14
    # All 14 resolved to BANCO_DEMO_001 + carry the fraud indicators.
    for r in rows:
        assert r.detected_institution_codes == ["SBS-001234"]
        assert "PHISHING_KEYWORD" in r.detected_fraud_indicators
        # Stored text is anonymized (no raw handles).
        assert "@" not in r.post_text_es


@pytest.mark.asyncio
async def test_ingestion_is_idempotent(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await run_social_ingestion(
                session, adapters=[FixtureSocialAdapter(session)], now=NOW
            )
            await session.commit()
            second = await run_social_ingestion(
                session, adapters=[FixtureSocialAdapter(session)], now=NOW
            )
            await session.commit()
            rows = (await session.execute(select(SocialSignal))).scalars().all()
    finally:
        await engine.dispose()
    assert second[0].inserted == 0
    assert second[0].reused == 14
    assert len(rows) == 14  # no duplicates


@pytest.mark.asyncio
async def test_twitter_and_meta_stubs_raise_without_credentials(monkeypatch):
    monkeypatch.delenv("SBS_TWITTER_API_KEY", raising=False)
    monkeypatch.delenv("SBS_META_API_KEY", raising=False)
    with pytest.raises(NotImplementedError):
        await TwitterAdapter().fetch_recent(NOW)
    with pytest.raises(NotImplementedError):
        await MetaAdapter().fetch_recent(NOW)
