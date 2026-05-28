"""System-signal detector for the Triage agent.

A *system signal* is a per-complaint indication that the complaint
represents a regulator-level event — an outage, a fraud-scale loss,
a regulatory breach, or an amount above a hard threshold. Investigation
runs only when at least one rule fires.

This module is deliberately deterministic. The four rules below cover
the May-2026 cockpit reshape; an LLM-augmented detector is an explicit
out-of-scope follow-up (see the ``LLM augmentation hook`` comment).

Reasons are emitted as enum-like codes (``OUTAGE_KEYWORD``,
``FRAUD_KEYWORD``, ``AMOUNT_THRESHOLD``, ``REGULATORY_BREACH_INDICATOR``)
rather than as raw narrative excerpts. That keeps the PII-sentinel
contract clean: ``system_signal_reasons`` never replays the user's
words back out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


REASON_OUTAGE = "OUTAGE_KEYWORD"
REASON_FRAUD = "FRAUD_KEYWORD"
REASON_AMOUNT = "AMOUNT_THRESHOLD"
REASON_REGULATORY_BREACH = "REGULATORY_BREACH_INDICATOR"

# Hard amount ceiling for the Peruvian sandbox (PEN).
AMOUNT_THRESHOLD_PEN = 50_000.0

# Categories that gate the outage keyword rule. Outage language alone
# does not promote a complaint to system_signal — the underlying product
# must be one of the three digital-access channels.
_OUTAGE_PRODUCT_CATEGORIES = frozenset(
    {
        "servicio_digital",
        "transferencia",
        "acceso_cuenta",
        # Anexo 1-A canonical codes (uppercase) that map to the same
        # intent. Kept in sync with sbs_api.models.anexo_1a.ProductCategory.
        "DEPOSITOS",
        "TARJETA_DEBITO",
        "TARJETA_CREDITO",
    }
)

# Categories that gate the amount-threshold rule.
_HIGH_AMOUNT_CATEGORIES = frozenset(
    {
        "fraude",
        "transferencia_no_autorizada",
        # Anexo 1-A canonical motivo codes that map to the same intent.
        "OPERACION_NO_RECONOCIDA",
        "COBRO_INDEBIDO",
    }
)

_OUTAGE_PATTERN = re.compile(
    # The accent on caí- is optional so user-typed text without diacritics
    # ("caido", "caida") still matches the locked rule semantics.
    r"\b("
    r"sistema\s+(?:ca[ií][dt]o|no\s+funciona|inaccesible)"
    r"|plataforma\s+ca[ií][dt]a"
    r"|app\s+(?:ca[ií][dt]a|no\s+abre)"
    r"|no\s+puedo\s+acceder"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

_FRAUD_PATTERN = re.compile(
    r"\b("
    r"fraude\s+masivo"
    r"|hackeo"
    r"|suplantaci[oó]n"
    r"|estafa\s+generalizada"
    r"|m[uú]ltiples\s+cargos\s+no\s+autorizados"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True)
class SystemSignalResult:
    """Return type of :func:`detect_system_signal`.

    ``flag`` is True when at least one rule fires. ``reasons`` is the
    deduplicated, sorted list of reason codes (so audit playback is
    deterministic regardless of rule order).
    """

    flag: bool
    reasons: list[str]


def _dedupe_sorted(reasons: Iterable[str]) -> list[str]:
    return sorted(set(reasons))


def detect_system_signal(
    *,
    narrative: str | None,
    product_category: str | None = None,
    motivo_code: str | None = None,
    amount_claimed: float | None = None,
    regulatory_breach_indicator: bool | None = None,
) -> SystemSignalResult:
    """Apply the four deterministic system-signal rules.

    Inputs come from the canonical Annex 1-A record after taxonomy
    normalisation. ``narrative`` is the post-PII-redaction text the
    Triage agent already operates on; passing the raw text is a bug.

    The function never raises on malformed input — missing or empty
    fields simply mean the corresponding rule cannot fire.

    LLM augmentation hook
    ---------------------
    A future revision may add an LLM scorer that returns the same
    ``SystemSignalResult`` shape. The orchestrator gates on ``flag``
    only, so adding an extra reason code is backwards-compatible. The
    deterministic rules below stay as the audit baseline.
    """
    reasons: list[str] = []

    text = narrative or ""
    product = (product_category or "").strip()
    motivo = (motivo_code or "").strip()

    if text and _OUTAGE_PATTERN.search(text) and product in _OUTAGE_PRODUCT_CATEGORIES:
        reasons.append(REASON_OUTAGE)

    if text and _FRAUD_PATTERN.search(text):
        reasons.append(REASON_FRAUD)

    if (
        amount_claimed is not None
        and amount_claimed > AMOUNT_THRESHOLD_PEN
        and motivo in _HIGH_AMOUNT_CATEGORIES
    ):
        reasons.append(REASON_AMOUNT)

    if regulatory_breach_indicator is True:
        reasons.append(REASON_REGULATORY_BREACH)

    deduped = _dedupe_sorted(reasons)
    return SystemSignalResult(flag=bool(deduped), reasons=deduped)
