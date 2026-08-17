# SPDX-License-Identifier: Apache-2.0
"""DIValeVale Pass 2 LLM malformed-output safety (P-RESHAPE-8). DB-backed.

When the on-prem model returns malformed JSON for the ambiguous-amount
disambiguation, DIValeVale must NOT crash and must NOT block ingestion —
the record is flagged for review and the audit records the failure.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.divalevale.agent import validate_tier1_record
from sbs_api.agents.divalevale.pass2_extraction import run_pass2
from sbs_api.agents.providers.mock import MockProvider
from sbs_api.db.models.validation_audit import ValidationAudit
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

# A record whose narrative has TWO amounts → forces the LLM path.
_AMBIGUOUS = {
    "complaint_id": "BCO-AMB-1",
    "institution_code": "BCO_DEMO_001",
    "captured_at": "2026-05-27T10:00:00Z",
    "motivo_code": "COBRO_INDEBIDO",
    "narrative_es": "Primero S/ 100 y después otro cargo de S/ 250 sin aviso.",
}


def _bad_provider(text: str) -> MockProvider:
    return MockProvider.with_script({"divalevale": [{"text": text}]})


async def _sender_ok(req) -> tuple[int, str]:
    return 200, "ok"


@pytest.mark.asyncio
async def test_malformed_json_flags_not_crash():
    res = await run_pass2(
        dict(_AMBIGUOUS), ["amount_claimed"], provider=_bad_provider("not json at all{{")
    )
    assert res.llm_invoked is True
    assert res.flagged_for_review is True
    assert res.recoveries == []


@pytest.mark.asyncio
async def test_missing_keys_flags():
    res = await run_pass2(
        dict(_AMBIGUOUS), ["amount_claimed"], provider=_bad_provider('{"foo": 1}')
    )
    assert res.flagged_for_review is True


@pytest.mark.asyncio
async def test_audit_records_flagged_record(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await validate_tier1_record(
                session,
                record=dict(_AMBIGUOUS, amount_claimed=None, currency=None),
                sbs_institution_id="SBS-001234",
                provider=_bad_provider("garbage"),
                sender=_sender_ok,
            )
            await session.commit()
            audit = (
                await session.execute(
                    select(ValidationAudit).where(
                        ValidationAudit.complaint_id == "BCO-AMB-1"
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    # No crash; record did not silently proceed; flagged_for_review recorded.
    assert res.flagged_for_review is True
    assert len(audit) == 1
    assert audit[0].pass2_invoked is True
