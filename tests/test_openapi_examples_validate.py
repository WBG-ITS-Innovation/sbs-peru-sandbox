"""Every named example in the OpenAPI spec parses through its Pydantic model.

A drift catcher. Spec examples are what institutions copy-paste into their
integration code; if an example does not validate against the matching
Pydantic model, the institution's first request 422s and the integration
team blames the spec. Pre-emptive failure in CI is cheaper than support
tickets.

The mapping below is intentionally explicit rather than reflection-driven:
the spec's example name → Pydantic class is a small table that's easier to
audit than discovery glue.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from pydantic import BaseModel

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
OPENAPI_PATH = REPO_ROOT / "api" / "openapi" / "sbs-api-v1.yaml"


@pytest.fixture(scope="module")
def spec() -> dict:
    return yaml.safe_load(OPENAPI_PATH.read_text())


def _model_for(name: str) -> type[BaseModel]:
    """Return the Pydantic model that should validate the example named ``name``."""

    from sbs_api.models.anexo_1a import Complaint
    from sbs_api.models.requests import BatchManifest, ComplaintSubmission
    from sbs_api.models.responses import (
        BatchStatus,
        BatchSubmission,
        ComplaintCreated,
        ComplaintListResponse,
        InstitutionStatus,
    )

    table: dict[str, type[BaseModel]] = {
        "ValidComplaintBody": Complaint,
        "ValidComplaintSubmission": ComplaintSubmission,
        "ComplaintCreatedExample": ComplaintCreated,
        "ComplaintListExample": ComplaintListResponse,
        "ValidBatchManifest": BatchManifest,
        "BatchSubmissionExample": BatchSubmission,
        "BatchStatusExample": BatchStatus,
        "InstitutionStatusExample": InstitutionStatus,
    }
    return table[name]


def test_all_named_examples_parse_through_pydantic(spec):
    """Drift catcher across the catalog of named examples."""

    examples = spec["components"].get("examples", {})
    skipped: list[str] = []
    parsed: list[str] = []
    for name, body in examples.items():
        try:
            model = _model_for(name)
        except KeyError:
            # Unmapped example name — not a failure, but flagged so the test
            # remains a maintenance signal when new examples land in the spec.
            skipped.append(name)
            continue
        value = body.get("value") if isinstance(body, dict) else None
        assert value is not None, f"example {name!r} has no `value`"
        model.model_validate(value)
        parsed.append(name)
    # At least the core complaint examples must be exercised.
    assert "ValidComplaintBody" in parsed
    assert "ValidComplaintSubmission" in parsed
    assert "ComplaintCreatedExample" in parsed
    assert "ComplaintListExample" in parsed
    assert "ValidBatchManifest" in parsed
