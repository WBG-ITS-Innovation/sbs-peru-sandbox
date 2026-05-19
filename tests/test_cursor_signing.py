"""Cursor signing — workstream F.5, ADR 0028 amendment, issue #L.

A cursor is HMAC-signed with a server-side master key. A client that
mutates the embedded payload or signature must get a 400 CURSOR_INVALID
back.
"""

from __future__ import annotations

import base64
import json

import pytest

from sbs_api.auth.cursor import (
    _b64url_decode,
    _b64url_encode,
    decode_cursor,
    encode_cursor,
)

KEY = b"\x33" * 32
KEY_OTHER = b"\x44" * 32


def test_encode_decode_roundtrip() -> None:
    payload = {"received_at": "2026-05-19T12:00:00Z", "complaint_id": "CMP-0001"}
    cursor = encode_cursor(payload, key=KEY)
    out = decode_cursor(cursor, key=KEY)
    assert out == payload


def test_decode_rejects_tampered_payload() -> None:
    payload = {"received_at": "2026-05-19T12:00:00Z", "complaint_id": "CMP-0001"}
    cursor = encode_cursor(payload, key=KEY)

    # Decode, mutate one byte of payload, re-encode (keeping the
    # original signature). Should fail HMAC verification.
    raw = _b64url_decode(cursor)
    payload_bytes, sig = raw[:-32], raw[-32:]
    # Flip a bit in the payload — choose a structural byte.
    tampered_payload = payload_bytes.replace(b"CMP-0001", b"CMP-0002")
    tampered = _b64url_encode(tampered_payload + sig)

    with pytest.raises(ValueError):
        decode_cursor(tampered, key=KEY)


def test_decode_rejects_tampered_signature() -> None:
    payload = {"received_at": "2026-05-19T12:00:00Z", "complaint_id": "CMP-0001"}
    cursor = encode_cursor(payload, key=KEY)

    raw = _b64url_decode(cursor)
    payload_bytes, sig = raw[:-32], raw[-32:]
    flipped_sig = bytes([sig[0] ^ 0x01]) + sig[1:]
    tampered = _b64url_encode(payload_bytes + flipped_sig)

    with pytest.raises(ValueError):
        decode_cursor(tampered, key=KEY)


def test_decode_rejects_signature_from_different_key() -> None:
    payload = {"received_at": "2026-05-19T12:00:00Z", "complaint_id": "CMP-0001"}
    cursor = encode_cursor(payload, key=KEY_OTHER)
    with pytest.raises(ValueError):
        decode_cursor(cursor, key=KEY)


def test_decode_rejects_too_short() -> None:
    with pytest.raises(ValueError):
        decode_cursor(_b64url_encode(b"short"), key=KEY)


def test_decode_rejects_malformed_base64() -> None:
    with pytest.raises(ValueError):
        decode_cursor("!!!not-valid-base64!!!", key=KEY)


def test_payload_serialisation_is_stable() -> None:
    """Cursors produced with the same payload twice must be identical
    (deterministic key ordering, separators)."""

    payload = {"received_at": "2026-05-19T12:00:00Z", "complaint_id": "CMP-0001"}
    payload_reordered = {"complaint_id": "CMP-0001", "received_at": "2026-05-19T12:00:00Z"}
    a = encode_cursor(payload, key=KEY)
    b = encode_cursor(payload_reordered, key=KEY)
    assert a == b
