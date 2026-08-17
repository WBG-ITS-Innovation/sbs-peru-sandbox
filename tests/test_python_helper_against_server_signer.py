# SPDX-License-Identifier: Apache-2.0
"""Cross-verify the published Python helper against the server signer.

The helper at ``sdk-helpers/python/sbs_webhooks.py`` is what
institutions install on their receiver side. The server's outbound
signer at ``api/sbs_api/webhook/signing.py`` is what attaches the
signature on the way out. If the two diverge on the canonical
request shape or the algorithm prefix, every webhook to every
integrator silently breaks.

This test is the byte-for-byte drift catcher. Both modules must
produce identical canonical request bytes and identical signature
values on the same inputs. Failure here means the helper and the
server have desynchronised; whichever side made the recent change
must be reverted or both must be updated together.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER_PATH = REPO_ROOT / "sdk-helpers" / "python" / "sbs_webhooks.py"

# Load the helper directly (it is not installed as a package by default).
spec = importlib.util.spec_from_file_location("sbs_webhooks_for_test", HELPER_PATH)
assert spec is not None and spec.loader is not None
helper = importlib.util.module_from_spec(spec)
sys.modules.setdefault("sbs_webhooks_for_test", helper)
spec.loader.exec_module(helper)

from sbs_api.webhook.signing import (  # noqa: E402
    ALGORITHM_PREFIX as SERVER_ALGO_PREFIX,
    KID_SANDBOX_V1 as SERVER_KID,
    build_outbound_canonical_request,
    compute_outbound_signature,
    signature_header,
)


@pytest.mark.parametrize(
    ("method", "path", "body", "institution_id"),
    [
        ("POST", "/sbs-callback", b'{"event":"batch_completed"}', "SBS-001234"),
        ("POST", "/cb?env=sandbox", b"", "SBS-005678"),
        ("POST", "/deep/path?a=1&b=2", b"a" * 4096, "SBS-001234"),
        ("post", "/case", b"{}", "SBS-001234"),  # method case-insensitive
    ],
)
def test_helper_and_server_agree_on_canonical_request_bytes(
    method, path, body, institution_id
):
    """Same five-line canonical bytes from both sides."""

    timestamp = "2026-05-20T12:34:56Z"
    server_canonical = build_outbound_canonical_request(
        method=method,
        callback_path=path,
        timestamp=timestamp,
        body=body,
        institution_id=institution_id,
    ).serialize()
    helper_canonical = helper.canonicalize_request(
        method=method,
        callback_path=path,
        timestamp=timestamp,
        raw_body=body,
        institution_id=institution_id,
    )
    assert helper_canonical == server_canonical


def test_helper_and_server_agree_on_signature_value():
    """Same signature output on the same canonical + secret."""

    secret = b"sandbox-shared"
    timestamp = "2026-05-20T12:34:56Z"
    body = b'{"event":"batch_completed","batch_id":"bch_abc"}'

    # Server side: build canonical, compute signature, attach header prefix.
    server_canonical = build_outbound_canonical_request(
        method="POST",
        callback_path="/sbs-callback",
        timestamp=timestamp,
        body=body,
        institution_id="SBS-001234",
    )
    server_b64 = compute_outbound_signature(secret, server_canonical)
    server_header = signature_header(server_b64)

    # Helper side: build canonical, compute signature.
    helper_header = helper.compute_signature(
        secret,
        helper.canonicalize_request(
            method="POST",
            callback_path="/sbs-callback",
            timestamp=timestamp,
            raw_body=body,
            institution_id="SBS-001234",
        ),
    )

    assert helper_header == server_header


def test_helper_verifies_signature_produced_by_server():
    """End-to-end round trip — server signs, helper verifies."""

    secret = b"sandbox-shared"
    timestamp = "2026-05-20T12:34:56Z"
    body = b'{"event":"batch_completed"}'

    server_canonical = build_outbound_canonical_request(
        method="POST",
        callback_path="/sbs-callback",
        timestamp=timestamp,
        body=body,
        institution_id="SBS-001234",
    )
    sig = signature_header(compute_outbound_signature(secret, server_canonical))

    # Helper accepts the server's signature.
    helper.verify_signature(
        secret=secret,
        key_id=helper.KEY_ID_SANDBOX_V1,
        timestamp=timestamp,
        raw_body=body,
        signature_header=sig,
        method="POST",
        callback_path="/sbs-callback",
        institution_id="SBS-001234",
        now=__import__("datetime").datetime.fromisoformat("2026-05-20T12:35:00+00:00"),
    )


def test_helper_rejects_tampered_body_signed_by_server():
    """Tamper one byte after the server signs — helper raises Invalid."""

    secret = b"sandbox-shared"
    timestamp = "2026-05-20T12:34:56Z"
    body = b'{"event":"batch_completed"}'
    canonical = build_outbound_canonical_request(
        method="POST",
        callback_path="/sbs-callback",
        timestamp=timestamp,
        body=body,
        institution_id="SBS-001234",
    )
    sig = signature_header(compute_outbound_signature(secret, canonical))

    tampered = b'{"event":"batch_canceled"}'
    with pytest.raises(helper.SignatureInvalidError):
        helper.verify_signature(
            secret=secret,
            key_id=helper.KEY_ID_SANDBOX_V1,
            timestamp=timestamp,
            raw_body=tampered,
            signature_header=sig,
            method="POST",
            callback_path="/sbs-callback",
            institution_id="SBS-001234",
            now=__import__("datetime").datetime.fromisoformat(
                "2026-05-20T12:35:00+00:00"
            ),
        )


def test_helper_and_server_agree_on_algorithm_prefix_and_kid():
    """The constants must match across helper and server."""

    assert helper.ALGORITHM_PREFIX == SERVER_ALGO_PREFIX
    assert helper.KEY_ID_SANDBOX_V1 == SERVER_KID
