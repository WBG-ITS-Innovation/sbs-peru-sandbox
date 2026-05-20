"""Outbound webhook HMAC signing — Workstream D unit tests (ADR 0035).

Pure-function tests; no DB / Redis / HTTP. Asserts the canonical
shape, signature determinism, and constant-time compare.
"""

from __future__ import annotations

import hashlib

import pytest

from sbs_api.webhook.signing import (
    KID_SANDBOX_V1,
    build_outbound_canonical_request,
    compute_outbound_signature,
    parse_signature_header,
    signature_header,
    verify_outbound_signature,
)

SECRET = bytes.fromhex(
    "a1b2c3d4e5f607182930415263748596a1b2c3d4e5f607182930415263748596"  # pragma: allowlist secret
)


def test_canonical_request_is_five_lines():
    canonical = build_outbound_canonical_request(
        method="POST",
        callback_path="/sbs-callback",
        timestamp="2026-05-20T12:00:00Z",
        body=b'{"event":"batch.complete"}',
        institution_id="SBS-001234",
    )
    serialized = canonical.serialize().decode("utf-8")
    assert serialized.count("\n") == 4, (
        "canonical request must be exactly 5 lines (4 newlines)"
    )
    lines = serialized.split("\n")
    assert lines[0] == "POST"
    assert lines[1] == "/sbs-callback"
    assert lines[2] == "2026-05-20T12:00:00Z"
    assert lines[3] == hashlib.sha256(
        b'{"event":"batch.complete"}'
    ).hexdigest()
    assert lines[4] == "SBS-001234"


def test_signature_is_deterministic_given_inputs():
    canonical = build_outbound_canonical_request(
        method="POST",
        callback_path="/sbs-callback",
        timestamp="2026-05-20T12:00:00Z",
        body=b"{}",
        institution_id="SBS-001234",
    )
    a = compute_outbound_signature(SECRET, canonical)
    b = compute_outbound_signature(SECRET, canonical)
    assert a == b
    # Sanity-check the format (base64 of 32 bytes ⇒ 44 chars with padding).
    assert len(a) == 44


def test_verify_signature_rejects_mismatch():
    canonical = build_outbound_canonical_request(
        method="POST",
        callback_path="/sbs-callback",
        timestamp="2026-05-20T12:00:00Z",
        body=b"{}",
        institution_id="SBS-001234",
    )
    sig = compute_outbound_signature(SECRET, canonical)
    assert verify_outbound_signature(SECRET, canonical, sig) is True

    # Mutate one byte — the signature must no longer verify.
    bad = "A" + sig[1:] if sig[0] != "A" else "B" + sig[1:]
    assert verify_outbound_signature(SECRET, canonical, bad) is False


def test_verify_signature_constant_time_compare_used():
    # Smoke check via the public API; the internal call is
    # hmac.compare_digest. We assert that an obviously-wrong same-length
    # signature returns False without raising.
    canonical = build_outbound_canonical_request(
        method="POST",
        callback_path="/x",
        timestamp="2026-05-20T12:00:00Z",
        body=b"{}",
        institution_id="SBS-001234",
    )
    expected = compute_outbound_signature(SECRET, canonical)
    same_length_wrong = "A" * len(expected)
    assert verify_outbound_signature(SECRET, canonical, same_length_wrong) is False


def test_signature_header_round_trip():
    sig_b64 = "ABCD" * 11
    header = signature_header(sig_b64)
    assert header == f"hmac-sha256-v1={sig_b64}"
    assert parse_signature_header(header) == sig_b64


def test_parse_signature_header_rejects_unknown_algorithm():
    with pytest.raises(ValueError):
        parse_signature_header("md5=abcdef")


def test_kid_constant():
    assert KID_SANDBOX_V1 == "sandbox-v1"
