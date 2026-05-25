"""Demo / sandbox-only live ingestion orchestrator (P11A).

Wires deterministic PII redaction (``sbs_api.redaction``) and the
deterministic data-quality checker (``sbs_api.data_quality``) into a
single end-to-end pipeline that the LiveIngestionPanel calls. This
endpoint is **not** the production institutional surface — that path
remains the existing ``POST /v1/complaints`` with the full mTLS +
OAuth + HMAC auth chain. ADR 0044 (redaction) and ADR 0045 (data
quality) record the policy details.
"""

from sbs_api.demo_ingestion.orchestrator import (
    DemoIngestionOutcome,
    run_demo_ingestion,
)

__all__ = ["DemoIngestionOutcome", "run_demo_ingestion"]
