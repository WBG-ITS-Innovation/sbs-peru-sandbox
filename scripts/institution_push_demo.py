#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Institution-side CLI sender for the P11A.5a sandbox granular endpoint.

Sends a real HTTP request to the SBS sandbox API at
``POST /v1/sandbox/complaints/granular`` with the institutional
security chain attached:

* OAuth 2.0 client_credentials token (``complaints:write`` scope).
* mTLS client cert. Two modes:
    1. **Production-like / direct or proxy with TLS**: the CLI presents
       ``dev-ca/<institution>-key.pem`` + ``dev-ca/<institution>.pem``
       on the TLS connection; the SBS API resolves the institution_id
       from the cert thumbprint.
    2. **Local sandbox smoke** (``--insecure-skip-mtls``): the API is
       running with ``SBS_API_MTLS_MODE=proxy`` over plain HTTP; the
       CLI sends a hand-rolled ``X-Forwarded-Client-Cert`` header
       carrying the dev cert's SHA-256(DER) thumbprint and the CN
       (Envoy XFCC shape), exactly as a trusted reverse-proxy would.
       Both the ``/v1/oauth/token`` and
       ``/v1/sandbox/complaints/granular`` calls receive the same
       header so the OAuth bucket (mTLS-keyed) and the business
       bucket (mTLS-keyed) both see the institution_id.
* HMAC SHA-256 canonical-request signature (ADR 0027 amendment).
* Idempotency-Key per ADR 0029.

Profiles map a friendly name to the institution's auth bundle:

* ``banco-tier1`` → SBS-001234 / banco-demo-001 / banco-demo-001.pem
* ``coopac-tier2`` → SBS-005678 / coopac-demo-002 / coopac-demo-002.pem

Scenarios drive a synthetic payload:

* ``wallet-misclassified``    — a happy-path Anexo-1A payload with PII
                                that produces an ``accepted`` receipt.
* ``missing-required-field``  — narrative omits structured product /
                                motive codes; expected DQ warnings →
                                ``accepted_with_warnings``.
* ``duplicate-retry``         — first send returns 201, an immediate
                                replay with the same Idempotency-Key
                                returns the cached receipt with
                                ``Idempotency-Replayed: true``.

This is sandbox infrastructure. The institution data is synthetic; the
network call, security chain, redaction, data-quality, audit, and SSE
behaviour on the SBS side are real.

PII safety: any DNI / phone / email / full-name / account or card
number in printed traces is masked before stdout. Raw values are sent
on the wire (the endpoint expects them; the SBS side redacts) and the
exit code is non-zero on any HTTP error.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_CA_DIR = REPO_ROOT / "dev-ca"


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Profile:
    name: str
    institution_id: str
    client_id: str
    client_secret: str
    cert_path: Path
    key_path: Path
    hmac_secret_hex: str
    institution_display: str


PROFILES: dict[str, Profile] = {
    "banco-tier1": Profile(
        name="banco-tier1",
        institution_id="SBS-001234",
        client_id="banco-demo-001",
        client_secret="banco-demo-001-secret",  # pragma: allowlist secret
        cert_path=DEV_CA_DIR / "banco-demo-001.pem",
        key_path=DEV_CA_DIR / "banco-demo-001-key.pem",
        # Mirrors scripts/dev-seed.sql.
        hmac_secret_hex=(
            "4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d"  # pragma: allowlist secret
        ),
        institution_display="BANCO_DEMO_001",
    ),
    "coopac-tier2": Profile(
        name="coopac-tier2",
        institution_id="SBS-005678",
        client_id="coopac-demo-002",
        client_secret="coopac-demo-002-secret",  # pragma: allowlist secret
        cert_path=DEV_CA_DIR / "coopac-demo-002.pem",
        key_path=DEV_CA_DIR / "coopac-demo-002-key.pem",
        hmac_secret_hex=(
            "1f2e3d4c5b6a79880f1e2d3c4b5a69877f8e9d0c1b2a39481f2e3d4c5b6a7988"  # pragma: allowlist secret
        ),
        institution_display="COOPAC_DEMO_002",
    ),
}


SCENARIOS = (
    "wallet-misclassified",
    "missing-required-field",
    "duplicate-retry",
    "hmac-replay-attack",
)


# ---------------------------------------------------------------------------
# Dev-mode XFCC header construction (proxy-mode local smoke)
# ---------------------------------------------------------------------------


