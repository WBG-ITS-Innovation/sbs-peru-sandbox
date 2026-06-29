# SPDX-License-Identifier: Apache-2.0
"""Cohort assignment tests — pure function, no DB."""

from __future__ import annotations

import pytest

from sbs_api.peer_risk.cohorts import (
    CohortAssignmentError,
    InstitutionSegment,
    SizeTier,
    assign_cohort,
)


def test_banco_large_maps_to_tier_1():
    c = assign_cohort(display_name="BANCO_DEMO_001", tier_classification="large")
    assert c.segment == InstitutionSegment.BANCO
    assert c.size_tier == SizeTier.TIER_1
    assert c.cohort_id == "BANCO:TIER_1"
    assert c.is_demo_seeded is True


def test_coopac_mid_maps_to_tier_2():
    c = assign_cohort(display_name="COOPAC_DEMO_002", tier_classification="mid")
    assert c.segment == InstitutionSegment.COOPAC
    assert c.size_tier == SizeTier.TIER_2
    assert c.cohort_id == "COOPAC:TIER_2"
    assert c.is_demo_seeded is True


def test_cmac_small_maps_to_tier_3():
    c = assign_cohort(display_name="CMAC_CUSCO", tier_classification="small")
    assert c.cohort_id == "CMAC:TIER_3"
    assert c.is_demo_seeded is False


def test_unknown_segment_maps_to_other():
    c = assign_cohort(display_name="SEGURO_XYZ", tier_classification="large")
    assert c.segment == InstitutionSegment.OTHER


def test_empty_display_name_raises():
    with pytest.raises(CohortAssignmentError):
        assign_cohort(display_name="", tier_classification="large")


def test_unknown_tier_raises():
    with pytest.raises(CohortAssignmentError):
        assign_cohort(display_name="BANCO_X", tier_classification="xlarge")


def test_product_mix_signature_stable_across_orders():
    c1 = assign_cohort(
        display_name="BANCO_A",
        tier_classification="large",
        motivo_codes_90d=["COBRO_INDEBIDO", "DEMORA_ATENCION", "OTRO"],
    )
    c2 = assign_cohort(
        display_name="BANCO_A",
        tier_classification="large",
        motivo_codes_90d=["OTRO", "COBRO_INDEBIDO", "DEMORA_ATENCION"],
    )
    assert c1.product_mix_signature == c2.product_mix_signature
    assert len(c1.product_mix_signature) == 12
