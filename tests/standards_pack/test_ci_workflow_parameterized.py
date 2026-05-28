"""The standards-pack CI workflow reads the version dynamically (CI fix).

A hardcoded tarball version in .github/workflows/standards-pack-validate.yml
broke build-and-verify after the v0.1.0 -> v0.2.0 bump. This guards
against re-hardcoding: the workflow must resolve the version from the
built manifest.json, not pin a literal.
"""

from __future__ import annotations

import pathlib
import re

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "standards-pack-validate.yml"


def _text() -> str:
    return WORKFLOW.read_text()


def test_workflow_is_valid_yaml():
    spec = yaml.safe_load(_text())
    assert "jobs" in spec
    assert "build-and-verify" in spec["jobs"]


def test_no_hardcoded_tarball_version():
    """No literal versioned tarball name — neither the stale v0.1.0 nor the
    current v0.2.0. The version must be substituted."""
    text = _text()
    assert "standards-pack-v0.1.0.tar.gz" not in text
    assert not re.search(r"standards-pack-v\d+\.\d+\.\d+\.tar\.gz", text), (
        "workflow still pins a hardcoded version in a tarball name"
    )
    assert not re.search(r"name:\s*standards-pack-v\d+\.\d+\.\d+\b", text)


def test_version_resolved_from_manifest():
    text = _text()
    assert "jq -r .version standards-pack/manifest.json" in text


def test_parameterized_substitutions_used():
    text = _text()
    # verify step uses the shell env var, upload step uses the step output.
    assert "standards-pack-v${PACK_VERSION}.tar.gz.sha256" in text
    assert "standards-pack-v${{ steps.pack.outputs.version }}.tar.gz" in text
