"""DIValeVale Pass 1 — schema + completeness (deterministic, no LLM).

Evaluates a single FI-submitted record (a dict) against the locked
required-field rules and returns a verdict:

* VALID         — every rule passes
* RECOVERABLE   — amount_claimed missing OR narrative truncated, but
                  candidate signals exist in the narrative (Pass 2 will try)
* INSUFFICIENT  — cannot recover (narrative < 30 chars AND no candidate
                  amount AND no other recoverable field)
* INVALID       — hard schema failure (bad institution_code, bad enum, …)

Pure: no DB, no LLM, no I/O. The failed-rule codes feed the audit row +
the FI diagnostic report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

# Canonical motivo enum (mirror sbs_api.models.anexo_1a.MotivoCode) plus
# the lowercase names the P-RESHAPE prompts use.
_CANONICAL_MOTIVOS = {
    "COBRO_INDEBIDO",
    "OPERACION_NO_RECONOCIDA",
    "DEMORA_ATENCION",
    "INFORMACION_INCORRECTA",
    "INCUMPLIMIENTO_CONTRATO",
    "CALIDAD_SERVICIO",
    "PUBLICIDAD_ENGANOSA",
    "OTRO",
}
_PROMPT_MOTIVOS = {
    "cobros_indebidos",
    "fraude",
    "cargos_no_reconocidos",
    "comisiones_no_divulgadas",
    "transferencia_no_autorizada",
}
VALID_MOTIVOS = _CANONICAL_MOTIVOS | _PROMPT_MOTIVOS

# Motivos for which amount_claimed is required.
AMOUNT_REQUIRED_MOTIVOS = {
    "COBRO_INDEBIDO",
    "OPERACION_NO_RECONOCIDA",
    "cobros_indebidos",
    "fraude",
    "cargos_no_reconocidos",
    "comisiones_no_divulgadas",
    "transferencia_no_autorizada",
}

_INSTITUTION_CODE = re.compile(r"^[A-Z]{3}_[A-Z]+_\d{3}$")
_VALID_CURRENCIES = {"PEN", "USD"}
_NARRATIVE_MIN = 30
_CAPTURED_MAX_AGE = timedelta(days=90)

# Candidate-amount detector (used to decide RECOVERABLE vs INSUFFICIENT).
_AMOUNT_CANDIDATE = re.compile(
    r"(S\/?\.?\s?\d+(?:[.,]\d{1,2})?|USD\s?\d+(?:[.,]\d{1,2})?)", re.IGNORECASE
)
_DATE_CANDIDATE = re.compile(r"\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}")


class Verdict(str, Enum):
    VALID = "VALID"
    RECOVERABLE = "RECOVERABLE"
    INSUFFICIENT = "INSUFFICIENT"
    INVALID = "INVALID"


# Failed-rule codes (enum-like, audit-safe — no narrative text).
RULE_INSTITUTION_CODE = "INSTITUTION_CODE_INVALID"
RULE_CAPTURED_AT = "CAPTURED_AT_INVALID"
RULE_MOTIVO = "MOTIVO_CODE_INVALID"
RULE_NARRATIVE_SHORT = "NARRATIVE_TOO_SHORT"
RULE_NARRATIVE_MISSING = "NARRATIVE_MISSING"
RULE_AMOUNT_MISSING = "AMOUNT_CLAIMED_MISSING"
RULE_CURRENCY_MISSING = "CURRENCY_MISSING_OR_INVALID"
RULE_COMPLAINT_ID_MISSING = "COMPLAINT_ID_MISSING"


@dataclass(frozen=True)
class Pass1Result:
    verdict: Verdict
    failed_rules: list[str]
    # Recovery candidates Pass 2 can act on.
    recoverable_fields: list[str] = field(default_factory=list)
    amount_candidates: list[str] = field(default_factory=list)


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def run_pass1(record: dict[str, Any], *, now: datetime | None = None) -> Pass1Result:
    """Evaluate one record. ``now`` overridable for deterministic tests."""
    now = now or datetime.now(tz=timezone.utc)
    hard_failures: list[str] = []  # → INVALID
    soft_failures: list[str] = []  # completeness gaps → maybe RECOVERABLE
    recoverable_fields: list[str] = []

    institution = record.get("institution_code")
    if not institution or not _INSTITUTION_CODE.match(str(institution)):
        hard_failures.append(RULE_INSTITUTION_CODE)

    captured = _parse_iso(record.get("captured_at"))
    if captured is None or (now - captured) > _CAPTURED_MAX_AGE or captured > now + timedelta(days=1):
        hard_failures.append(RULE_CAPTURED_AT)

    motivo = record.get("motivo_code")
    if not motivo or motivo not in VALID_MOTIVOS:
        hard_failures.append(RULE_MOTIVO)

    if not record.get("complaint_id"):
        hard_failures.append(RULE_COMPLAINT_ID_MISSING)

    narrative = (record.get("narrative_es") or "").strip()
    narrative_short = len(narrative) < _NARRATIVE_MIN
    if not narrative:
        soft_failures.append(RULE_NARRATIVE_MISSING)
    elif narrative_short:
        soft_failures.append(RULE_NARRATIVE_SHORT)

    amount_candidates = _AMOUNT_CANDIDATE.findall(narrative)
    amount_candidates = [m if isinstance(m, str) else m[0] for m in amount_candidates]

    amount = record.get("amount_claimed")
    amount_required = motivo in AMOUNT_REQUIRED_MOTIVOS
    if amount_required and amount in (None, "", 0):
        soft_failures.append(RULE_AMOUNT_MISSING)
        if amount_candidates:
            recoverable_fields.append("amount_claimed")
    if amount not in (None, "", 0):
        currency = record.get("currency")
        if currency not in _VALID_CURRENCIES:
            # Currency is required when amount present — a hard rule.
            hard_failures.append(RULE_CURRENCY_MISSING)

    # Date recovery candidate (incident_date missing but a date in text).
    if not record.get("incident_date") and _DATE_CANDIDATE.search(narrative):
        recoverable_fields.append("incident_date")

    # --- Verdict ---
    if hard_failures:
        return Pass1Result(
            Verdict.INVALID,
            hard_failures + soft_failures,
            recoverable_fields,
            amount_candidates,
        )

    if not soft_failures:
        return Pass1Result(Verdict.VALID, [], [], amount_candidates)

    # Soft failures only — recoverable if there's something to recover.
    recoverable = bool(recoverable_fields) or (
        RULE_AMOUNT_MISSING in soft_failures and bool(amount_candidates)
    )
    # Narrative-too-short with a recoverable candidate is still recoverable;
    # narrative missing/short with NO candidates is INSUFFICIENT.
    if recoverable:
        return Pass1Result(
            Verdict.RECOVERABLE, soft_failures, recoverable_fields, amount_candidates
        )
    return Pass1Result(Verdict.INSUFFICIENT, soft_failures, [], amount_candidates)