def _cert_thumbprint_sha256_hex(pem_path: Path) -> str:
    """Return the lowercase hex SHA-256 of the DER-encoded leaf cert.

    Matches what the API computes when uvicorn terminates TLS, and
    what a reverse-proxy is expected to put in the XFCC ``Hash=`` field
    when running in proxy mode.
    """

    pem_bytes = pem_path.read_bytes()
    # Lazy import: keep the CLI usable for ``--help`` even on a stripped
    # venv that does not have ``cryptography`` installed.
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    cert = x509.load_pem_x509_certificate(pem_bytes)
    der = cert.public_bytes(serialization.Encoding.DER)
    return hashlib.sha256(der).hexdigest()


def _build_xfcc_header(profile: "Profile") -> str:
    """Build an Envoy-shaped X-Forwarded-Client-Cert value for the profile.

    Shape (one XFCC element, no trailing comma — the dependency parses
    the rightmost element):

        Hash=<sha256-hex>;Subject="CN=<CN>,O=SBS";URI=

    The thumbprint is recomputed from the on-disk PEM so a fresh
    ``bash scripts/dev-ca.sh`` rotation is picked up without touching
    this file. Falls back to the static ``dev-ca/thumbprints.txt`` row
    when the PEM is missing (e.g. a stripped checkout).
    """

    if profile.cert_path.exists():
        thumbprint = _cert_thumbprint_sha256_hex(profile.cert_path)
    else:
        thumbprint = _lookup_static_thumbprint(profile.institution_id)
    return f'Hash={thumbprint};Subject="CN={profile.institution_display},O=SBS";URI='


def _lookup_static_thumbprint(institution_id: str) -> str:
    path = DEV_CA_DIR / "thumbprints.txt"
    if not path.exists():
        raise SystemExit(
            f"cannot resolve dev cert thumbprint: neither the leaf PEM "
            f"nor {path} is present. Run `bash scripts/dev-ca.sh`."
        )
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 3 and parts[0] == institution_id:
            return parts[2].strip().lower()
    raise SystemExit(
        f"institution_id {institution_id!r} not found in {path}; "
        "re-run `bash scripts/dev-ca.sh`."
    )


# ---------------------------------------------------------------------------
# PII masking (for printed traces only)
# ---------------------------------------------------------------------------


# Order matters: longer / more-specific patterns first so e.g. an
# 8-digit DNI inside a 16-digit card doesn't lose its first match.
_PII_REGEXES: list[tuple[re.Pattern[str], str]] = [
    # Email
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "<EMAIL>"),
    # Card / account: 12-19 digits with optional spaces / hyphens.
    (re.compile(r"(?<!\d)(?:\d[\s\-]?){11,18}\d(?!\d)"), "<ACCOUNT>"),
    # Peruvian phone (with or without +51 prefix).
    (re.compile(r"(?<!\d)(?:\+?51[\s\-]*)?9\d{2}[\s\-]*\d{3}[\s\-]*\d{3}(?!\d)"), "<PHONE>"),
    # DNI (8 contiguous digits, optional DNI: prefix).
    (re.compile(r"\bDNI\s*[:.\-]?\s*\d{8}\b", flags=re.IGNORECASE), "DNI:<DNI>"),
    (re.compile(r"(?<!\d)\d{8}(?!\d)"), "<DNI>"),
]


_NAME_TOKENS = (
    "Carlos Rodríguez Mendoza",
    "Carlos Rodriguez Mendoza",
    "María Pérez Quispe",
    "Maria Perez Quispe",
    "Juan Quispe Huamán",
    "Juan Quispe Huaman",
)


def mask_pii(text: str) -> str:
    """Replace PII tokens with stable placeholders for printing.

    Returned text is safe to log. Raw inputs sent on the wire are
    untouched; this only sanitises the printed trace.
    """

    if not text:
        return text
    out = text
    for token in _NAME_TOKENS:
        out = out.replace(token, "<PERSON>")
    for pattern, repl in _PII_REGEXES:
        out = pattern.sub(repl, out)
    return out


