"""CI fixture tests for the Java + Go webhook verification snippets.

Each snippet is committed inline in its markdown recipe at
``standards-pack/recipes/webhook-verification-{java,go}.md``. This
test extracts the snippet from the markdown's first fenced code
block, writes it to a temp file, compiles it with the host
toolchain, and runs it against a fixture signed payload that the
server-side outbound signer produced. A mismatched canonical-request
shape or a wrong algorithm prefix produces VERIFY_FAIL (subprocess
exit != 0); a correct implementation produces VERIFY_OK (exit 0).

If the host toolchain is not available (no `java`/`javac`, no `go`),
the test ``pytest.skip``s. The CI workflow at
``.github/workflows/standards-pack-validate.yml`` installs both
toolchains via standard GitHub Actions setup steps so this test
runs there even when the local maintainer's machine lacks one.

Closes the dominant "translate Python to Java by eye" failure mode
that ADR 0038's E.1 was designed to prevent.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
from datetime import datetime, timezone

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RECIPES_DIR = REPO_ROOT / "standards-pack" / "recipes"


def _java_toolchain_works() -> bool:
    """Run `javac --version` and verify it produces a real version string.

    macOS ships /usr/bin/javac as a stub that prints "Unable to locate a
    Java Runtime" and exits 0 — `shutil.which` returns a path but the
    binary cannot actually compile anything. CI installs a real JDK
    via setup-java.
    """

    if shutil.which("javac") is None or shutil.which("java") is None:
        return False
    try:
        result = subprocess.run(
            ["javac", "--version"], capture_output=True, text=True, timeout=10
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0 and result.stdout.lower().startswith("javac ")


def _go_toolchain_works() -> bool:
    """Run `go version` and verify it produces a real version string."""

    if shutil.which("go") is None:
        return False
    try:
        result = subprocess.run(
            ["go", "version"], capture_output=True, text=True, timeout=10
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0 and "go version" in result.stdout


# ---- Fixture: generate a server-signed payload ------------------------------


@pytest.fixture(scope="module")
def signed_fixture() -> dict:
    """Produce a known-good canonical request + signature using the server signer.

    The fixture stays inside the test session — both the Java and Go
    snippets are invoked with the same inputs so a divergence between
    them is also catchable.
    """

    from sbs_api.webhook.signing import (
        build_outbound_canonical_request,
        compute_outbound_signature,
        signature_header,
    )

    secret = b"sandbox-shared-fixture-secret-2026"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    method = "POST"
    callback_path = "/sbs-callback"
    institution_id = "SBS-001234"
    body = b'{"event":"batch_completed","batch_id":"bch_e1_fixture"}'

    canonical = build_outbound_canonical_request(
        method=method,
        callback_path=callback_path,
        timestamp=timestamp,
        body=body,
        institution_id=institution_id,
    )
    sig_b64 = compute_outbound_signature(secret, canonical)
    header = signature_header(sig_b64)

    return {
        "secret": secret,
        "timestamp": timestamp,
        "method": method,
        "callback_path": callback_path,
        "institution_id": institution_id,
        "body": body,
        "signature_header": header,
    }


# ---- Snippet extraction helper ---------------------------------------------


_CODE_BLOCK_RE = re.compile(
    r"```(?P<lang>java|go)\n(?P<code>.*?)```",
    re.DOTALL,
)


def _extract_first_code_block(recipe_path: pathlib.Path, expected_lang: str) -> str:
    """Pull the first fenced code block of `expected_lang` from the markdown."""

    text = recipe_path.read_text(encoding="utf-8")
    for match in _CODE_BLOCK_RE.finditer(text):
        if match.group("lang") == expected_lang:
            return match.group("code")
    raise AssertionError(
        f"no `{expected_lang}` code block found in {recipe_path}"
    )


# ---- Java snippet ----------------------------------------------------------


@pytest.mark.skipif(
    not _java_toolchain_works(),
    reason="Java toolchain not actually runnable (macOS provides stubs that fail)",
)
def test_java_snippet_compiles_and_verifies_a_good_signature(
    tmp_path, signed_fixture
):
    """Extract → compile → run; expect VERIFY_OK on a good signature."""

    snippet = _extract_first_code_block(
        RECIPES_DIR / "webhook-verification-java.md", "java"
    )
    src = tmp_path / "SbsWebhookVerifier.java"
    src.write_text(snippet, encoding="utf-8")

    compile_result = subprocess.run(
        ["javac", str(src)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert compile_result.returncode == 0, (
        f"javac failed:\n{compile_result.stderr}"
    )

    run_result = subprocess.run(
        [
            "java",
            "-cp",
            str(tmp_path),
            "SbsWebhookVerifier",
            signed_fixture["secret"].decode("utf-8"),
            signed_fixture["timestamp"],
            signed_fixture["body"].decode("utf-8"),
            signed_fixture["institution_id"],
            signed_fixture["signature_header"],
            signed_fixture["method"],
            signed_fixture["callback_path"],
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert run_result.returncode == 0, (
        f"java verify failed:\nstdout: {run_result.stdout}\nstderr: {run_result.stderr}"
    )
    assert "VERIFY_OK" in run_result.stdout


@pytest.mark.skipif(
    not _java_toolchain_works(),
    reason="Java toolchain not actually runnable (macOS provides stubs that fail)",
)
def test_java_snippet_rejects_tampered_signature(tmp_path, signed_fixture):
    """Flip one byte of the signature header — snippet must non-zero exit."""

    snippet = _extract_first_code_block(
        RECIPES_DIR / "webhook-verification-java.md", "java"
    )
    src = tmp_path / "SbsWebhookVerifier.java"
    src.write_text(snippet, encoding="utf-8")
    subprocess.run(["javac", str(src)], check=True, cwd=tmp_path, capture_output=True)

    bad = signed_fixture["signature_header"][:-1] + (
        "A" if signed_fixture["signature_header"][-1] != "A" else "B"
    )
    run_result = subprocess.run(
        [
            "java",
            "-cp",
            str(tmp_path),
            "SbsWebhookVerifier",
            signed_fixture["secret"].decode("utf-8"),
            signed_fixture["timestamp"],
            signed_fixture["body"].decode("utf-8"),
            signed_fixture["institution_id"],
            bad,
            signed_fixture["method"],
            signed_fixture["callback_path"],
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert run_result.returncode != 0, (
        f"java snippet should have rejected a tampered signature; "
        f"stdout: {run_result.stdout}\nstderr: {run_result.stderr}"
    )


# ---- Go snippet ------------------------------------------------------------


@pytest.mark.skipif(
    not _go_toolchain_works(),
    reason="Go toolchain not actually runnable",
)
def test_go_snippet_compiles_and_verifies_a_good_signature(
    tmp_path, signed_fixture
):
    """Extract → build → run; expect VERIFY_OK on a good signature."""

    snippet = _extract_first_code_block(
        RECIPES_DIR / "webhook-verification-go.md", "go"
    )
    src = tmp_path / "sbs_webhook_verifier.go"
    src.write_text(snippet, encoding="utf-8")

    binary = tmp_path / "sbs_webhook_verifier"
    build_result = subprocess.run(
        ["go", "build", "-o", str(binary), str(src)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"GOCACHE": str(tmp_path / "gocache"), **__import__("os").environ},
    )
    assert build_result.returncode == 0, (
        f"go build failed:\n{build_result.stderr}"
    )

    run_result = subprocess.run(
        [
            str(binary),
            signed_fixture["secret"].decode("utf-8"),
            signed_fixture["timestamp"],
            signed_fixture["body"].decode("utf-8"),
            signed_fixture["institution_id"],
            signed_fixture["signature_header"],
            signed_fixture["method"],
            signed_fixture["callback_path"],
        ],
        capture_output=True,
        text=True,
    )
    assert run_result.returncode == 0, (
        f"go verify failed:\nstdout: {run_result.stdout}\nstderr: {run_result.stderr}"
    )
    assert "VERIFY_OK" in run_result.stdout


@pytest.mark.skipif(
    not _go_toolchain_works(),
    reason="Go toolchain not actually runnable",
)
def test_go_snippet_rejects_tampered_signature(tmp_path, signed_fixture):
    """Flip one byte of the signature header — snippet must non-zero exit."""

    snippet = _extract_first_code_block(
        RECIPES_DIR / "webhook-verification-go.md", "go"
    )
    src = tmp_path / "sbs_webhook_verifier.go"
    src.write_text(snippet, encoding="utf-8")
    binary = tmp_path / "sbs_webhook_verifier"
    subprocess.run(
        ["go", "build", "-o", str(binary), str(src)],
        check=True,
        cwd=tmp_path,
        env={"GOCACHE": str(tmp_path / "gocache"), **__import__("os").environ},
        capture_output=True,
    )

    bad = signed_fixture["signature_header"][:-1] + (
        "A" if signed_fixture["signature_header"][-1] != "A" else "B"
    )
    run_result = subprocess.run(
        [
            str(binary),
            signed_fixture["secret"].decode("utf-8"),
            signed_fixture["timestamp"],
            signed_fixture["body"].decode("utf-8"),
            signed_fixture["institution_id"],
            bad,
            signed_fixture["method"],
            signed_fixture["callback_path"],
        ],
        capture_output=True,
        text=True,
    )
    assert run_result.returncode != 0, (
        f"go snippet should have rejected a tampered signature; "
        f"stdout: {run_result.stdout}\nstderr: {run_result.stderr}"
    )


# ---- Recipe-format sanity checks (always run, no toolchain required) ------


def test_each_snippet_recipe_has_a_code_block():
    """Every recipe markdown must contain at least one fenced code block.

    Catches accidental deletion of the snippet, which would cause the
    extract step to fail with an unclear AssertionError. This test
    fails fast and prominently if the markdown drifts.
    """

    for recipe, expected_lang in [
        ("webhook-verification-java.md", "java"),
        ("webhook-verification-go.md", "go"),
    ]:
        path = RECIPES_DIR / recipe
        assert path.is_file(), f"recipe missing: {path}"
        _extract_first_code_block(path, expected_lang)


def test_pointer_recipes_exist_for_python_and_typescript():
    """The Python and TypeScript recipes are pointers to the helpers."""

    for fname in ("webhook-verification-python.md", "webhook-verification-typescript.md"):
        path = RECIPES_DIR / fname
        assert path.is_file(), f"pointer recipe missing: {path}"
        text = path.read_text(encoding="utf-8")
        assert "sdk-helpers/" in text
