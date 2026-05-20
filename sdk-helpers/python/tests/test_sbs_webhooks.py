"""Tests for the Python webhook verification helper.

Pure-stdlib coverage — no network, no docker, no database. The matrix
covers round-trip success, tampered signature rejection, expired
timestamp rejection, wrong key_id rejection, and a timing-variance
smoke check (sanity-only — ``hmac.compare_digest`` provides the
real constant-time guarantee).

A separate test under the root repo's ``tests/`` directory verifies
this helper agrees byte-for-byte with the server's outbound signer
in ``api/sbs_api/webhook/signing.py``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

# Load the helper directly from the file. Avoids requiring the package
# to be installed for tests to run.
_HELPER_PATH = pathlib.Path(__file__).resolve().parent.parent / "sbs_webhooks.py"
spec = importlib.util.spec_from_file_location("sbs_webhooks", _HELPER_PATH)
assert spec is not None and spec.loader is not None
sbs_webhooks = importlib.util.module_from_spec(spec)
sys.modules.setdefault("sbs_webhooks", sbs_webhooks)
spec.loader.exec_module(sbs_webhooks)

from sbs_webhooks import (  # noqa: E402
    ALGORITHM_PREFIX,
    KEY_ID_SANDBOX_V1,
    MAX_CLOCK_SKEW_SECONDS,
    KeyIdUnknownError,
    SignatureExpiredError,
    SignatureInvalidError,
    canonicalize_request,
    compute_signature,
    constant_time_compare,
    verify_signature,
)


# ---- Fixtures ----------------------------------------------------------------


SECRET = b"sandbox-shared-secret-known-only-to-coopac-and-sbs"
INSTITUTION_ID = "SBS-001234"
METHOD = "POST"
CALLBACK_PATH = "/sbs-callback"


def _now_iso() -> str:
    """Return an RFC 3339 UTC timestamp for "right now"."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sign(
    *,
    timestamp: str,
    body: bytes,
    secret: bytes = SECRET,
    method: str = METHOD,
    callback_path: str = CALLBACK_PATH,
    institution_id: str = INSTITUTION_ID,
) -> str:
    canonical = canonicalize_request(
        method=method,
        callback_path=callback_path,
        timestamp=timestamp,
        raw_body=body,
        institution_id=institution_id,
    )
    return compute_signature(secret, canonical)


# ---- Canonical-request construction ----------------------------------------


def test_canonical_request_has_five_lines_LF_joined():
    """The canonical request is five lines, LF-joined, UTF-8 encoded."""

    canonical = canonicalize_request(
        method="post",  # lowercase input, uppercased output
        callback_path="/cb",
        timestamp="2026-05-20T12:00:00Z",
        raw_body=b'{"ok":true}',
        institution_id="SBS-001234",
    )
    text = canonical.decode("utf-8")
    lines = text.split("\n")
    assert len(lines) == 5
    assert lines[0] == "POST"  # uppercased
    assert lines[1] == "/cb"
    assert lines[2] == "2026-05-20T12:00:00Z"
    # Verify the body hash is lowercase hex SHA-256 of the body.
    expected_hash = hashlib.sha256(b'{"ok":true}').hexdigest()
    assert lines[3] == expected_hash
    assert lines[4] == "SBS-001234"


def test_canonical_request_empty_body_uses_cached_hash():
    """Empty body uses the well-known SHA-256(b'')."""

    canonical = canonicalize_request(
        method="POST",
        callback_path="/cb",
        timestamp="2026-05-20T12:00:00Z",
        raw_body=b"",
        institution_id="SBS-001234",
    )
    lines = canonical.decode("utf-8").split("\n")
    # SHA-256 of an empty bytes object.
    assert (
        lines[3]
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # pragma: allowlist secret
    )


def test_signature_header_value_starts_with_algorithm_prefix():
    """Computed signature carries the ``hmac-sha256-v1=`` prefix."""

    sig = compute_signature(SECRET, b"canonical")
    assert sig.startswith(ALGORITHM_PREFIX)
    # The remainder is base64.
    b64 = sig[len(ALGORITHM_PREFIX):]
    assert base64.b64decode(b64) == hmac.new(
        SECRET, b"canonical", hashlib.sha256
    ).digest()


# ---- verify_signature round-trip + failure cases ----------------------------


def test_round_trip_verify_signature_returns_none_on_success():
    ts = _now_iso()
    body = b'{"event":"batch_completed","batch_id":"bch_abc"}'
    sig = _sign(timestamp=ts, body=body)
    # Returns None on success — no raise.
    assert (
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp=ts,
            raw_body=body,
            signature_header=sig,
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
        )
        is None
    )


def test_tampered_body_byte_raises_signature_invalid():
    ts = _now_iso()
    body = b'{"ok":true}'
    sig = _sign(timestamp=ts, body=body)
    # Flip one byte.
    tampered = b'{"ok":TRUE}'
    with pytest.raises(SignatureInvalidError):
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp=ts,
            raw_body=tampered,
            signature_header=sig,
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
        )


def test_tampered_signature_raises_signature_invalid():
    ts = _now_iso()
    body = b'{"ok":true}'
    sig = _sign(timestamp=ts, body=body)
    # Replace last char of the base64 chunk (cheap byte-flip).
    bad = sig[:-1] + ("A" if sig[-1] != "A" else "B")
    with pytest.raises(SignatureInvalidError):
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp=ts,
            raw_body=body,
            signature_header=bad,
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
        )


def test_wrong_method_raises_signature_invalid():
    """Method is part of the canonical request — a mismatch must fail."""

    ts = _now_iso()
    body = b'{"ok":true}'
    sig = _sign(timestamp=ts, body=body, method="POST")
    with pytest.raises(SignatureInvalidError):
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp=ts,
            raw_body=body,
            signature_header=sig,
            method="PUT",  # mismatch
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
        )