def mask_json_for_print(payload: Any) -> Any:
    """Recursively walk a JSON-ish value and mask PII fields.

    Field-level allow-list approach: known PII-bearing keys are
    redacted by key; free-text fields are passed through ``mask_pii``.
    """

    pii_keys = {
        "tid_cli",
        "nro_cli",
        "ncl_cli",
        "cod_cli",
        "institution_complaint_id",
    }
    text_keys = {"narrative", "response_detail", "description_text"}
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if k in pii_keys and isinstance(v, str) and v:
                out[k] = "<MASKED>"
            elif k in text_keys and isinstance(v, str):
                out[k] = mask_pii(v)
            else:
                out[k] = mask_json_for_print(v)
        return out
    if isinstance(payload, list):
        return [mask_json_for_print(item) for item in payload]
    if isinstance(payload, str):
        return mask_pii(payload)
    return payload


# ---------------------------------------------------------------------------
# Payload scenarios
# ---------------------------------------------------------------------------


def _scenario_payload(scenario: str, profile: Profile) -> dict[str, Any]:
    """Return a synthetic Anexo-1A-shaped DemoSubmissionRequest body.

    The narratives carry PII deliberately — the sandbox endpoint
    redacts them on receipt. Names are drawn from the
    ``DEMO_KNOWN_NAMES`` allow-list so the redaction engine produces
    the expected entity counts.
    """

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {
        "institution_id": profile.institution_id,
        "institution_name": profile.institution_display,
        "client_submission_id": f"cli-{scenario}-{secrets.token_hex(4)}",
        "received_at": now_iso,
        "demo_scenario": scenario,
    }
    if scenario == "wallet-misclassified":
        return {
            **base,
            "institution_complaint_id": f"BCO-CLI-{secrets.token_hex(3).upper()}",
            "channel_in": "APP_MOVIL",
            "channel_operation": "APP_MOVIL",
            "product": "TARJETA_CREDITO",
            "motive": "COBRO_INDEBIDO",
            "narrative": (
                "El cliente Carlos Rodríguez Mendoza (DNI 12345678) reporta "
                "un cargo no reconocido por S/ 700 en la tarjeta "
                "4556 1234 5678 9999. Indica que recibió notificaciones "
                "por su billetera digital y solicita ser contactado al "
                "+51 987 654 321 o al correo carlos.rodriguez@example.com."
            ),
            "response_detail": None,
            "status": "pendiente",
            "severity": "HIGH",
        }
    if scenario == "missing-required-field":
        # No product / motive / channel codes → DQ warnings.
        return {
            **base,
            "institution_complaint_id": f"BCO-CLI-{secrets.token_hex(3).upper()}",
            "narrative": (
                "Cliente Carlos Rodríguez Mendoza (DNI 12345678) presenta "
                "queja sobre un cobro, sin detalle adicional. Contactar "
                "carlos.rodriguez@example.com."
            ),
            "severity": "MEDIUM",
        }
    if scenario in ("duplicate-retry", "hmac-replay-attack"):
        return {
            **base,
            "institution_complaint_id": f"BCO-CLI-{secrets.token_hex(3).upper()}",
            "channel_in": "APP_MOVIL",
            "channel_operation": "APP_MOVIL",
            "product": "TARJETA_CREDITO",
            "motive": "COBRO_INDEBIDO",
            "narrative": (
                "Cliente Carlos Rodríguez Mendoza (DNI 12345678) reporta "
                "cargo duplicado por S/ 250.00 en la tarjeta "
                "4556 1234 5678 9999."
            ),
            "severity": "MEDIUM",
        }
    raise SystemExit(f"unknown scenario {scenario!r}; pick one of {SCENARIOS}")


# ---------------------------------------------------------------------------
# OAuth + HMAC plumbing
# ---------------------------------------------------------------------------


def _now_rfc3339() -> str:
    """Return a microsecond-precision RFC 3339 timestamp.

    Microsecond precision is required so that two POSTs sent within
    the same wall-second produce distinct canonical-request strings
    (and therefore distinct HMAC signatures). Without this, an
    idempotent retry would collide with the HMAC replay cache and
    return 401 ``SIGNATURE_REPLAYED`` instead of an idempotency
    replay. The server's ``datetime.fromisoformat`` parser accepts
    fractional seconds.
    """

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _build_canonical_request(
    *,
    method: str,
    target: str,
    host: str,
    timestamp: str,
    body: bytes,
    institution_id: str,
) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest() if body else (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # pragma: allowlist secret
    )
    return "\n".join(
        (method.upper(), target, host.lower(), timestamp, body_hash, institution_id)
    ).encode("utf-8")


