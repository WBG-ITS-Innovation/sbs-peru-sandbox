"""Deterministic data-quality rules for the P11A demo ingestion path.

Rules are pure functions over the **redacted** narrative plus the
structured Anexo-1A-like fields the demo endpoint receives. None of
the rules calls an LLM; none consumes raw PII (the narrative passed
in here has already been through ``sbs_api.redaction.redact``).

Rule output shape::

    DataQualityReport(
        errors=[{"rule_id", "field", "message"}],
        warnings=[{"rule_id", "field", "message"}],
        suggested_enrichments=[{"rule_id", "field", "suggested_value", "evidence"}],
        extracted_fields={"amount_claimed_extracted": "...", ...},
        policy_version="dq-demo-v1",
    )

The rule IDs are stable across runs so an audit dashboard can pin a
filter on a specific rule. The full set lives at module scope under
``RULES`` so docs/tests can enumerate them without importing the
report shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

POLICY_VERSION = "dq-demo-v1"


# Sandbox-scoped allow-lists. Real production checking would join
# against the canonical Anexo 1-A code lists; for the demo we cover
# the codes Cockpit/Findings already exercise plus a small handful of
# alternative spellings (e.g., motivo codes the seed uses).
_KNOWN_PRODUCTS = frozenset(
    {
        "DEPOSITOS",
        "CREDITOS",
        "TARJETA_CREDITO",
        "TARJETA_DEBITO",
        "SEGUROS",
        "AFP_PENSIONES",
        "COOPAC",
        "OTRO",
    }
)
_KNOWN_MOTIVOS = frozenset(
    {
        "COBRO_INDEBIDO",
        "OPERACION_NO_RECONOCIDA",
        "DEMORA_ATENCION",
        "INFORMACION_INCORRECTA",
        "INCUMPLIMIENTO_CONTRATO",
        "CALIDAD_SERVICIO",
        "PUBLICIDAD_ENGANOSA",
        "OTRO",
    }
)
_KNOWN_CHANNEL_OPERATION = frozenset(
    {
        "AGENCIA",
        "CAJERO",
        "APP_MOVIL",
        "WEB",
        "POS",
        "AGENTE_CORRESPONSAL",
        "OTRO",
    }
)

_WALLET_PATTERN = re.compile(
    r"\b(billetera(?:\s+digital)?|wallet|yape|plin)\b",
    flags=re.IGNORECASE,
)

# Amount extraction patterns. Order matters — the first match wins.
# Each pattern captures the numeric portion so the report can carry
# the extracted value.
_AMOUNT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("amount-pen-symbol-dot", re.compile(r"S/\.?\s*(\d{1,7}(?:[.,]\d{1,2})?)", flags=re.IGNORECASE)),
    ("amount-pen-prefix", re.compile(r"\bPEN\s+(\d{1,7}(?:[.,]\d{1,2})?)\b", flags=re.IGNORECASE)),
    ("amount-soles-suffix", re.compile(r"\b(\d{1,7}(?:[.,]\d{1,2})?)\s*soles\b", flags=re.IGNORECASE)),
    ("amount-monto-keyword", re.compile(r"\bmonto\s+(?:de\s+)?(\d{1,7}(?:[.,]\d{1,2})?)\b", flags=re.IGNORECASE)),
)

_NARRATIVE_MIN_LENGTH = 40

RULES: tuple[str, ...] = (
    "missing-institution-complaint-id",
    "missing-narrative",
    "missing-product",
    "missing-motive",
    "unknown-product-code",
    "unknown-motive-code",
    "missing-channel-operation",
    "unknown-channel-operation-code",
    "wallet-clue-without-mobile-channel",
    "amount-mentioned-without-claim",
    "narrative-too-short",
)


@dataclass
class DataQualityReport:
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    suggested_enrichments: list[dict[str, Any]] = field(default_factory=list)
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    policy_version: str = POLICY_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "suggested_enrichments": list(self.suggested_enrichments),
            "extracted_fields": dict(self.extracted_fields),
            "policy_version": self.policy_version,
        }

    @property
    def has_blocking_errors(self) -> bool:
        return len(self.errors) > 0


def _add_error(report: DataQualityReport, rule_id: str, field_name: str, message: str) -> None:
    report.errors.append({"rule_id": rule_id, "field": field_name, "message": message})


def _add_warning(report: DataQualityReport, rule_id: str, field_name: str, message: str) -> None:
    report.warnings.append({"rule_id": rule_id, "field": field_name, "message": message})


def _add_suggested(
    report: DataQualityReport,
    rule_id: str,
    field_name: str,
    suggested_value: Any,
    evidence: str,
) -> None:
    report.suggested_enrichments.append(
        {
            "rule_id": rule_id,
            "field": field_name,
            "suggested_value": suggested_value,
            "evidence": evidence,
        }
    )


def _normalise(value: Any) -> str | None:
    """Return a stripped string or None for empty values.

    Defensive: callers pass dicts of mixed types. None / blank / pure
    whitespace all collapse to None so the rule predicates stay simple.
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def run_checks(
    *,
    fields: dict[str, Any],
    redacted_narrative: str,
) -> DataQualityReport:
    """Run the DQ rules and return a structured report.

    ``fields`` carries the structured Anexo-1A-like fields the demo
    endpoint received. ``redacted_narrative`` is the post-redaction
    text — the engine never sees raw PII.
    """

    report = DataQualityReport()

    institution_complaint_id = _normalise(fields.get("institution_complaint_id"))
    narrative = _normalise(redacted_narrative)
    product = _normalise(fields.get("product"))
    motive = _normalise(fields.get("motive"))
    channel_operation = _normalise(fields.get("channel_operation"))
    amount_claimed = _normalise(fields.get("amount_claimed"))

    # --- structural errors ---------------------------------------------
    if not institution_complaint_id:
        _add_error(
            report,
            "missing-institution-complaint-id",
            "institution_complaint_id",
            "Missing institution_complaint_id (Anexo 1-A COD_REC).",
        )
    if not narrative:
        _add_error(
            report,
            "missing-narrative",
            "narrative",
            "Missing narrative (Anexo 1-A DET_REC).",
        )
    if not product:
        _add_error(
            report,
            "missing-product",
            "product",
            "Missing product (Anexo 1-A PRD_SBS).",
        )
    if not motive:
        _add_error(
            report,
            "missing-motive",
            "motive",
            "Missing motive (Anexo 1-A MOT_SBS).",
        )

    # --- code-list checks -----------------------------------------------
    if product and product.upper() not in _KNOWN_PRODUCTS:
        _add_warning(
            report,
            "unknown-product-code",
            "product",
            f"Product '{product}' is not in the sandbox-known product code-list.",
        )
    if motive and motive.upper() not in _KNOWN_MOTIVOS:
        _add_warning(
            report,
            "unknown-motive-code",
            "motive",
            f"Motive '{motive}' is not in the sandbox-known motive code-list.",
        )

    if not channel_operation:
        _add_warning(
            report,
            "missing-channel-operation",
            "channel_operation",
            "Missing channel_operation (Anexo 1-A CNL_OPE).",
        )
    elif channel_operation.upper() not in _KNOWN_CHANNEL_OPERATION:
        _add_warning(
            report,
            "unknown-channel-operation-code",
            "channel_operation",
            f"channel_operation '{channel_operation}' is not in the sandbox-known list.",
        )

    # --- narrative-derived heuristics -----------------------------------
    if narrative and len(narrative) < _NARRATIVE_MIN_LENGTH:
        _add_warning(
            report,
            "narrative-too-short",
            "narrative",
            f"Narrative is shorter than {_NARRATIVE_MIN_LENGTH} characters; supervisors usually need more context.",
        )

    if narrative:
        wallet_match = _WALLET_PATTERN.search(narrative)
        if wallet_match:
            current = (channel_operation or "").upper()
            if not channel_operation or current in {"", "OTRO", "APP_MOVIL"}:
                # APP_MOVIL is generic — we still suggest WALLET when a
                # wallet keyword is in the narrative so a supervisor can
                # see the clue surfaced.
                _add_suggested(
                    report,
                    "wallet-clue-without-mobile-channel",
                    "channel_operation",
                    "APP_MOVIL",
                    evidence=f"narrative mentions '{wallet_match.group(1)}'",
                )
                _add_warning(
                    report,
                    "wallet-clue-without-mobile-channel",
                    "channel_operation",
                    "Narrative mentions a digital wallet but the channel_operation is missing or generic.",
                )

        if not amount_claimed:
            for rule_id, pattern in _AMOUNT_PATTERNS:
                match = pattern.search(narrative)
                if match:
                    extracted = match.group(1).replace(",", ".")
                    report.extracted_fields["amount_claimed_extracted"] = extracted
                    _add_suggested(
                        report,
                        rule_id,
                        "amount_claimed",
                        extracted,
                        evidence=match.group(0),
                    )
                    break

    return report