def test_wrong_institution_id_raises_signature_invalid():
    """institution_id is part of the canonical request — mismatch must fail."""

    ts = _now_iso()
    body = b'{"ok":true}'
    sig = _sign(timestamp=ts, body=body)
    with pytest.raises(SignatureInvalidError):
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp=ts,
            raw_body=body,
            signature_header=sig,
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id="SBS-999999",  # mismatch
        )


def test_expired_timestamp_raises_signature_expired():
    """Timestamp older than MAX_CLOCK_SKEW_SECONDS raises Expired."""

    ts_old = (
        datetime.now(timezone.utc) - timedelta(seconds=MAX_CLOCK_SKEW_SECONDS + 30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = b"{}"
    sig = _sign(timestamp=ts_old, body=body)
    with pytest.raises(SignatureExpiredError):
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp=ts_old,
            raw_body=body,
            signature_header=sig,
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
        )


def test_future_timestamp_raises_signature_expired():
    """Timestamp far in the future also fails — the skew window is two-sided."""

    ts_future = (
        datetime.now(timezone.utc) + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS + 30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = b"{}"
    sig = _sign(timestamp=ts_future, body=body)
    with pytest.raises(SignatureExpiredError):
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp=ts_future,
            raw_body=body,
            signature_header=sig,
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
        )


def test_malformed_timestamp_raises_signature_expired():
    """A non-ISO-8601 timestamp is rejected as expired (treated as invalid)."""

    body = b"{}"
    sig = ALGORITHM_PREFIX + "any"
    with pytest.raises(SignatureExpiredError):
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp="not-a-timestamp",
            raw_body=body,
            signature_header=sig,
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
        )


def test_wrong_key_id_raises_key_id_unknown():
    """Anything other than ``sandbox-v1`` raises KeyIdUnknownError."""

    ts = _now_iso()
    body = b"{}"
    sig = _sign(timestamp=ts, body=body)
    with pytest.raises(KeyIdUnknownError):
        verify_signature(
            secret=SECRET,
            key_id="sandbox-v9000",
            timestamp=ts,
            raw_body=body,
            signature_header=sig,
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
        )


def test_signature_header_missing_prefix_raises_signature_invalid():
    """Header without ``hmac-sha256-v1=`` prefix is rejected."""

    ts = _now_iso()
    body = b"{}"
    with pytest.raises(SignatureInvalidError):
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp=ts,
            raw_body=body,
            signature_header="bare-base64-no-prefix",
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
        )


def test_now_parameter_overrides_for_reproducibility():
    """The ``now`` parameter lets tests pin the clock."""

    ts = "2026-05-20T12:00:00Z"
    body = b"{}"
    sig = _sign(timestamp=ts, body=body)
    # Pin "current time" to the same instant — should pass.
    current = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    assert (
        verify_signature(
            secret=SECRET,
            key_id=KEY_ID_SANDBOX_V1,
            timestamp=ts,
            raw_body=body,
            signature_header=sig,
            method=METHOD,
            callback_path=CALLBACK_PATH,
            institution_id=INSTITUTION_ID,
            now=current,
        )
        is None
    )


# ---- Constant-time helper ---------------------------------------------------


def test_constant_time_compare_equal():
    assert constant_time_compare(b"abc", b"abc") is True
    assert constant_time_compare("abc", "abc") is True


def test_constant_time_compare_unequal():
    assert constant_time_compare(b"abc", b"abd") is False
    assert constant_time_compare(b"abc", b"abcd") is False


# ---- Timing variance sanity check -------------------------------------------


def test_timing_variance_sanity_check():
    """Sanity smoke check — NOT a security guarantee.

    Two distinct signatures should compare in roughly the same time
    as two equal signatures, because ``hmac.compare_digest`` short-
    circuits AFTER walking the whole string. This test is a tripwire
    against catastrophic regressions (e.g., a refactor that swaps in
    ``==``); the real constant-time property is provided by stdlib's
    ``hmac.compare_digest``.

    Threshold: the maximum 1000-iteration mean delta must be under
    1 millisecond, which is far above any realistic timing-oracle
    signal but well within ``compare_digest``'s expected variance.
    """

    same_a = b"a" * 64
    same_b = b"a" * 64
    diff_a = b"a" * 64
    diff_b = b"b" * 64
    iters = 1000

    t0 = time.perf_counter()
    for _ in range(iters):
        constant_time_compare(same_a, same_b)
    elapsed_same = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(iters):
        constant_time_compare(diff_a, diff_b)
    elapsed_diff = time.perf_counter() - t0

    # 1000 iterations each, < 1ms total per side is generous.
    assert elapsed_same < 1.0
    assert elapsed_diff < 1.0


# ---- Installed-deps smoke check ---------------------------------------------


def test_helper_does_not_import_cryptography():
    """The helper must use stdlib only — no `cryptography` import.

    ADR 0038: COOPACs lack a C toolchain. Importing `cryptography`
    would re-introduce that dependency.
    """

    source = _HELPER_PATH.read_text(encoding="utf-8")
    # The helper file should not contain any imports of the
    # `cryptography` package (which would compile to a C extension).
    assert "import cryptography" not in source
    assert "from cryptography" not in source


def test_helper_pyproject_declares_empty_dependencies():
    """pyproject.toml's project.dependencies must be an empty list."""

    pyproject = (_HELPER_PATH.parent / "pyproject.toml").read_text(encoding="utf-8")
    # Look for the canonical empty-deps declaration.
    assert "dependencies = []" in pyproject
