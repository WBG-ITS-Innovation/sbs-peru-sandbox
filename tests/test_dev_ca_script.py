# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for scripts/dev-ca.sh — workstream A.

The script is the only sanctioned way to produce the dev CA + leaf
certs the sandbox uses. Tests assert: idempotency, --force regeneration,
expected file set, parseable certs, valid CA→leaf chain, distinct
thumbprints for the two leaves.
"""

from __future__ import annotations

import hashlib
import pathlib
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "dev-ca.sh"


def _run(args: list[str], *, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def dev_ca_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Copy the script's REPO_ROOT discipline into a tmp dir so generation
    lands under tmp_path/dev-ca, not the project's real dev-ca/.

    The script uses ``REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"``
    so we need to invoke it with a copy living under tmp_path/scripts/.
    """

    (tmp_path / "scripts").mkdir()
    shutil.copy2(SCRIPT, tmp_path / "scripts" / "dev-ca.sh")
    (tmp_path / "scripts" / "dev-ca.sh").chmod(0o755)
    return tmp_path


def test_script_produces_expected_files(dev_ca_root: pathlib.Path) -> None:
    proc = subprocess.run(
        ["bash", str(dev_ca_root / "scripts" / "dev-ca.sh")],
        cwd=dev_ca_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    ca_dir = dev_ca_root / "dev-ca"
    for name in (
        "ca.key",
        "ca.pem",
        "banco-demo-001-key.pem",
        "banco-demo-001.pem",
        "coopac-demo-002-key.pem",
        "coopac-demo-002.pem",
        "thumbprints.txt",
        "seed-certificates.sql",
    ):
        assert (ca_dir / name).exists(), f"missing {name}"


def test_script_is_idempotent(dev_ca_root: pathlib.Path) -> None:
    subprocess.run(
        ["bash", str(dev_ca_root / "scripts" / "dev-ca.sh")],
        cwd=dev_ca_root,
        check=True,
        capture_output=True,
    )
    banco_cert = dev_ca_root / "dev-ca" / "banco-demo-001.pem"
    fingerprint_before = hashlib.sha256(banco_cert.read_bytes()).hexdigest()

    # Re-run without --force.
    proc = subprocess.run(
        ["bash", str(dev_ca_root / "scripts" / "dev-ca.sh")],
        cwd=dev_ca_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "already present" in proc.stdout
    fingerprint_after = hashlib.sha256(banco_cert.read_bytes()).hexdigest()
    assert fingerprint_before == fingerprint_after


def test_force_regenerates(dev_ca_root: pathlib.Path) -> None:
    subprocess.run(
        ["bash", str(dev_ca_root / "scripts" / "dev-ca.sh")],
        cwd=dev_ca_root,
        check=True,
        capture_output=True,
    )
    banco_cert = dev_ca_root / "dev-ca" / "banco-demo-001.pem"
    before = hashlib.sha256(banco_cert.read_bytes()).hexdigest()

    proc = subprocess.run(
        ["bash", str(dev_ca_root / "scripts" / "dev-ca.sh"), "--force"],
        cwd=dev_ca_root,
        check=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    after = hashlib.sha256(banco_cert.read_bytes()).hexdigest()
    assert before != after, "--force did not regenerate the leaf cert"


def test_leaf_certs_chain_to_ca(dev_ca_root: pathlib.Path) -> None:
    subprocess.run(
        ["bash", str(dev_ca_root / "scripts" / "dev-ca.sh")],
        cwd=dev_ca_root,
        check=True,
        capture_output=True,
    )
    ca = dev_ca_root / "dev-ca" / "ca.pem"
    for leaf_name in ("banco-demo-001.pem", "coopac-demo-002.pem"):
        leaf = dev_ca_root / "dev-ca" / leaf_name
        verify = subprocess.run(
            ["openssl", "verify", "-CAfile", str(ca), str(leaf)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert verify.returncode == 0, verify.stderr
        assert "OK" in verify.stdout


def test_thumbprints_are_distinct(dev_ca_root: pathlib.Path) -> None:
    subprocess.run(
        ["bash", str(dev_ca_root / "scripts" / "dev-ca.sh")],
        cwd=dev_ca_root,
        check=True,
        capture_output=True,
    )
    thumbs = (dev_ca_root / "dev-ca" / "thumbprints.txt").read_text()
    lines = [line for line in thumbs.splitlines() if line and not line.startswith("#")]
    # Three demo institutions land with Prompt 8 (FINANCIERA_DEMO_003).
    assert len(lines) == 3
    tp_values = [line.split("\t")[2] for line in lines]
    assert len(set(tp_values)) == len(tp_values)
    for tp in tp_values:
        assert len(tp) == 64
        assert all(c in "0123456789abcdef" for c in tp)


def test_seed_sql_references_thumbprints(dev_ca_root: pathlib.Path) -> None:
    subprocess.run(
        ["bash", str(dev_ca_root / "scripts" / "dev-ca.sh")],
        cwd=dev_ca_root,
        check=True,
        capture_output=True,
    )
    sql = (dev_ca_root / "dev-ca" / "seed-certificates.sql").read_text()
    thumbs = (dev_ca_root / "dev-ca" / "thumbprints.txt").read_text()
    tp_values = [
        line.split("\t")[2]
        for line in thumbs.splitlines()
        if line and not line.startswith("#")
    ]
    for tp in tp_values:
        assert tp in sql
    assert "INSERT INTO institution_certificates" in sql
    assert "ON CONFLICT" in sql
