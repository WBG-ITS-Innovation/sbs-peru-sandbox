# SPDX-License-Identifier: Apache-2.0
"""Deterministic PII redaction for the P11A demo ingestion path.

ADR 0044 documents the policy choice. The engine is regex-and-allowlist
based — no LLM, no third-party service, no cloud call. The policy
version string is part of every redacted output so a downstream auditor
can re-run the same policy against the raw narrative kept in
``raw_complaints``.
"""

from sbs_api.redaction.engine import RedactionResult, redact
from sbs_api.redaction.policy import POLICY_VERSION, RedactionEntity

__all__ = [
    "POLICY_VERSION",
    "RedactionEntity",
    "RedactionResult",
    "redact",
]