def _sign(secret_hex: str, canonical: bytes) -> str:
    secret = bytes.fromhex(secret_hex)
    mac = hmac.new(secret, canonical, hashlib.sha256).digest()
    return "hmac-sha256-v1=" + base64.b64encode(mac).decode("ascii")


def _make_client(
    *,
    api_base: str,
    profile: Profile,
    insecure_skip_mtls: bool,
) -> httpx.Client:
    """Build an httpx client with mTLS cert / verify configured.

    Local-sandbox-smoke mode (``--insecure-skip-mtls``) drops the
    TLS-layer cert+verify pair — the API is running over plain HTTP
    with ``SBS_API_MTLS_MODE=proxy`` and the trusted reverse-proxy is
    simulated by sending the XFCC header explicitly (see
    ``_dev_proxy_headers``). The HMAC + OAuth chain is still enforced.
    """

    if insecure_skip_mtls or api_base.startswith("http://"):
        return httpx.Client(timeout=10.0)
    ca_bundle = DEV_CA_DIR / "ca.pem"
    if not ca_bundle.exists():
        raise SystemExit(
            f"CA bundle {ca_bundle} not found; run scripts/dev-ca.sh "
            "or pass --insecure-skip-mtls for plain-HTTP dev."
        )
    if not profile.cert_path.exists() or not profile.key_path.exists():
        raise SystemExit(
            f"client cert/key not found for profile {profile.name}; "
            "run scripts/dev-ca.sh first."
        )
    return httpx.Client(
        timeout=10.0,
        verify=str(ca_bundle),
        cert=(str(profile.cert_path), str(profile.key_path)),
    )


def _dev_proxy_headers(
    *, profile: Profile, insecure_skip_mtls: bool
) -> dict[str, str]:
    """Return the XFCC header dict for local sandbox smoke; empty otherwise.

    Real mTLS modes (direct uvicorn or a real reverse proxy) rely on
    the TLS layer / the proxy to populate XFCC; the CLI must not
    forge a header in those modes. Only ``--insecure-skip-mtls``
    (the explicit local-only opt-in) attaches the dev XFCC header.
    """

    if not insecure_skip_mtls:
        return {}
    return {"X-Forwarded-Client-Cert": _build_xfcc_header(profile)}


_LOCAL_SMOKE_HINT = (
    # Retained as an alias for backwards compatibility with the test
    # that asserts the SystemExit message mentions both the mode and
    # the flag. The classifier (``_classify_failure``) is the
    # canonical source for response-driven hints.
    "Local-smoke hint: start the API with\n"
    "    SBS_API_MTLS_MODE=proxy PYTHONPATH=\"$PWD/api\" bash scripts/run-api.sh\n"
    "and pass --insecure-skip-mtls to this CLI. In that mode the CLI sends "
    "a dev X-Forwarded-Client-Cert header. For real mTLS, run the API in "
    "direct mode behind a TLS terminator and omit --insecure-skip-mtls."
)


def _fetch_token(
    client: httpx.Client,
    *,
    api_base: str,
    profile: Profile,
    dev_proxy_headers: dict[str, str],
) -> str:
    """Run the OAuth client_credentials grant; return the JWT.

    Raises ``SystemExit`` with a clear local-smoke hint if the API
    rejects the request (typical cause in dev: missing XFCC header
    when the API is in proxy mode).
    """

    url = f"{api_base.rstrip('/')}/oauth/token"
    headers = {
        "Authorization": _basic_auth_header(
            profile.client_id, profile.client_secret
        ),
        "Content-Type": "application/x-www-form-urlencoded",
        **dev_proxy_headers,
    }
    resp = client.post(
        url,
        data={
            "grant_type": "client_credentials",
            "scope": "complaints:write complaints:read",
        },
        headers=headers,
    )
    if resp.status_code != 200:
        msg = (
            f"OAuth token request failed: HTTP {resp.status_code}\n"
            f"    response: {resp.text}\n"
            f"{_LOCAL_SMOKE_HINT}"
        )
        raise SystemExit(msg)
    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise SystemExit(f"no access_token in token response: {payload}")
    return token


