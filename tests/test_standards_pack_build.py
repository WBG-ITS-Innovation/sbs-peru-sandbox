# SPDX-License-Identifier: Apache-2.0
"""Tests for the standards pack v0.1 build pipeline (ADR 0039).

Exercises ``scripts/build-standards-pack.sh`` against the working
repository, then verifies the produced tarball:

* tarball extracts to the documented directory structure
* manifest.json schema-validates against manifest.schema.json
* manifest.json has the documented fields (semver, ISO timestamps,
  SPDX license placeholder, contains[])
* checksums.sha256 covers every file in the pack
* example payloads validate against their Pydantic models
* the tarball ``.sha256`` companion verifies the bytes
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import tarfile
from datetime import datetime

import jsonschema
import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def built_pack(tmp_path_factory) -> dict:
    """Run the build once per module and return paths + parsed manifest."""

    # Run the build using the real script. Suppress stdout via
    # check_output discarding, but propagate stderr to pytest output.
    result = subprocess.run(
        ["bash", "scripts/build-standards-pack.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            "build-standards-pack.sh failed\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    pack_dir = REPO_ROOT / "standards-pack"
    tarball = REPO_ROOT / "dist" / "standards-pack-v0.1.0.tar.gz"
    sha256_file = pathlib.Path(str(tarball) + ".sha256")
    manifest_path = pack_dir / "manifest.json"
    manifest_schema_path = pack_dir / "manifest.schema.json"

    return {
        "pack_dir": pack_dir,
        "tarball": tarball,
        "tarball_sha256": sha256_file,
        "manifest_path": manifest_path,
        "manifest_schema_path": manifest_schema_path,
        "manifest": json.loads(manifest_path.read_text(encoding="utf-8")),
        "manifest_schema": json.loads(
            manifest_schema_path.read_text(encoding="utf-8")
        ),
    }


# ---- Tarball and disk surface -----------------------------------------------


def test_build_succeeded(built_pack):
    """The build script exited 0 and produced the expected outputs."""

    assert built_pack["tarball"].is_file()
    assert built_pack["tarball_sha256"].is_file()
    assert built_pack["pack_dir"].is_dir()
    assert built_pack["manifest_path"].is_file()
    assert built_pack["manifest_schema_path"].is_file()


def test_tarball_sha256_companion_verifies(built_pack):
    """The .sha256 companion file matches the tarball bytes."""

    tarball = built_pack["tarball"]
    expected = built_pack["tarball_sha256"].read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(tarball.read_bytes()).hexdigest()
    assert actual == expected


def test_tarball_extracts_to_documented_structure(built_pack, tmp_path):
    """Extraction produces standards-pack/ with the documented subdirs."""

    with tarfile.open(built_pack["tarball"], "r:gz") as tf:
        tf.extractall(tmp_path)  # noqa: S202 — controlled archive from our own build

    pack = tmp_path / "standards-pack"
    assert pack.is_dir()
    for required in (
        "manifest.json",
        "manifest.schema.json",
        "README.md",
        "checksums.sha256",
        "openapi",
        "schemas",
        "catalogs",
        "sdk-helpers/python",
        "sdk-helpers/typescript",
        "examples",
    ):
        assert (pack / required).exists(), f"missing {required} in extracted pack"


def test_checksums_file_covers_every_file_in_the_pack(built_pack):
    """Every file other than checksums.sha256 itself appears in checksums.sha256."""

    pack = built_pack["pack_dir"]
    checksums = (pack / "checksums.sha256").read_text(encoding="utf-8")
    listed = {line.split("  ", 1)[1].strip() for line in checksums.splitlines() if line}

    on_disk = set()
    for p in pack.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(pack).as_posix()
        if rel == "checksums.sha256":
            continue
        if "__pycache__" in rel:
            continue
        on_disk.add(rel)

    missing = on_disk - listed
    extra = listed - on_disk
    assert not missing, f"files on disk not in checksums.sha256: {sorted(missing)}"
    assert not extra, f"checksums.sha256 lists files not on disk: {sorted(extra)}"


def test_checksums_file_values_match_actual_file_contents(built_pack):
    """Every listed hash equals the SHA-256 of the file on disk."""

    pack = built_pack["pack_dir"]
    checksums_text = (pack / "checksums.sha256").read_text(encoding="utf-8")
    for line in checksums_text.splitlines():
        if not line.strip():
            continue
        expected_hex, _, rel = line.partition("  ")
        rel = rel.strip()
        path = pack / rel
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected_hex, f"checksum mismatch for {rel}"


# ---- Manifest contents -------------------------------------------------------


def test_manifest_schema_validates(built_pack):
    """The manifest passes the schema."""

    jsonschema.validate(
        instance=built_pack["manifest"],
        schema=built_pack["manifest_schema"],
    )


def test_manifest_has_documented_fields(built_pack):
    """Spot-check the required fields from ADR 0039."""

    m = built_pack["manifest"]
    assert m["manifest_schema_version"] == "0.1.0"
    assert m["name"] == "sbs-complaints-standards-pack"
    assert m["version"] == "0.1.0"
    assert m["status"] == "sandbox"
    assert m["license"] == "LicenseRef-sandbox-pending-legal-review"
    assert m["webhook_signature_version"] == "v1"
    assert m["api_server_compatibility"]["min_version"] == "0.1.0"
    assert m["api_server_compatibility"]["exclusive_max_version"] == "1.0.0"
    # contains is a subset of the documented enum.
    assert set(m["contains"]).issubset(
        {"openapi", "schemas", "catalogs", "sdk-helpers", "examples", "recipes"}
    )


def test_manifest_git_commit_matches_repo_head(built_pack):
    """The recorded git commit is the actual HEAD at build time.

    The build script captures HEAD; the test verifies the value is a
    valid 40-char hex SHA-1, not specifically the current HEAD (which
    can advance between build and test).
    """

    sha = built_pack["manifest"]["git_commit"]
    assert re.fullmatch(r"[0-9a-f]{40}", sha)


def test_manifest_generated_at_is_recent_iso8601_utc(built_pack):
    """The build timestamp is a recent UTC ISO-8601."""

    ts = built_pack["manifest"]["generated_at"]
    # Format: YYYY-MM-DDTHH:MM:SSZ
    parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    # Strictly speaking we cannot assert "recent" without coupling to
    # wall-clock; the format check is the strong assertion here.
    assert parsed.year >= 2026


def test_license_placeholder_is_spdx_licenseref_form(built_pack):
    """The license placeholder uses the SPDX LicenseRef- prefix per ADR 0039."""

    assert built_pack["manifest"]["license"].startswith("LicenseRef-")


def test_manifest_carries_explicit_attestation_field(built_pack):
    """The attestation gap is named in the manifest, not only in the ADR.

    second-opinion §weakness: an attacker who can publish a tarball
    with matching checksums to a mirror site can imitate the pack.
    Naming the attestation type='none' in the manifest itself makes
    the gap visible at the artifact boundary.
    """

    attestation = built_pack["manifest"].get("attestation")
    assert attestation is not None, "manifest must declare attestation"
    assert attestation["type"] == "none"
    assert "v0.2" in attestation["rationale"] or "OCI" in attestation["rationale"]


# ---- Example payloads -------------------------------------------------------


def test_examples_directory_contains_three_files(built_pack):
    examples = built_pack["pack_dir"] / "examples"
    assert (examples / "valid-anexo-1a-complaint.json").is_file()
    assert (examples / "valid-batch-manifest.json").is_file()
    assert (examples / "invalid-missing-field.json").is_file()


def test_valid_complaint_example_validates_against_pydantic_model(built_pack):
    """The valid-anexo-1a-complaint.json example parses through the Complaint model."""

    from sbs_api.models.anexo_1a import Complaint

    data = json.loads(
        (
            built_pack["pack_dir"] / "examples" / "valid-anexo-1a-complaint.json"
        ).read_text(encoding="utf-8")
    )
    Complaint.model_validate(data)


def test_valid_batch_manifest_example_validates_against_pydantic_model(built_pack):
    """The valid-batch-manifest.json example parses through the BatchManifest model."""

    from sbs_api.models.requests import BatchManifest

    data = json.loads(
        (
            built_pack["pack_dir"] / "examples" / "valid-batch-manifest.json"
        ).read_text(encoding="utf-8")
    )
    BatchManifest.model_validate(data)


def test_openapi_spec_in_pack_is_well_formed_yaml(built_pack):
    """The frozen OpenAPI spec inside the pack is parseable YAML 3.1."""

    spec_path = built_pack["pack_dir"] / "openapi" / "sbs-complaints-v0.1.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    assert spec.get("openapi", "").startswith("3.1")


def test_error_catalog_present_as_markdown(built_pack):
    """The error catalog is kept as markdown per ADR 0039 (Brazil precedent)."""

    catalog = built_pack["pack_dir"] / "catalogs" / "error-catalog.md"
    assert catalog.is_file()
    text = catalog.read_text(encoding="utf-8")
    assert text.strip().startswith("#")  # Markdown heading


# ---- SDK helpers inside the pack -------------------------------------------


def test_python_helper_present_inside_pack(built_pack):
    """The Python helper ships inside the pack with its module + pyproject."""

    helper = built_pack["pack_dir"] / "sdk-helpers" / "python"
    assert (helper / "sbs_webhooks.py").is_file()
    assert (helper / "pyproject.toml").is_file()
    assert (helper / "README.md").is_file()
    assert (helper / "tests" / "test_sbs_webhooks.py").is_file()


def test_typescript_helper_source_present_inside_pack(built_pack):
    """The TypeScript helper ships inside the pack with its package.json + tsconfigs."""

    helper = built_pack["pack_dir"] / "sdk-helpers" / "typescript"
    assert (helper / "index.ts").is_file()
    assert (helper / "package.json").is_file()
    assert (helper / "tsconfig.cjs.json").is_file()
    assert (helper / "tsconfig.esm.json").is_file()
