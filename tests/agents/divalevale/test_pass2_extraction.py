# SPDX-License-Identifier: Apache-2.0
"""DIValeVale Pass 2 — regex + LLM-fallback extraction (no DB)."""

from __future__ import annotations

import pytest

from sbs_api.agents.divalevale.pass2_extraction import (
    LLM_MODEL_ID,
    RECOVERY_LLM,
    RECOVERY_REGEX,
    run_pass2,
)
from sbs_api.agents.providers.mock import MockProvider


def _provider_json(payload: str) -> MockProvider:
    return MockProvider.with_script({"divalevale": [{"text": payload}]})


@pytest.mark.asyncio
async def test_single_amount_recovered_by_regex():
    record = {"narrative_es": "Me cobraron S/ 245.00 indebidamente, reclamo."}
    res = await run_pass2(record, ["amount_claimed"], provider=MockProvider())
    by_field = {r.field_name: r for r in res.recoveries}
    assert by_field["amount_claimed"].value == 245.0
    assert by_field["amount_claimed"].recovery_source == RECOVERY_REGEX
    assert by_field["currency"].value == "PEN"
    assert res.llm_invoked is False


@pytest.mark.asyncio
async def test_usd_amount_currency():
    record = {"narrative_es": "Cargo de USD 80 no reconocido en mi cuenta."}
    res = await run_pass2(record, ["amount_claimed"], provider=MockProvider())
    by_field = {r.field_name: r for r in res.recoveries}
    assert by_field["amount_claimed"].value == 80.0
    assert by_field["currency"].value == "USD"


@pytest.mark.asyncio
async def test_ambiguous_amounts_invoke_llm_and_recover_on_high_confidence():
    record = {"narrative_es": "Primero S/ 100 y luego otro cargo de S/ 250."}
    provider = _provider_json(
        '{"amount": 250.0, "currency": "PEN", "confidence": 0.92, "reasoning_short_es": "el mayor"}'
    )
    res = await run_pass2(record, ["amount_claimed"], provider=provider)
    assert res.llm_invoked is True
    assert res.llm_model_id == "mock-1"
    by_field = {r.field_name: r for r in res.recoveries}
    assert by_field["amount_claimed"].value == 250.0
    assert by_field["amount_claimed"].recovery_source == RECOVERY_LLM


@pytest.mark.asyncio
async def test_ambiguous_low_confidence_flags_for_review():
    record = {"narrative_es": "Cargos de S/ 100 y S/ 250, no estoy seguro."}
    provider = _provider_json(
        '{"amount": 250.0, "currency": "PEN", "confidence": 0.40, "reasoning_short_es": "duda"}'
    )
    res = await run_pass2(record, ["amount_claimed"], provider=provider)
    assert res.llm_invoked is True
    assert res.flagged_for_review is True
    assert not res.recoveries


@pytest.mark.asyncio
async def test_account_references_flagged_not_filled():
    record = {"narrative_es": "Mi cuenta 12345678 tiene cargo S/ 50 raro."}
    res = await run_pass2(record, ["amount_claimed"], provider=MockProvider())
    # Account-looking digits are flagged, never proposed as a field value.
    assert "12345678" in res.account_references_flagged
    assert all(r.field_name != "account" for r in res.recoveries)


@pytest.mark.asyncio
async def test_date_recovery_regex():
    record = {"narrative_es": "El cargo ocurrió el 12/05/2026 sin autorización previa."}
    res = await run_pass2(record, ["incident_date"], provider=MockProvider())
    by_field = {r.field_name: r for r in res.recoveries}
    assert by_field["incident_date"].value == "12/05/2026"