def _post_complaint(
    client: httpx.Client,
    *,
    api_base: str,
    profile: Profile,
    token: str,
    body_dict: dict[str, Any],
    idempotency_key: str,
    dev_proxy_headers: dict[str, str],
    force_timestamp: str | None = None,
) -> tuple[httpx.Response, str, str]:
    """Send the signed POST to /v1/sandbox/complaints/granular.

    Returns ``(response, timestamp_used, signature_used)`` so the
    caller can deliberately replay an exact signed request (the
    ``hmac-replay-attack`` scenario). ``force_timestamp`` reuses a
    prior wall-clock timestamp instead of generating a fresh one —
    used only by ``hmac-replay-attack`` to provoke the server's
    replay protection.
    """

    target = "/v1/sandbox/complaints/granular"
    url = f"{api_base.rstrip('/')}/sandbox/complaints/granular"

    # Parse host/port from api_base for the canonical Host header.
    parsed = urllib.parse.urlparse(api_base)
    host_header = parsed.netloc or parsed.path
    if not host_header:
        host_header = "localhost"

    timestamp = force_timestamp or _now_rfc3339()
    body_bytes = json.dumps(body_dict, separators=(",", ":")).encode("utf-8")
    canonical = _build_canonical_request(
        method="POST",
        target=target,
        host=host_header,
        timestamp=timestamp,
        body=body_bytes,
        institution_id=profile.institution_id,
    )
    signature = _sign(profile.hmac_secret_hex, canonical)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
        "X-SBS-Timestamp": timestamp,
        "X-SBS-Signature": signature,
        "X-SBS-Institution-Id": profile.institution_id,
        **dev_proxy_headers,
    }
    resp = client.post(url, content=body_bytes, headers=headers)
    return resp, timestamp, signature


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


_TOTAL_STEPS = 6


