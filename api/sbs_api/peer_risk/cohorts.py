# SPDX-License-Identifier: Apache-2.0
"""Peer cohort assignment.

A cohort is the comparison frame for "is this normal?". P-RESHAPE-3
defines a cohort by **institution segment** and **size tier** only —
product_mix_signature is computed and persisted for cockpit drilldown
but is not part of the matching key (the larger your basket of
products, the smaller your cohort would otherwise become, which
defeats the purpose).

Segments are derived from the institution's regulator-assigned
``display_name`` (BANCO_… / FINANCIERA_… / CMAC_… / COOPAC_…). Size
tier reuses the existing ``tier_classification`` column on
``InstitutionRecord`` (large → TIER_1, mid → TIER_2, small → TIER_3)
— P-RESHAPE-3 explicitly mentions ``portfolio_value`` as the canonical
derivation but the prototype does not yet carry that column; the
tier_classification mapping is the documented adaptation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class InstitutionSegment(str, Enum):
    BANCO = "BANCO"
    FINANCIERA = "FINANCIERA"
    CMAC = "CMAC"
    COOPAC = "COOPAC"
    OTHER = "OTHER"


class SizeTier(str, Enum):
    TIER_1 = "TIER_1"  # large
    TIER_2 = "TIER_2"  # mid
    TIER_3 = "TIER_3"  # small


# Leading keyword → segment. Covers both the legacy code form
# (BANCO_DEMO_001) and realistic spaced names (Banco Nuevo Horizonte;
# Cooperativa de Ahorro …; Caja Los Andes).
_SEGMENT_PREFIX = {
    "BANCO": InstitutionSegment.BANCO,
    "FINANCIERA": InstitutionSegment.FINANCIERA,
    "CMAC": InstitutionSegment.CMAC,
    "CAJA": InstitutionSegment.CMAC,
    "COOPAC": InstitutionSegment.COOPAC,
    "COOPERATIVA": InstitutionSegment.COOPAC,
}

_TIER_FROM_CLASSIFICATION = {
    "large": SizeTier.TIER_1,
    "mid": SizeTier.TIER_2,
    "small": SizeTier.TIER_3,
}


class CohortAssignmentError(ValueError):
    """Raised when an institution's metadata cannot be mapped to a cohort."""


@dataclass(frozen=True)
class Cohort:
    cohort_id: str
    segment: InstitutionSegment
    size_tier: SizeTier
    product_mix_signature: str  # informational only — not part of cohort_id

    @property
    def is_demo_seeded(self) -> bool:
        """True for the two cohorts pre-populated with synthetic peers
        for the demo (BANCO:TIER_1, COOPAC:TIER_2). The PRR forecast
        layer uses this to gate live forecasting vs PINNED_NULL."""
        return self.cohort_id in {"BANCO:TIER_1", "COOPAC:TIER_2"}


def _segment_from_display_name(display_name: str) -> InstitutionSegment:
    if not display_name:
        raise CohortAssignmentError("display_name required for segment derivation")
    # Leading token, splitting on the first space OR underscore so both the
    # legacy code form (BANCO_DEMO_001) and realistic names (Banco Nuevo
    # Horizonte del Perú) resolve to the same segment keyword.
    head = re.split(r"[ _]", display_name.strip(), maxsplit=1)[0].upper()
    return _SEGMENT_PREFIX.get(head, InstitutionSegment.OTHER)


def _size_tier_from_classification(value: str | None) -> SizeTier:
    if value is None:
        raise CohortAssignmentError(
            "institution tier_classification required for size tier derivation"
        )
    tier = _TIER_FROM_CLASSIFICATION.get(value.lower())
    if tier is None:
        raise CohortAssignmentError(
            f"unknown tier_classification {value!r}; expected one of "
            f"{sorted(_TIER_FROM_CLASSIFICATION)}"
        )
    return tier


def _product_mix_signature(motivo_codes_90d: Iterable[str]) -> str:
    """Top-3 motivos over the last 90 days, lower-cased and joined,
    hashed for an opaque-but-stable 12-char signature. Empty when no
    activity (cockpit renders that as "n/a")."""
    cleaned = [m.lower() for m in motivo_codes_90d if m]
    if not cleaned:
        return ""
    # Stable order — most-frequent first (caller is expected to pass
    # already-ordered; we resort here so input ordering does not
    # silently change the signature for the same set of codes).
    top3 = sorted(set(cleaned))[:3]
    h = hashlib.sha256("|".join(top3).encode("utf-8")).hexdigest()
    return h[:12]


def assign_cohort(
    *,
    display_name: str,
    tier_classification: str | None,
    motivo_codes_90d: Iterable[str] = (),
) -> Cohort:
    """Deterministic cohort assignment. Pure function — same inputs
    always produce the same Cohort, including the same opaque
    product_mix_signature."""
    segment = _segment_from_display_name(display_name)
    size_tier = _size_tier_from_classification(tier_classification)
    cohort_id = f"{segment.value}:{size_tier.value}"
    signature = _product_mix_signature(motivo_codes_90d)
    return Cohort(
        cohort_id=cohort_id,
        segment=segment,
        size_tier=size_tier,
        product_mix_signature=signature,
    )
