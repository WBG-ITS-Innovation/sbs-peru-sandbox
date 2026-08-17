# SPDX-License-Identifier: Apache-2.0
"""Deterministic regex-and-allowlist redaction engine.

Five entity kinds are detected:

* ``pii_id``    — Peruvian DNI (8 digits, optionally ``DNI`` prefix).
* ``pii_ruc``   — Peruvian RUC (11 digits, optionally ``RUC`` prefix). The
                  taxpayer identifier — issued to both individuals and firms,
                  so it can show up in granular complaint payloads when the
                  complainant is a small business / sole proprietor.
* ``pii_phone`` — Peruvian mobile (``+51 9XX XXX XXX``, ``9XX XXX XXX``,
  ``9XXXXXXXX``).
* ``pii_email`` — RFC-shaped email.
* ``pii_account`` — 12-19 digit account/card number, with optional
  spaces or hyphens. Amounts like ``S/ 700`` and ``S/.700`` and ``700
  soles`` are explicitly **not** matched because the engine refuses to
  treat a 3-4 digit number after a Soles marker as an account.
* ``pii_name``  — exact match against ``DEMO_KNOWN_NAMES``.

Replacements use stable tags numbered per kind in detection order::

    <PERSON_1>, <PERSON_2>, ...
    <DNI_1>, ...
    <PHONE_1>, ...
    <EMAIL_1>, ...
    <ACCOUNT_1>, ...

The output is a ``RedactionResult`` carrying the redacted text plus
one ``RedactionEntity`` per detection. The engine is pure (no I/O,
no random) so the same input always produces the same output, which
the redaction tests assert.

The schema validator at ``docs/schemas/agent_run.schema.json`` uses
the kinds ``pii_name``, ``pii_id``, ``pii_account``, ``pii_phone``,
``pii_email``, ``pii_address``. The kinds emitted here match those
names exactly so the anonymizer tool_call output validates against
the existing schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sbs_api.redaction.policy import (
    DEMO_KNOWN_NAMES,
    POLICY_VERSION,
    RedactionEntity,
)


# A 3-4 digit number immediately preceded by a Soles marker is an
# amount, not an account. The engine matches the marker shape so the
# account regex can exclude it cheaply.
_SOLES_AMOUNT_PATTERN = re.compile(
    r"(?:S/\.?\s*|S/\s+|PEN\s+|monto\s+(?:de\s+)?)\d{1,7}(?:[.,]\d{1,2})?"
    r"|\d{1,7}\s*soles",
    flags=re.IGNORECASE,
)

# Separator between an identifier keyword and its digits: optional
# whitespace, an optional ``:``/``.``/``-``, optional whitespace.
#
# Both whitespace runs are **bounded**. An unbounded ``\s*[:.-]?\s*``
# is polynomial-time on backtracking: N spaces can be split between the
# two stars N+1 ways, so a keyword followed by a long whitespace run and
# no digits costs O(N^2). Redaction runs on attacker-influenced
# complaint narratives, so that is a denial-of-service surface
# (CodeQL py/polynomial-redos). Bounding each run to 4 makes the
# separator cost constant.
#
# Degradation is safe: a keyword separated from its digits by more than
# four spaces no longer matches the *prefixed* branch, but the bare
# digit-run branch below still matches, so the identifier is still
# redacted — only the keyword itself stays outside the replaced span.
_ID_SEPARATOR = r"\s{0,4}[:.-]?\s{0,4}"

# DNI: 8 contiguous digits, with optional ``DNI`` prefix. The prefix
# itself is consumed so the replacement spans the whole construct.
_DNI_PATTERN = re.compile(
    rf"\bDNI{_ID_SEPARATOR}(\d{{8}})\b|\b(\d{{8}})\b",
    flags=re.IGNORECASE,
)

# RUC: 11 contiguous digits, with optional ``RUC`` prefix. Distinct from
# the 8-digit DNI and the 12-19-digit account/card range, so a bare
# 11-digit run is overwhelmingly a RUC in Peruvian financial-complaint
# narratives. The prefix is consumed.
_RUC_PATTERN = re.compile(
    rf"\bRUC{_ID_SEPARATOR}(\d{{11}})\b|\b(\d{{11}})\b",
    flags=re.IGNORECASE,
)

# Peruvian mobile phone: starts with 9, 9 digits total. International
# form ``+51`` prefix and free spacing supported.
_PHONE_PATTERN = re.compile(
    r"(?<![\d])(?:\+?51[\s\-]*)?9\d{2}[\s\-]*\d{3}[\s\-]*\d{3}(?![\d])"
)

# Email — simple form, sufficient for the sandbox payloads.
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")

# 12-19 digits with optional spaces or hyphens between groups. Account
# and card numbers both fall in this range. The engine excludes ranges
# inside Soles amount windows below.
_ACCOUNT_PATTERN = re.compile(r"(?:\d[\s\-]?){11,18}\d")


@dataclass(frozen=True)
class RedactionResult:
    """The output of one redaction pass.

    ``entities`` carries the matched values for the caller; the caller
    is responsible for stripping ``matched_value`` before exposing the
    list to any non-restricted surface. ``safe_entities()`` does the
    stripping in one call.
    """

    redacted_text: str
    entities: tuple[RedactionEntity, ...]
    policy_version: str

    def safe_entities(self) -> list[dict]:
        """Return entities with ``matched_value`` removed — safe for SSE / UI / audit."""

        return [
            {
                "kind": e.kind,
                "rule_id": e.rule_id,
                "span": list(e.span),
                "replacement": e.replacement,
                "confidence": e.confidence,
            }
            for e in self.entities
        ]

    def schema_redactions(self) -> list[dict]:
        """Shape the anonymizer tool_call's ``output.redactions`` field expects.

        Per ``docs/schemas/agent_run.schema.json`` the array items are
        ``{kind, span}`` only — no replacement / rule_id / matched value.
        """

        return [{"kind": e.kind, "span": list(e.span)} for e in self.entities]


def _soles_amount_ranges(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in _SOLES_AMOUNT_PATTERN.finditer(text)]


def _inside_any_range(span: tuple[int, int], ranges: list[tuple[int, int]]) -> bool:
    for start, end in ranges:
        if span[0] >= start and span[1] <= end:
            return True
    return False


def _ranges_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return not (a[1] <= b[0] or b[1] <= a[0])


def _build_replacement(kind: str, counters: dict[str, int]) -> str:
    label = {
        "pii_name": "PERSON",
        "pii_id": "DNI",
        "pii_ruc": "RUC",
        "pii_phone": "PHONE",
        "pii_email": "EMAIL",
        "pii_account": "ACCOUNT",
    }[kind]
    counters[kind] = counters.get(kind, 0) + 1
    return f"<{label}_{counters[kind]}>"


def _detect_names(text: str) -> list[RedactionEntity]:
    out: list[RedactionEntity] = []
    # Longest-first so "Carlos Rodríguez Mendoza" wins over "Carlos".
    for name in sorted(DEMO_KNOWN_NAMES, key=len, reverse=True):
        for match in re.finditer(re.escape(name), text):
            out.append(
                RedactionEntity(
                    kind="pii_name",
                    rule_id="known-name-allowlist",
                    span=(match.start(), match.end()),
                    replacement="",  # filled in during stitching
                    confidence=0.99,
                    matched_value=match.group(0),
                )
            )
    return out


def _detect_dni(text: str) -> list[RedactionEntity]:
    out: list[RedactionEntity] = []
    for match in _DNI_PATTERN.finditer(text):
        out.append(
            RedactionEntity(
                kind="pii_id",
                rule_id="dni-8-digits",
                span=(match.start(), match.end()),
                replacement="",
                confidence=0.95,
                matched_value=match.group(0),
            )
        )
    return out


def _detect_ruc(text: str) -> list[RedactionEntity]:
    out: list[RedactionEntity] = []
    for match in _RUC_PATTERN.finditer(text):
        out.append(
            RedactionEntity(
                kind="pii_ruc",
                rule_id="ruc-11-digits",
                span=(match.start(), match.end()),
                replacement="",
                # Slightly lower than DNI because an 11-digit run could
                # in principle be a coincidence; in Peruvian complaint
                # narratives it is overwhelmingly a RUC.
                confidence=0.92,
                matched_value=match.group(0),
            )
        )
    return out


def _detect_phone(text: str) -> list[RedactionEntity]:
    out: list[RedactionEntity] = []
    for match in _PHONE_PATTERN.finditer(text):
        out.append(
            RedactionEntity(
                kind="pii_phone",
                rule_id="pe-mobile-9-digits",
                span=(match.start(), match.end()),
                replacement="",
                confidence=0.9,
                matched_value=match.group(0),
            )
        )
    return out


def _detect_email(text: str) -> list[RedactionEntity]:
    out: list[RedactionEntity] = []
    for match in _EMAIL_PATTERN.finditer(text):
        out.append(
            RedactionEntity(
                kind="pii_email",
                rule_id="email-simple",
                span=(match.start(), match.end()),
                replacement="",
                confidence=0.95,
                matched_value=match.group(0),
            )
        )
    return out


def _detect_account(
    text: str, exclude_ranges: list[tuple[int, int]]
) -> list[RedactionEntity]:
    out: list[RedactionEntity] = []
    for match in _ACCOUNT_PATTERN.finditer(text):
        span = match.span()
        if _inside_any_range(span, exclude_ranges):
            continue
        # Sanity: count actual digits, not separators.
        digit_count = sum(ch.isdigit() for ch in match.group(0))
        if digit_count < 12 or digit_count > 19:
            continue
        out.append(
            RedactionEntity(
                kind="pii_account",
                rule_id="account-or-card-12-19-digits",
                span=span,
                replacement="",
                confidence=0.7,
                matched_value=match.group(0),
            )
        )
    return out


def _resolve_overlaps(entities: list[RedactionEntity]) -> list[RedactionEntity]:
    """Resolve span overlaps by preferring the higher-confidence detection.

    With ties, the longer span wins so ``Carlos Rodríguez Mendoza`` is
    preferred over a partial inside it.

    **This is O(n^2) in entity count, and the input cap is what makes that
    safe.** Every candidate is compared against every already-kept entity,
    so cost grows 4x per doubling of the entity count — measured at 2.9 s
    for 11,368 entities, 11.7 s for 22,737, and 47.7 s for 45,474 (64.6
    million ``_ranges_overlap`` calls at the middle figure). A long run of
    digits is an efficient way to manufacture entities, because each ~19
    digits yields one non-overlapping ``pii_account`` candidate.

    Callers must therefore bound their input. Both narrative surfaces cap
    free text at 8000 characters (``anexo_1a.Complaint.description_text``
    and ``demo_ingestion.DemoSubmissionRequest.narrative``), which holds the
    worst construable input to ~7 ms. ``tests/test_redaction_engine.py``
    pins both the cap and the runtime budget, so raising the cap or adding
    a caller that redacts unbounded text fails a test rather than becoming
    a quiet denial-of-service surface. If unbounded input ever becomes a
    requirement, replace this loop with a sweep over spans sorted by start
    offset — O(n log n) — rather than raising the budget.

    Background: docs/audit/2026-08-17-v02-check.md F2. This is distinct from
    the bounded-separator fix above, which closed a regex-backtracking
    (CodeQL py/polynomial-redos) issue in the DNI/RUC patterns; nothing here
    involves the regex engine.
    """

    sorted_ents = sorted(
        entities, key=lambda e: (-e.confidence, -(e.span[1] - e.span[0]), e.span[0])
    )
    kept: list[RedactionEntity] = []
    for ent in sorted_ents:
        if any(_ranges_overlap(ent.span, k.span) for k in kept):
            continue
        kept.append(ent)
    kept.sort(key=lambda e: e.span[0])
    return kept


def redact(text: str) -> RedactionResult:
    """Run the deterministic redaction pipeline against ``text``.

    Pure function. The same input always produces the same output.
    """

    if not text:
        return RedactionResult(redacted_text="", entities=(), policy_version=POLICY_VERSION)

    soles_ranges = _soles_amount_ranges(text)

    raw: list[RedactionEntity] = []
    raw.extend(_detect_names(text))
    raw.extend(_detect_email(text))
    raw.extend(_detect_phone(text))
    raw.extend(_detect_dni(text))
    raw.extend(_detect_ruc(text))
    raw.extend(_detect_account(text, exclude_ranges=soles_ranges))

    resolved = _resolve_overlaps(raw)

    # Assign stable replacements in detection order (left-to-right).
    counters: dict[str, int] = {}
    finalised: list[RedactionEntity] = []
    for ent in resolved:
        replacement = _build_replacement(ent.kind, counters)
        finalised.append(
            RedactionEntity(
                kind=ent.kind,
                rule_id=ent.rule_id,
                span=ent.span,
                replacement=replacement,
                confidence=ent.confidence,
                matched_value=ent.matched_value,
            )
        )

    # Stitch redacted text.
    out_parts: list[str] = []
    cursor = 0
    for ent in finalised:
        out_parts.append(text[cursor : ent.span[0]])
        out_parts.append(ent.replacement)
        cursor = ent.span[1]
    out_parts.append(text[cursor:])
    redacted_text = "".join(out_parts)

    return RedactionResult(
        redacted_text=redacted_text,
        entities=tuple(finalised),
        policy_version=POLICY_VERSION,
    )


def masked_preview(text: str, entities: tuple[RedactionEntity, ...]) -> str:
    """Build a browser-safe BEFORE preview from the raw text.

    Names are replaced with ``<PERSON:masked>``; DNI keeps only the
    last 4 digits as ``****NNNN``; phone keeps the last 3 digits;
    email keeps the first character before ``@``; account/card keeps
    the last 4 digits. This preview is what the UI's redaction_diff
    shows as "before" — full raw PII never reaches the browser.
    """

    if not text or not entities:
        return text

    def mask_value(ent: RedactionEntity) -> str:
        value = ent.matched_value
        if ent.kind == "pii_name":
            return "<PERSON:masked>"
        if ent.kind == "pii_id":
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 4:
                return "****" + digits[-4:]
            return "****"
        if ent.kind == "pii_ruc":
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 4:
                return "***" + digits[-4:]
            return "***"
        if ent.kind == "pii_phone":
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 3:
                return "***" + digits[-3:]
            return "***"
        if ent.kind == "pii_email":
            if "@" in value:
                head, tail = value.split("@", 1)
                return (head[:1] if head else "*") + "***@" + tail.split(".")[-1]
            return "***@***"
        if ent.kind == "pii_account":
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 4:
                return "****" + digits[-4:]
            return "****"
        return "***"

    out_parts: list[str] = []
    cursor = 0
    for ent in sorted(entities, key=lambda e: e.span[0]):
        out_parts.append(text[cursor : ent.span[0]])
        out_parts.append(mask_value(ent))
        cursor = ent.span[1]
    out_parts.append(text[cursor:])
    return "".join(out_parts)