def _step(num: int, msg: str) -> None:
    print(f"  [{num}/{_TOTAL_STEPS}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Failure-hint selection
# ---------------------------------------------------------------------------


_PROXY_MODE_HINT = (
    "Local-smoke hint: start the API with\n"
    "    SBS_API_MTLS_MODE=proxy PYTHONPATH=\"$PWD/api\" bash scripts/run-api.sh\n"
    "and pass --insecure-skip-mtls. In that mode the CLI sends a dev "
    "X-Forwarded-Client-Cert header. For real mTLS, run the API in direct "
    "mode behind a TLS terminator and omit --insecure-skip-mtls."
)

_REPLAY_HINT = (
    "Expected replay protection: exact HMAC signature was reused. Use a "
    "fresh signature with the same Idempotency-Key for an idempotent retry."
)


# Substrings used to detect which failure class the API returned. The
# ProblemDetail envelope carries either ``type`` (URI suffix) or
# ``code`` — match on the stable type suffix from the error catalogue.
_PROXY_ERROR_MARKERS = (
    "CERT_REQUIRED",
    "CERT_INVALID",
    "CERT_CN_UNKNOWN",
    "CERT_REVOKED",
    "CERT_EXPIRED",
)
_REPLAY_ERROR_MARKERS = ("SIGNATURE_REPLAYED",)


def _classify_failure(response_text: str) -> str | None:
    """Return the hint string to print for a non-2xx response, or None."""

    for marker in _REPLAY_ERROR_MARKERS:
        if marker in response_text:
            return _REPLAY_HINT
    for marker in _PROXY_ERROR_MARKERS:
        if marker in response_text:
            return _PROXY_MODE_HINT
    return None


def _print_request_trace(*, target: str, body_dict: dict[str, Any]) -> None:
    masked_body = mask_json_for_print(body_dict)
    print("    request body (PII-masked for print):", flush=True)
    for line in json.dumps(masked_body, indent=2, ensure_ascii=False).splitlines():
        print(f"      {line}", flush=True)


def _print_response(resp: httpx.Response) -> None:
    masked_text = mask_pii(resp.text)
    print(f"    HTTP {resp.status_code}", flush=True)
    try:
        masked_body = mask_json_for_print(resp.json())
        for line in json.dumps(masked_body, indent=2, ensure_ascii=False).splitlines():
            print(f"      {line}", flush=True)
    except json.JSONDecodeError:
        print(f"      {masked_text}", flush=True)


def run_once(
    *,
    api_base: str,
    profile: Profile,
    scenario: str,
    insecure_skip_mtls: bool,
    idempotency_key: str | None = None,
    token_override: str | None = None,
    body_override: dict[str, Any] | None = None,
    force_timestamp: str | None = None,
) -> tuple[int, dict[str, Any] | None, str | None, str, str]:
    """Drive one full request.

    Returns ``(status_code, json_body, token, timestamp_used,
    signature_used)``. ``timestamp_used`` / ``signature_used`` are
    returned so the caller can deliberately replay the same signed
    request — the ``hmac-replay-attack`` scenario uses this to
    provoke the server's HMAC replay protection.

    Step numbering is chronological:
      [1/6] mTLS / dev XFCC header prepared
      [2/6] OAuth token obtained
      [3/6] HMAC signature generated
      [4/6] Idempotency-Key attached
      [5/6] POST /v1/sandbox/complaints/granular
      [6/6] SBS receipt received (or rejection class)
    """

    client = _make_client(
        api_base=api_base, profile=profile, insecure_skip_mtls=insecure_skip_mtls
    )
    dev_proxy_headers = _dev_proxy_headers(
        profile=profile, insecure_skip_mtls=insecure_skip_mtls
    )
    try:
        # [1/6] cert evidence — must be ready before the OAuth bucket
        # call (which is mTLS-keyed).
        if dev_proxy_headers:
            _step(
                1,
                f"dev XFCC header prepared (CN={profile.institution_display}, "
                "proxy-mode local smoke)",
            )
        else:
            _step(
                1,
                f"mTLS client cert attached (CN={profile.institution_display})",
            )

        # [2/6] OAuth token. ``_fetch_token`` raises SystemExit on
        # non-2xx with a clear local-smoke hint; the success line
        # only prints on a 200.
        if token_override is None:
            token = _fetch_token(
                client,
                api_base=api_base,
                profile=profile,
                dev_proxy_headers=dev_proxy_headers,
            )
            _step(2, "OAuth token obtained (client_credentials)")
        else:
            token = token_override
            _step(2, "OAuth token reused from earlier step")

        # [3/6] HMAC + [4/6] Idempotency-Key — both are constructed
        # inside ``_post_complaint``; we log the intent here.
        if force_timestamp is None:
            _step(3, "HMAC signature generated (hmac-sha256-v1, fresh nonce)")
        else:
            _step(
                3,
                "HMAC signature reused verbatim (replay-attack scenario; "
                "expect 401 SIGNATURE_REPLAYED)",
            )

        idem_key = idempotency_key or f"cli-{uuid.uuid4().hex[:24]}"
        _step(4, f"Idempotency-Key attached ({idem_key})")

        body_dict = body_override or _scenario_payload(scenario, profile)

        # [5/6] POST.
        _step(5, "POST /v1/sandbox/complaints/granular")
        _print_request_trace(target="/v1/sandbox/complaints/granular", body_dict=body_dict)

        resp, ts_used, sig_used = _post_complaint(
            client,
            api_base=api_base,
            profile=profile,
            token=token,
            body_dict=body_dict,
            idempotency_key=idem_key,
            dev_proxy_headers=dev_proxy_headers,
            force_timestamp=force_timestamp,
        )

        # [6/6] outcome.
        if resp.status_code in (200, 201):
            _step(6, "SBS receipt received")
        else:
            _step(6, f"SBS rejected request (HTTP {resp.status_code})")
        _print_response(resp)
        if resp.status_code not in (200, 201):
            hint = _classify_failure(resp.text)
            if hint:
                print(hint, flush=True)
        try:
            json_body: dict[str, Any] | None = resp.json()
        except json.JSONDecodeError:
            json_body = None
        return resp.status_code, json_body, token, ts_used, sig_used
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--api-base",
        default=os.environ.get("SBS_API_BASE", "http://localhost:8000/v1"),
        help="SBS API base URL including /v1 (default: http://localhost:8000/v1).",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES.keys()),
        default="banco-tier1",
        help="Institution profile (default: banco-tier1).",
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="wallet-misclassified",
        help="Synthetic payload scenario (default: wallet-misclassified).",
    )
    parser.add_argument(
        "--insecure-skip-mtls",
        action="store_true",
        help=(
            "Local sandbox smoke only. Skips the TLS-layer client cert "
            "and instead sends a dev X-Forwarded-Client-Cert header "
            "carrying the profile's CN + cert thumbprint (the proxy-"
            "mode shape the API verifies). Use this when the API is "
            "running over plain HTTP with SBS_API_MTLS_MODE=proxy. "
            "Do not use against any non-sandbox endpoint."
        ),
    )
    args = parser.parse_args(argv)

    profile = PROFILES[args.profile]
    print(
        f"sandbox sender: profile={profile.name} scenario={args.scenario} "
        f"api_base={args.api_base}",
        flush=True,
    )

    if args.scenario == "duplicate-retry":
        idem_key = f"cli-dup-{uuid.uuid4().hex[:20]}"
        # Build the payload once so both attempts hash identically.
        # Each send signs the canonical request freshly (microsecond-
        # precision timestamp); the Idempotency-Key + body stay the
        # same so the server returns the original receipt.
        body_dict = _scenario_payload(args.scenario, profile)
        print(">> first send (fresh HMAC, new Idempotency-Key)", flush=True)
        status1, body1, token, _ts1, _sig1 = run_once(
            api_base=args.api_base,
            profile=profile,
            scenario=args.scenario,
            insecure_skip_mtls=args.insecure_skip_mtls,
            idempotency_key=idem_key,
            body_override=body_dict,
        )
        if status1 != 201:
            print(f"first send failed (status={status1})", flush=True)
            return 1
        print(
            ">> idempotent retry (same Idempotency-Key, same body, "
            "FRESH HMAC signature)",
            flush=True,
        )
        status2, body2, _token, _ts2, _sig2 = run_once(
            api_base=args.api_base,
            profile=profile,
            scenario=args.scenario,
            insecure_skip_mtls=args.insecure_skip_mtls,
            idempotency_key=idem_key,
            token_override=token,
            body_override=body_dict,
        )
        if status2 != 201:
            print(f"retry returned unexpected status={status2}", flush=True)
            return 1
        if body1 and body2 and body1.get("complaint_id") != body2.get("complaint_id"):
            print(
                f"idempotent retry produced a different complaint_id "
                f"({body1.get('complaint_id')} vs {body2.get('complaint_id')}) — "
                "idempotency failed",
                flush=True,
            )
            return 1
        print(
            "ok — idempotent retry returned the original receipt; "
            "no second canonical complaint was created",
            flush=True,
        )
        return 0

    if args.scenario == "hmac-replay-attack":
        # Demonstrates that the backend's HMAC replay protection
        # rejects an *exact* signature replay even when a fresh
        # Idempotency-Key is supplied. The second POST reuses the
        # first send's timestamp; the canonical request is therefore
        # byte-identical and the signature collides in the replay
        # cache → expected HTTP 401 SIGNATURE_REPLAYED.
        body_dict = _scenario_payload(args.scenario, profile)
        idem_key_a = f"cli-replay-a-{uuid.uuid4().hex[:16]}"
        idem_key_b = f"cli-replay-b-{uuid.uuid4().hex[:16]}"
        print(">> first send (fresh signature)", flush=True)
        status1, _body1, token, ts1, _sig1 = run_once(
            api_base=args.api_base,
            profile=profile,
            scenario=args.scenario,
            insecure_skip_mtls=args.insecure_skip_mtls,
            idempotency_key=idem_key_a,
            body_override=body_dict,
        )
        if status1 not in (200, 201):
            print(f"first send failed (status={status1})", flush=True)
            return 1
        print(
            ">> attempted exact-signature replay (same timestamp + body; "
            "expect 401 SIGNATURE_REPLAYED)",
            flush=True,
        )
        status2, body2, _token, _ts2, _sig2 = run_once(
            api_base=args.api_base,
            profile=profile,
            scenario=args.scenario,
            insecure_skip_mtls=args.insecure_skip_mtls,
            idempotency_key=idem_key_b,
            token_override=token,
            body_override=body_dict,
            force_timestamp=ts1,
        )
        if status2 == 401 and body2 and "SIGNATURE_REPLAYED" in json.dumps(body2):
            print(
                "ok — exact-signature replay was rejected with "
                "401 SIGNATURE_REPLAYED",
                flush=True,
            )
            return 0
        print(
            f"unexpected: replay attack returned status={status2} "
            "(expected 401 SIGNATURE_REPLAYED)",
            flush=True,
        )
        return 1

    status, _body, _token, _ts, _sig = run_once(
        api_base=args.api_base,
        profile=profile,
        scenario=args.scenario,
        insecure_skip_mtls=args.insecure_skip_mtls,
    )
    if status not in (201, 200):
        print(f"send failed (status={status})", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
