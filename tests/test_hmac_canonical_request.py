"""Canonical-request construction and signing primitives — workstream B.

Pure unit tests of :mod:`sbs_api.auth.hmac` — no DB, no Redis, no HTTP.
The ADR 0027 amendment fixes the wire shape; these tests pin it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
from datetime import datetime, timezone

import pytest

from sbs_api.auth.hmac import (
    EMPTY_BODY_SHA256,
    build_canonical_request,
    body_sha256_hex,
    compute_signature,
    parse_signature_header,
    replay_cache_key,
    validate_timestamp,
    verify_signature,
)


# ---------------------------------------------------------------------------
# Body hashing
# ---------------------------------------------------------------------------


def test_empty_body_hashes_to_known_constant() -> None:
    assert body_sha256_hex(b"") == EMPTY_BODY_SHA256
    # Cross-check against hashlib directly.
    assert body_sha256_hex(b"") == hashlib.sha256(b"").hexdigest()


def test_nonempty_body_hashes_lowercase_hex() -> None:
    digest = body_sha256_hex(b'{"institution_id":"SBS-001234"}')
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(c in "0123456789abcdef" for c in digest)


# ---------------------------------------------------------------------------
# Canonical request shape
# ---------------------------------------------------------------------------


def test_canonical_request_serialisation_is_six_lines() -> None:
    canonical = build_canonical_request(
        method="POST",
        target="/v1/complaints",
        host="sbs-suptech-sandbox.local",
        timestamp="2026-05-19T14:23:45Z",
        body=b"",
        institution_id="BANCO_DEMO_001",
    )
    lines = canonical.serialize().decode("ascii").split("\n")
    assert len(lines) == 6
    assert lines[0] == "POST"
    assert lines[1] == "/v1/complaints"
    assert lines[2] == "sbs-suptech-sandbox.local"
    assert lines[3] == "2026-05-19T14:23:45Z"
    assert lines[4] == EMPTY_BODY_SHA256
    assert lines[5] == "BANCO_DEMO_001"


def test_method_is_uppercased() -> None:
    canonical = build_canonical_request(
        method="post",
        target="/v1/complaints",
        host="example.com",
        timestamp="2026-05-19T14:23:45Z",
        body=b"",
        institution_id="X",
    )
    assert canonical.serialize().decode("ascii").startswith("POST\n")


def test_host_is_lowercased() -> None:
    canonical = build_canonical_request(
        method="POST",
        target="/v1/complaints",
        host="SBS-Suptech-SANDBOX.local",
        timestamp="2026-05-19T14:23:45Z",
        body=b"",
        institution_id="X",
    )
    assert "sbs-suptech-sandbox.local" in canonical.serialize().decode("ascii")


def test_query_string_preserved_in_target() -> None:
    canonical = build_canonical_request(
        method="GET",
        target="/v1/complaints?cursor=abc&limit=20",
        host="example.com",
        timestamp="2026-05-19T14:23:45Z",
        body=b"",
        institution_id="X",
    )
    assert "cursor=abc&limit=20" in canonical.serialize().decode("ascii")


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def test_compute_signature_matches_independent_hmac() -> None:
    secret = b"\x01" * 32
    canonical = build_canonical_request(
        method="POST",
        target="/v1/complaints",
        host="example.com",
        timestamp="2026-05-19T14:23:45Z",
        body=b"hello",
        institution_id="BANCO_DEMO_001",
    )
    sig = compute_signature(secret, canonical)
    expected = base64.b64encode(
        _hmac.new(secret, canonical.serialize(), hashlib.sha256).digest()
    ).decode("ascii")
    assert sig == expected


def test_verify_signature_round_trips() -> None:
    secret = b"\x02" * 32
    canonical = build_canonical_request(
        method="POST",
        target="/v1/complaints",
        host="example.com",
        timestamp="2026-05-19T14:23:45Z",
        body=b'{"a":1}',
        institution_id="X",
    )
    sig = compute_signature(secret, canonical)
    assert verify_signature(secret, canonical, sig) is True


def test_verify_signature_rejects_tamper() -> None:
    secret = b"\x03" * 32
    canonical = build_canonical_request(
        method="POST",
        target="/v1/complaints",
        host="example.com",
        timestamp="2026-05-19T14:23:45Z",
        body=b'{"a":1}',
        institution_id="X",
    )
    sig = compute_signature(secret, canonical)
    # Flip a single bit of the signature.
    tampered = base64.b64decode(sig.encode("ascii"))
    tampered = bytes([tampered[0] ^ 0x01]) + tampered[1:]
    bad_b64 = base64.b64encode(tampered).decode("ascii")
    assert verify_signature(secret, canonical, bad_b64) is False


# ---------------------------------------------------------------------------
# Signature header parsing
# ---------------------------------------------------------------------------


def test_parse_signature_accepts_v1() -> None:
    sig = parse_signature_header("hmac-sha256-v1=AAAAAA==")
    assert sig == "AAAAAA=="


def test_parse_signature_rejects_unknown_algorithm() -> None:
    with pytest.raises(ValueError):
        parse_signature_header("hmac-sha1-v0=AAAA")


def test_parse_signature_rejects_missing_separator() -> None:
    with pytest.raises(ValueError):
        parse_signature_header("hmac-sha256-v1")


def test_parse_signature_rejects_empty_value() -> None:
    with pytest.raises(ValueError):
        parse_signature_header("hmac-sha256-v1=")


# ---------------------------------------------------------------------------
# Timestamp window
# ---------------------------------------------------------------------------


def test_timestamp_valid_within_window() -> None:
    now = datetime(2026, 5, 19, 14, 23, 45, tzinfo=timezone.utc)
    verdict = validate_timestamp(
        "2026-05-19T14:22:00Z", now=now, skew_seconds=300
    )
    assert verdict.valid is True
    assert verdict.reason is None


def test_timestamp_too_old_rejected() -> None:
    now = datetime(2026, 5, 19, 14, 23, 45, tzinfo=timezone.utc)
    verdict = validate_timestamp(
        "2026-05-19T14:00:00Z", now=now, skew_seconds=300
    )
    assert verdict.valid is False
    assert "past" in verdict.reason


def test_timestamp_too_future_rejected() -> None:
    now = datetime(2026, 5, 19, 14, 23, 45, tzinfo=timezone.utc)
    verdict = validate_timestamp(
        "2026-05-19T14:30:00Z", now=now, skew_seconds=300,
        future_skew_max_seconds=60,
    )
    assert verdict.valid is False
    assert "future" in verdict.reason


def test_timestamp_naive_rejected() -> None:
    now = datetime(2026, 5, 19, 14, 23, 45, tzinfo=timezone.utc)
    verdict = validate_timestamp(
        "2026-05-19T14:23:00", now=now, skew_seconds=300
    )
    assert verdict.valid is False


def test_timestamp_garbage_rejected() -> None:
    now = datetime(2026, 5, 19, 14, 23, 45, tzinfo=timezone.utc)
    verdict = validate_timestamp("yesterday", now=now, skew_seconds=300)
    assert verdict.valid is False


# ---------------------------------------------------------------------------
# Replay cache key
# ---------------------------------------------------------------------------


def test_replay_cache_key_shape() -> None:
    key = replay_cache_key("SBS-001234", "AAAAAA==")
    assert key.startswith("sbs:hmac:replay:SBS-001234:")
    # 16 hex chars suffix.
    suffix = key.rsplit(":", 1)[1]
    assert len(suffix) == 16
    assert all(c in "0123456789abcdef" for c in suffix)
