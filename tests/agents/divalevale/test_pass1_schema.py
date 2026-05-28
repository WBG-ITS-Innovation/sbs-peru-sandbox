"""DIValeVale Pass 1 — verdict matrix + per-rule failures (pure, no DB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sbs_api.agents.divalevale.pass1_schema import (
    RULE_AMOUNT_MISSING,
    RULE_CAPTURED_AT,
    RULE_CURRENCY_MISSING,
    RULE_INSTITUTION_CODE,
    RULE_MOTIVO,
    RULE_NARRATIVE_SHORT,
    Verdict,
    run_pass1,
)

NOW = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)


def _rec(**kw):
    base = {
        "complaint_id": "BCO-X",
        "institution_code": "BCO_DEMO_001",
        "captured_at": "2026-05-27T10:00:00Z",
        "motivo_code": "CALIDAD_SERVICIO",
        "narrative_es": "x" * 40,
    }
    base.update(kw)
    return base


def test_valid_record():
    r = run_pass1(_rec(), now=NOW)
    assert r.verdict == Verdict.VALID
    assert r.failed_rules == []


def test_recoverable_amount_in_narrative():
    r = run_pass1(
        _rec(
            motivo_code="COBRO_INDEBIDO",
            narrative_es="Me cobraron S/ 245.00 sin aviso, presento reclamo formal.",
        ),
        now=NOW,
    )
    assert r.verdict == Verdict.RECOVERABLE
    assert "amount_claimed" in r.recoverable_fields
    assert r.amount_candidates == ["S/ 245.00"]


def test_insufficient_short_narrative_no_candidates():
    r = run_pass1(
        _rec(motivo_code="COBRO_INDEBIDO", narrative_es="se me cobró mal"),
        now=NOW,
    )
    assert r.verdict == Verdict.INSUFFICIENT
    assert RULE_NARRATIVE_SHORT in r.failed_rules
    assert RULE_AMOUNT_MISSING in r.failed_rules


def test_invalid_bad_institution_code():
    r = run_pass1(_rec(institution_code="BANCO_DEMO_001"), now=NOW)
    # "BANCO" is 5 letters; the locked regex wants exactly 3.
    assert r.verdict == Verdict.INVALID
    assert RULE_INSTITUTION_CODE in r.failed_rules


def test_invalid_bad_motivo():
    r = run_pass1(_rec(motivo_code="NOT_A_MOTIVO"), now=NOW)
    assert r.verdict == Verdict.INVALID
    assert RULE_MOTIVO in r.failed_rules


def test_invalid_captured_at_too_old():
    old = (NOW - timedelta(days=120)).isoformat()
    r = run_pass1(_rec(captured_at=old), now=NOW)
    assert r.verdict == Verdict.INVALID
    assert RULE_CAPTURED_AT in r.failed_rules


def test_currency_required_when_amount_present():
    r = run_pass1(
        _rec(motivo_code="COBRO_INDEBIDO", amount_claimed=245.0, currency="EUR"),
        now=NOW,
    )
    assert r.verdict == Verdict.INVALID
    assert RULE_CURRENCY_MISSING in r.failed_rules


def test_amount_present_with_valid_currency_is_valid():
    r = run_pass1(
        _rec(motivo_code="COBRO_INDEBIDO", amount_claimed=245.0, currency="PEN"),
        now=NOW,
    )
    assert r.verdict == Verdict.VALID


def test_non_amount_motivo_does_not_require_amount():
    r = run_pass1(_rec(motivo_code="DEMORA_ATENCION"), now=NOW)
    assert r.verdict == Verdict.VALID
