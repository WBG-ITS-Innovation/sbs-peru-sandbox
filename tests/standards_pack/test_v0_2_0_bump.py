# SPDX-License-Identifier: Apache-2.0
"""Standards pack / contract bump to v0.2.0 (P-RESHAPE-9).

Asserts the canonical OpenAPI contract carries the SupervisoryMetadata
block on ComplaintListItem (response-side) and that it is ABSENT from the
FI submission schema (Complaint). No DB or build required — parses the
committed artifacts directly.
"""

from __future__ import annotations

import json
import pathlib

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OPENAPI = REPO_ROOT / "api" / "openapi" / "sbs-api-v1.yaml"
SCHEMAS = REPO_ROOT / "api" / "openapi" / "schemas"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-standards-pack.sh"


def _spec() -> dict:
    return yaml.safe_load(OPENAPI.read_text())


def test_openapi_version_is_0_2_0():
    assert _spec()["info"]["version"] == "0.2.0"


def test_build_script_pack_version_is_0_2_0():
    text = BUILD_SCRIPT.read_text()
    assert 'PACK_VERSION="0.2.0"' in text


def test_supervisory_metadata_schema_present():
    schemas = _spec()["components"]["schemas"]
    assert "SupervisoryMetadata" in schemas
    sm = schemas["SupervisoryMetadata"]
    assert sm["additionalProperties"] is False
    props = sm["properties"]
    assert set(props) == {
        "system_signal",
        "system_signal_reasons",
        "validation_verdict",
        "triage_classified_at",
    }
    assert set(props["system_signal_reasons"]["items"]["enum"]) == {
        "OUTAGE_KEYWORD",
        "FRAUD_KEYWORD",
        "AMOUNT_THRESHOLD",
        "REGULATORY_BREACH_INDICATOR",
    }
    assert set(props["validation_verdict"]["enum"]) == {
        "VALID",
        "RECOVERABLE",
        "INSUFFICIENT",
        "INVALID",
    }


def test_supervisory_metadata_on_complaint_list_item_optional():
    cli = _spec()["components"]["schemas"]["ComplaintListItem"]
    assert "supervisory_metadata" in cli["properties"]
    # Read-only / optional — never required.
    assert "supervisory_metadata" not in cli.get("required", [])


def test_supervisory_metadata_absent_from_fi_submission_contract():
    """The FI submission schema (Complaint) is unchanged: no
    supervisory_metadata, additionalProperties:false preserved."""
    complaint = _spec()["components"]["schemas"]["Complaint"]
    assert "supervisory_metadata" not in complaint["properties"]
    assert complaint["additionalProperties"] is False


def test_committed_json_schemas_match_both_ways():
    cli = json.loads((SCHEMAS / "ComplaintListItem.json").read_text())
    assert "supervisory_metadata" in cli["properties"]
    assert "SupervisoryMetadata" in cli.get("$defs", {})

    complaint = json.loads((SCHEMAS / "Complaint.json").read_text())
    assert "supervisory_metadata" not in complaint["properties"]
    assert "SupervisoryMetadata" not in json.dumps(complaint)
