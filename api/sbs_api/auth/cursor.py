# SPDX-License-Identifier: Apache-2.0
"""Signed cursor payload — ADR 0028 amendment (Prompt 7 issue #L, F.5).

Cursors used for keyset pagination were previously plain base64 of the
payload JSON. A client that decodes the cursor can mutate the embedded
``received_at`` or ``complaint_id`` and submit it; the server's keyset
WHERE clause then runs against attacker-controlled coordinates. The
re-validation against the query catches *most* tampering, but the
design contract (cursor is server-controlled, client passes verbatim)
is undermined.

This module implements the signed wire format:

    cursor = base64url(payload_json || HMAC-SHA256(key, payload_json))

On decode the server splits the trailing 32 bytes as the signature,
recomputes the HMAC against the payload, and returns 400
``CURSOR_INVALID`` on mismatch. The signing key is generated at first
boot via ``secrets.token_bytes(32)`` and persisted at
``dev-ca/cursor-signing-key.bin``; production loads it from the secret
manager.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import secrets
from pathlib import Path
from typing import Any

SANDBOX_KEY_FILE = "dev-ca/cursor-signing-key.bin"


def load_or_create_cursor_signing_key(path: str = SANDBOX_KEY_FILE) -> bytes:
    """Return the cursor HMAC key; create it on first use.

    Sandbox-grade like the OAuth signing key: anyone with read access
    to the file can forge cursors. Production overlay loads the key
    from the secret manager; see ADR 0028 amendment §cursor-signing.
    """

    p = Path(path)
    if p.exists():
        return p.read_bytes()
    p.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    p.write_bytes(key)
    p.chmod(0o600)
    return key


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def encode_cursor(payload: dict[str, Any], *, key: bytes) -> str:
    """Sign and base64url-encode a cursor payload."""

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    sig = _hmac.new(key, payload_json, hashlib.sha256).digest()
    return _b64url_encode(payload_json + sig)


def decode_cursor(cursor: str, *, key: bytes) -> dict[str, Any]:
    """Verify the signature and return the decoded payload.

    Raises :class:`ValueError` on any decode or signature failure; the
    caller maps to :class:`CursorInvalid`.
    """

    try:
        raw = _b64url_decode(cursor)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"cursor base64 decode failed: {exc}") from exc

    if len(raw) <= 32:
        raise ValueError("cursor is too short to carry a signature")
    payload_json, sig = raw[:-32], raw[-32:]
    expected = _hmac.new(key, payload_json, hashlib.sha256).digest()
    if not _hmac.compare_digest(sig, expected):
        raise ValueError("cursor signature does not match")
    try:
        return json.loads(payload_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cursor payload not valid JSON: {exc}") from exc
