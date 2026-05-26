"""Deterministic data-quality checks for the P11A demo ingestion path.

ADR 0045 documents the rule contract. The checker is regex-and-rule
based — no LLM, no third-party service. The policy version string is
attached to every report so a downstream auditor can re-run the same
rules against the redacted narrative.
"""

from sbs_api.data_quality.checks import (
    POLICY_VERSION,
    DataQualityReport,
    run_checks,
)

__all__ = [
    "POLICY_VERSION",
    "DataQualityReport",
    "run_checks",
]
