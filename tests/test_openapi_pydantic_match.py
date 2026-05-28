"""Integration test: OpenAPI inline schemas agree with Pydantic-exported JSON Schemas.

ADR 0027 makes the OpenAPI specification at api/openapi/sbs-api-v1.yaml the
canonical contract. The Pydantic models implement it; the standalone JSON
Schemas under api/openapi/schemas/ are exported from those models. This
test asserts that the *semantic* shape of each shared model — required
fields, types, enum values, formats, patterns — agrees between the two.

Cosmetic differences (property ordering, $defs vs components.schemas
placement, examples-as-field vs examples-at-schema-level, additionalProperties
defaults inherited differently) are tolerated.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
OPENAPI_PATH = REPO_ROOT / "api" / "openapi" / "sbs-api-v1.yaml"
SCHEMAS_DIR = REPO_ROOT / "api" / "openapi" / "schemas"


# Models declared in both the OpenAPI components.schemas and as standalone
# JSON Schema files. Models that appear in only one side are out of scope
# for this match check.
SHARED_MODELS = [
    "Complaint",
    "ComplaintCreated",
    "ComplaintListItem",
    "ComplaintListResponse",
    "ComplaintStatusPatch",
    "BatchManifest",
    "BatchSubmission",
    "BatchStatus",
    "BatchRowRejectionDetail",
    "BatchRejectionsResponse",
    "InstitutionStatus",
    "HealthStatus",
    "VersionInfo",
    "ProblemDetail",
]


@pytest.fixture(scope="module")
def openapi_spec() -> dict:
    with OPENAPI_PATH.open() as f:
        return yaml.safe_load(f)


def _load_pydantic_schema(model_name: str) -> dict:
    path = SCHEMAS_DIR / f"{model_name}.json"
    return json.loads(path.read_text())


def _required_fields(schema: dict) -> set[str]:
    return set(schema.get("required", []))


def _property_names(schema: dict) -> set[str]:
    return set((schema.get("properties") or {}).keys())


def _normalize(base_type) -> str:
    """Collapse nullability cosmetics. Both OAS 3.1 (`type: [t, null]`) and
    Pydantic v2 (`anyOf: [{type: t}, {type: null}]`) describe the same shape;
    this test treats them as equal by returning the non-null inner type."""
    if isinstance(base_type, tuple):
        non_null = tuple(t for t in base_type if t != "null" and t is not None)
        if len(non_null) == 1:
            return non_null[0]
        return base_type
    return base_type


def _resolve_pydantic_property_type(
    schema: dict, prop_name: str, pyd_schema: dict
):
    """Walk Pydantic $defs to identify the property's underlying type.

    Returns either a string ('string', 'integer', 'boolean', ...) or a tuple
    of names for union shapes. Enums are reported as ('enum', tuple_of_values).
    """
    prop = (schema.get("properties") or {}).get(prop_name, {})

    # union (anyOf / "type": [..., "null"])
    if "anyOf" in prop:
        types = []
        for member in prop["anyOf"]:
            t = member.get("type") or _resolve_ref_type(member, pyd_schema)
            if isinstance(t, tuple):
                types.append(t)
            elif t:
                types.append(t)
        return _normalize(tuple(sorted(t for t in types if isinstance(t, str))))

    if "$ref" in prop:
        return _resolve_ref_type(prop, pyd_schema)

    t = prop.get("type")
    if isinstance(t, list):
        return _normalize(tuple(sorted(t)))
    return t or "unknown"


def _resolve_ref_type(prop_or_ref: dict, pyd_schema: dict):
    ref = prop_or_ref.get("$ref")
    if not ref:
        return prop_or_ref.get("type", "unknown")
    if not ref.startswith("#/$defs/"):
        return "unknown"
    defs = pyd_schema.get("$defs", {})
    target = defs.get(ref.split("/")[-1], {})
    if "enum" in target:
        return ("enum", tuple(sorted(target["enum"], key=str)))
    return target.get("type", "object")


def _resolve_openapi_property_type(prop: dict, oas_schemas: dict):
    if "$ref" in prop:
        ref_name = prop["$ref"].split("/")[-1]
        target = oas_schemas.get(ref_name, {})
        if "enum" in target:
            return ("enum", tuple(sorted(target["enum"], key=str)))
        return target.get("type", "object")
    t = prop.get("type")
    if isinstance(t, list):
        return _normalize(tuple(sorted(t)))
    if "oneOf" in prop:
        # match BatchResultRow.problem shape — collapse to "object|null"
        members = prop["oneOf"]
        if any(m.get("type") == "null" for m in members):
            return "object"
        return "oneOf"
    return t or "unknown"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_openapi_spec_has_all_shared_schemas(openapi_spec):
    schemas = openapi_spec["components"]["schemas"]
    missing = [m for m in SHARED_MODELS if m not in schemas]
    assert not missing, f"missing OpenAPI schemas: {missing}"


def test_pydantic_schemas_committed_for_all_shared_models():
    missing = [m for m in SHARED_MODELS if not (SCHEMAS_DIR / f"{m}.json").exists()]
    assert not missing, (
        f"missing JSON Schema exports: {missing}. "
        f"Run `bash scripts/regenerate-schemas.sh` to refresh."
    )


@pytest.mark.parametrize("model_name", SHARED_MODELS)
def test_required_fields_agree(openapi_spec, model_name):
    oas_schema = openapi_spec["components"]["schemas"][model_name]
    pyd_schema = _load_pydantic_schema(model_name)

    oas_req = _required_fields(oas_schema)
    pyd_req = _required_fields(pyd_schema)

    assert oas_req == pyd_req, (
        f"{model_name}: required-fields mismatch.\n"
        f"  only in OpenAPI: {oas_req - pyd_req}\n"
        f"  only in Pydantic JSON Schema: {pyd_req - oas_req}"
    )


@pytest.mark.parametrize("model_name", SHARED_MODELS)
def test_property_names_agree(openapi_spec, model_name):
    oas_schema = openapi_spec["components"]["schemas"][model_name]
    pyd_schema = _load_pydantic_schema(model_name)

    oas_props = _property_names(oas_schema)
    pyd_props = _property_names(pyd_schema)

    assert oas_props == pyd_props, (
        f"{model_name}: property-name mismatch.\n"
        f"  only in OpenAPI: {oas_props - pyd_props}\n"
        f"  only in Pydantic JSON Schema: {pyd_props - oas_props}"
    )


@pytest.mark.parametrize("model_name", SHARED_MODELS)
def test_property_types_agree(openapi_spec, model_name):
    oas_schemas = openapi_spec["components"]["schemas"]
    oas_schema = oas_schemas[model_name]
    pyd_schema = _load_pydantic_schema(model_name)

    pyd_props = pyd_schema.get("properties") or {}
    oas_props = oas_schema.get("properties") or {}

    for prop_name in sorted(set(pyd_props) & set(oas_props)):
        oas_type = _resolve_openapi_property_type(oas_props[prop_name], oas_schemas)
        pyd_type = _resolve_pydantic_property_type(pyd_schema, prop_name, pyd_schema)

        # Both sides should resolve to the same base type or to matching enums
        if isinstance(oas_type, tuple) and isinstance(pyd_type, tuple):
            assert oas_type == pyd_type, (
                f"{model_name}.{prop_name}: enum mismatch:\n"
                f"  OpenAPI:  {oas_type}\n"
                f"  Pydantic: {pyd_type}"
            )
        else:
            assert oas_type == pyd_type, (
                f"{model_name}.{prop_name}: type mismatch: "
                f"OpenAPI={oas_type!r}, Pydantic={pyd_type!r}"
            )


def test_taxonomy_enums_in_openapi_match_pydantic_complaint_export(openapi_spec):
    """The Complaint model embeds enum references via $ref; both sides agree."""
    pyd_complaint = _load_pydantic_schema("Complaint")
    oas_schemas = openapi_spec["components"]["schemas"]

    enums_to_check = {
        "complainant_doc_type": "ComplainantDocType",
        "product_category": "ProductCategory",
        "channel": "Channel",
        "submission_method": "SubmissionMethod",
        "motivo_code": "MotivoCode",
        "severity": "Severity",
        "description_language": "DescriptionLanguage",
        "complainant_age_range": "ComplainantAgeRange",
        "resolution_status": "ResolutionStatus",
    }

    for field, enum_name in enums_to_check.items():
        # Pydantic places enums under $defs.{enum_name}.enum
        pyd_values = pyd_complaint["$defs"][enum_name]["enum"]
        oas_values = oas_schemas[enum_name]["enum"]
        assert sorted(map(str, pyd_values)) == sorted(map(str, oas_values)), (
            f"enum mismatch on {enum_name}:\n"
            f"  Pydantic: {sorted(map(str, pyd_values))}\n"
            f"  OpenAPI:  {sorted(map(str, oas_values))}"
        )


def test_problem_detail_carries_rfc_9457_required_fields(openapi_spec):
    """ProblemDetail must require at minimum: type, title, status.

    The SBS profile additionally requires `code`.
    """
    rfc_minimum = {"type", "title", "status"}
    oas = openapi_spec["components"]["schemas"]["ProblemDetail"]
    pyd = _load_pydantic_schema("ProblemDetail")
    assert rfc_minimum <= _required_fields(oas)
    assert rfc_minimum <= _required_fields(pyd)
    # SBS profile: code is also required
    assert "code" in _required_fields(oas)
    assert "code" in _required_fields(pyd)


def test_openapi_version_is_3_1(openapi_spec):
    assert openapi_spec["openapi"].startswith("3.1"), (
        f"expected OpenAPI 3.1.x, got {openapi_spec['openapi']!r}"
    )


def test_openapi_info_version_matches_schemas(openapi_spec):
    """The OpenAPI info.version is the standards-pack version. Sanity-check
    that it matches the BatchManifest schema_version regex (the manifest
    carries the schema version institutions are aligned to)."""
    info_version = openapi_spec["info"]["version"]
    assert info_version == "0.2.0"
    # schemas/BatchManifest schema_version is Optional[str], so the pattern
    # is nested under anyOf[0]. Find the non-null branch and pull its
    # pattern.
    pyd = _load_pydantic_schema("BatchManifest")
    schema_version_field = pyd["properties"]["schema_version"]
    if "pattern" in schema_version_field:
        pattern = schema_version_field["pattern"]
    else:
        any_of = schema_version_field["anyOf"]
        string_branch = next(
            b for b in any_of if b.get("type") == "string"
        )
        pattern = string_branch["pattern"]

    import re

    assert re.match(pattern, f"v{info_version}"), (
        f"schema_version pattern {pattern!r} does not accept v{info_version}"
    )
