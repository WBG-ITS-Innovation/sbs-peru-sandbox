"""Test-fixture conformance — Workstream F.1 (closes Prompt 7 Day-2 deferral).

ADR 0028 amendment §test-fixture-conformance. The standard ``app``
fixture in conftest.py installs blanket overrides for
``verified_hmac_signature`` and ``verified_oauth_token_with_scope``
to keep ordinary endpoint tests simple. That blanket-override is a
recognised defect class — a refactor that introduces a *new* security
dependency might silently fall outside the bypass, or a test might
override the dependency to a different identity without anyone
realising security is being skipped.

This file holds the conformance check the Prompt 7 second-opinion
review asked for: no test file outside ``conftest.py`` may install an
override on the HMAC or OAuth dependencies *unless* it carries an
explicit ``# auth-bypass:`` opt-in marker explaining why, OR the file
is in the allowlist below.

The marker is a code-comment, not a pytest mark, because it must be
visible to a reviewer grepping the source and is robust to test
collection ordering.
"""

from __future__ import annotations

import pathlib
import re

import pytest

TESTS_DIR = pathlib.Path(__file__).resolve().parent

# Files that legitimately install dependency overrides outside conftest.
# Each entry includes the rationale so the allowlist itself is
# self-documenting.
_FILES_ALLOWED_TO_OVERRIDE_AUTH = {
    # The conftest is the canonical bypass owner; not in tests/ as a
    # collected file but listed for clarity.
    "conftest.py": "Standard fixture installs blanket bypasses.",
    # HMAC end-to-end tests legitimately exercise the real chain by
    # constructing their own app and overriding around the chain.
    "test_hmac_middleware.py": "Tests the HMAC dependency end-to-end.",
    "test_hmac_secret_rotation.py": "Tests HMAC secret rotation paths.",
    "test_auth_stub_failclosed.py": "Tests fail-closed of the auth stub.",
    "test_oauth_token_endpoint.py": "Tests OAuth token endpoint paths.",
    "test_oauth_cert_binding.py": "Tests OAuth cert-binding paths.",
    "test_oauth_scope_enforcement.py": "Tests OAuth scope enforcement.",
    "test_oauth_token_claims.py": "Tests OAuth token claims.",
    "test_mtls_dependency.py": "Tests mTLS dependency directly.",
    "test_mtls_integration.py": "Tests the full mTLS integration path.",
    "test_rate_limiter.py": "Tests the rate limiter with the real chain.",
    "test_rate_limiter_token_endpoint.py": "Tests the token-endpoint bucket.",
    # Cross-tenant tests legitimately swap the OAuth identity to a
    # different institution_id (still authenticated, different tenant).
    # These are not bypasses; they exercise the tenant-binding 404
    # contract.
    "test_batch_endpoint.py": "Cross-tenant identity swap for 404 test.",
    "test_batch_status_endpoint.py": "Cross-tenant identity swap for 404 test.",
}

_OVERRIDE_PATTERNS = (
    re.compile(r"dependency_overrides\s*\[\s*verified_hmac_signature\s*\]"),
    re.compile(
        r"dependency_overrides\s*\[\s*verified_oauth_token_with_scope\s*\("
    ),
    re.compile(
        r"dependency_overrides\s*\[\s*verified_mtls_subject\s*\]"
    ),
)

# Opt-in marker — a line containing this comment string declares the
# file as an explicit, reviewed bypass.
_OPT_IN_COMMENT = "# auth-bypass:"


def test_no_unsanctioned_auth_overrides():
    offenders: list[tuple[str, str]] = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        rel = path.name
        if rel in _FILES_ALLOWED_TO_OVERRIDE_AUTH:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pat in _OVERRIDE_PATTERNS:
            if pat.search(text):
                if _OPT_IN_COMMENT in text:
                    # File opts in via the explicit marker. The presence
                    # of a written rationale is the contract; a reviewer
                    # sees it on read.
                    break
                offenders.append((rel, pat.pattern))
                break
    assert not offenders, (
        "Unsanctioned auth-bypass overrides detected. Either add the "
        "file to _FILES_ALLOWED_TO_OVERRIDE_AUTH (with rationale) or "
        "place a `# auth-bypass: <why>` comment in the file. Offenders: "
        + ", ".join(f"{f} (matched {p})" for f, p in offenders)
    )


@pytest.mark.parametrize(
    "filename",
    sorted(_FILES_ALLOWED_TO_OVERRIDE_AUTH.keys()),
)
def test_allowlisted_files_still_exist(filename):
    """If a file leaves the tree, its allowlist entry should leave too.

    Stale allowlist entries weaken the conformance check; this test
    catches them.
    """

    if filename == "conftest.py":
        target = TESTS_DIR / filename
    else:
        target = TESTS_DIR / filename
    assert target.exists(), (
        f"Allowlist references {filename!r} but the file is missing. "
        "Remove the entry from _FILES_ALLOWED_TO_OVERRIDE_AUTH."
    )


_CONFTEST_REQUIRED_SYMBOLS = (
    "verified_hmac_signature",
    "verified_oauth_token_with_scope",
    "verified_mtls_subject",
    "dependency_overrides",
)


def test_conftest_installs_expected_overrides():
    """The conftest's blanket bypass remains the canonical entry point.

    Asserts the conftest still references every security dependency
    *and* the ``dependency_overrides`` machinery that installs the
    bypasses. A refactor that quietly removes one of them would
    silently re-engage the real chain for every endpoint test — easy
    to miss without a guardrail.

    Looser than the file-level regex used in
    :func:`test_no_unsanctioned_auth_overrides` because the conftest
    binds the dep to a local before installing the override (the loop
    over ALL_SCOPES), which the strict regex would not catch.
    """

    text = (TESTS_DIR / "conftest.py").read_text(encoding="utf-8")
    missing = [s for s in _CONFTEST_REQUIRED_SYMBOLS if s not in text]
    assert not missing, (
        f"conftest no longer references {missing!r}. Restore the bypass "
        "or move ownership of this conformance check."
    )
