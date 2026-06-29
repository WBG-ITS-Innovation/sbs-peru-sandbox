# SPDX-License-Identifier: Apache-2.0
"""Social entity resolution + anonymization (P-RESHAPE-6)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.ingestion.social.entity_resolver import (
    normalize_alias,
    resolve_institution_codes,
)
from sbs_api.ingestion.social.runner import (
    anonymize_post_text,
    classify_fraud_indicators,
)
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


def test_normalize_alias_strips_at_and_scheme():
    assert normalize_alias("@BancoDemo") == "bancodemo"
    assert normalize_alias("https://bcodemo.pe") == "bcodemo.pe"
    assert normalize_alias("Banco Demo") == "banco demo"


def test_anonymize_strips_handles():
    out = anonymize_post_text("Ojo @cliente con la estafa de @BancoDemo")
    assert "@cliente" not in out
    assert "@BancoDemo" not in out
    assert "[HANDLE]" in out


def test_classify_fraud_indicators_keywords():
    codes = classify_fraud_indicators(
        "Es un phishing, cobran comisión no autorizada y hay app falsa"
    )
    assert "PHISHING_KEYWORD" in codes
    assert "UNAUTHORIZED_FEE_KEYWORD" in codes
    assert "FAKE_APP_KEYWORD" in codes


def test_classify_clean_text_no_indicators():
    assert classify_fraud_indicators("Buen servicio, gracias.") == []


@pytest.mark.asyncio
async def test_resolver_matches_brand_alias(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            # The conftest seeds "banco demo" / "bancodemo" / "bcodemo.pe"
            # aliases for SBS-001234.
            matched = await resolve_institution_codes(
                session, text="Cuidado con el phishing de Banco Demo"
            )
            handle = await resolve_institution_codes(
                session, text="ojo con @BancoDemo que cobra de mas"
            )
            none = await resolve_institution_codes(
                session, text="reclamo generico sin marca"
            )
    finally:
        await engine.dispose()
    assert matched == ["SBS-001234"]
    assert handle == ["SBS-001234"]
    assert none == []
