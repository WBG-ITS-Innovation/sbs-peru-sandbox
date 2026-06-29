# SPDX-License-Identifier: Apache-2.0
"""DIValeVale Pass 2 — narrative-field extraction (P-RESHAPE-8).

Invoked ONLY when Pass 1 returns RECOVERABLE. Tries targeted regex
extractions first; falls back to a single on-prem LLM call ONLY when the
amount regex finds *multiple* candidates (the genuinely ambiguous case).

Every recovered field carries provenance: ``recovery_source``
(REGEX | LLM | NONE) + ``recovery_confidence``. PII is redacted before
the LLM sees the narrative. Malformed LLM output never crashes and never
blocks ingestion — the record is flagged for review instead.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sbs_api.agents.providers.base import ModelProvider
from sbs_api.redaction.engine import redact

log = logging.getLogger(__name__)

LLM_MODEL_ID = "qwen2.5-14b-onprem"
LLM_CONFIDENCE_THRESHOLD = 0.85

_AMOUNT = re.compile(
    r"(?:S\/?\.?\s?|USD\s?)(\d+(?:[.,]\d{1,2})?)", re.IGNORECASE
)
_AMOUNT_WITH_CCY = re.compile(
    r"(S\/?\.?\s?\d+(?:[.,]\d{1,2})?|USD\s?\d+(?:[.,]\d{1,2})?)", re.IGNORECASE
)
_DATE = re.compile(r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})\b")
_ACCOUNT_LOOSE = re.compile(r"\b\d{4,}\b")

RECOVERY_REGEX = "REGEX"
RECOVERY_LLM = "LLM"
RECOVERY_NONE = "NONE"


@dataclass(frozen=True)
class RecoveredField:
    field_name: str
    value: Any
    field_recovered: bool
    recovery_source: str
    recovery_confidence: float
    original_field_value: Any = None


@dataclass(frozen=True)
class Pass2Result:
    recoveries: list[RecoveredField] = field(default_factory=list)
    flagged_for_review: bool = False
    llm_invoked: bool = False
    llm_model_id: str | None = None
    account_references_flagged: list[str] = field(default_factory=list)

    def as_audit(self) -> dict[str, Any]:
        return {
            "recoveries": [
                {
                    "field": r.field_name,
                    "value": r.value,
                    "recovery_source": r.recovery_source,
                    "recovery_confidence": r.recovery_confidence,
                    "field_recovered": r.field_recovered,
                }
                for r in self.recoveries
            ],
            "flagged_for_review": self.flagged_for_review,
            "llm_invoked": self.llm_invoked,
            "account_references_flagged": self.account_references_flagged,
        }


def _currency_from_token(token: str) -> str:
    return "USD" if token.upper().startswith("USD") else "PEN"


def _to_float(num: str) -> float:
    # Normalise "1.234,56" / "1,234.56" / "245.00" → float. Treat the last
    # separator as the decimal mark.
    s = num.strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Comma as decimal if it has 1-2 trailing digits.
        if re.search(r",\d{1,2}$", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    return float(s)


async def _llm_disambiguate_amount(
    provider: ModelProvider, *, redacted_narrative: str
) -> dict[str, Any] | None:
    """Single on-prem call; structured amount/currency/confidence. Returns
    None on any malformed output (caller flags the record)."""
    prompt = (
        "Extrae el monto reclamado del texto. Devuelve SOLO JSON con las "
        "claves amount (float|null), currency ('PEN'|'USD'|null), confidence "
        "(0-1), reasoning_short_es (str). Texto: " + redacted_narrative
    )
    try:
        resp = await provider.complete(
            messages=[
                {"role": "system", "content": "Eres DIValeVale, validador de datos de la SBS."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=200,
            agent_name="divalevale",
        )
        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        # Shape validation — malformed → None (flag, don't crash).
        if "amount" not in parsed or "confidence" not in parsed:
            return None
        amount = parsed.get("amount")
        if amount is not None:
            amount = float(amount)
        conf = float(parsed.get("confidence"))
        currency = parsed.get("currency")
        if currency not in (None, "PEN", "USD"):
            return None
        return {
            "amount": amount,
            "currency": currency,
            "confidence": conf,
            "model_id": resp.model_id,
        }
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        log.warning("DIValeVale Pass2 LLM malformed output — flagging: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("DIValeVale Pass2 LLM call failed — flagging: %s", exc)
        return None


async def run_pass2(
    record: dict[str, Any],
    recoverable_fields: list[str],
    *,
    provider: ModelProvider,
) -> Pass2Result:
    """Attempt recovery on a RECOVERABLE record."""
    narrative = (record.get("narrative_es") or "").strip()
    recoveries: list[RecoveredField] = []
    flagged = False
    llm_invoked = False
    llm_model_id: str | None = None

    # --- Amount ---
    if "amount_claimed" in recoverable_fields:
        tokens = _AMOUNT_WITH_CCY.findall(narrative)
        tokens = [t if isinstance(t, str) else t[0] for t in tokens]
        nums = _AMOUNT.findall(narrative)
        if len(tokens) == 1 and nums:
            recoveries.append(
                RecoveredField(
                    field_name="amount_claimed",
                    value=_to_float(nums[0]),
                    field_recovered=True,
                    recovery_source=RECOVERY_REGEX,
                    recovery_confidence=1.0,
                )
            )
            recoveries.append(
                RecoveredField(
                    field_name="currency",
                    value=_currency_from_token(tokens[0]),
                    field_recovered=True,
                    recovery_source=RECOVERY_REGEX,
                    recovery_confidence=1.0,
                )
            )
        elif len(tokens) > 1:
            # Ambiguous → single on-prem LLM call on the REDACTED narrative.
            llm_invoked = True
            redacted = redact(narrative).redacted_text
            out = await _llm_disambiguate_amount(provider, redacted_narrative=redacted)
            if out is None:
                flagged = True  # FLAGGED_FOR_REVIEW
            else:
                llm_model_id = out["model_id"]
                if out["amount"] is not None and out["confidence"] >= LLM_CONFIDENCE_THRESHOLD:
                    recoveries.append(
                        RecoveredField(
                            field_name="amount_claimed",
                            value=out["amount"],
                            field_recovered=True,
                            recovery_source=RECOVERY_LLM,
                            recovery_confidence=out["confidence"],
                        )
                    )
                    if out["currency"]:
                        recoveries.append(
                            RecoveredField(
                                field_name="currency",
                                value=out["currency"],
                                field_recovered=True,
                                recovery_source=RECOVERY_LLM,
                                recovery_confidence=out["confidence"],
                            )
                        )
                else:
                    flagged = True  # low confidence → review

    # --- Date ---
    if "incident_date" in recoverable_fields:
        m = _DATE.search(narrative)
        if m:
            recoveries.append(
                RecoveredField(
                    field_name="incident_date",
                    value=m.group(1),
                    field_recovered=True,
                    recovery_source=RECOVERY_REGEX,
                    recovery_confidence=0.9,
                )
            )

    # --- Account references: flag only, never propose-fill (too ambiguous). ---
    account_refs = _ACCOUNT_LOOSE.findall(narrative)

    return Pass2Result(
        recoveries=recoveries,
        flagged_for_review=flagged,
        llm_invoked=llm_invoked,
        llm_model_id=llm_model_id,
        account_references_flagged=account_refs,
    )
