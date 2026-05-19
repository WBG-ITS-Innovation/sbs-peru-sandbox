"""mTLS dependency tests — workstream A.

Direct-mode tests synthesize a leaf cert via the cryptography library
and inject its DER bytes onto ``request.state.peer_cert_der``, where the
:class:`MtlsTransportCaptureMiddleware` would have stashed them when
running behind real uvicorn (see ``api/sbs_api/middleware/mtls_transport.py``).
Proxy-mode tests inject an XFCC header in the Envoy shape.

The institution_certificates registry is provisioned via the existing
``db_schema`` testcontainer fixture; a per-test helper inserts the
synthesized cert's thumbprint before the dependency runs.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sbs_api.config import get_settings
from sbs_api.db.session import reset_engine_for_test
from sbs_api.dependencies.mtls import (
    MtlsSubject,
    _extract_cn,
    _parse_xfcc,
    verified_mtls_subject,
)


# ---------------------------------------------------------------------------
# Helper: synthesize a leaf cert for direct-mode tests
# ---------------------------------------------------------------------------


def _make_leaf_cert(cn: str, *, not_after_days: int = 365) -> tuple[str, str]:
    """Return ``(pem, sha256_hex_thumbprint)`` for a freshly minted RSA leaf."""

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "PE"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SBS Sandbox"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=not_after_days))
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    der = cert.public_bytes(serialization.Encoding.DER)
    return pem, hashlib.sha256(der).hexdigest()


# ---------------------------------------------------------------------------
# XFCC header-parsing unit tests (no DB)
# ---------------------------------------------------------------------------


def test_parse_xfcc_single_element() -> None:
    header = 'Hash=abc123;Subject="CN=BANCO_DEMO_001,O=SBS";URI='
    fields = _parse_xfcc(header)
    assert fields["Hash"] == "abc123"
    assert fields["Subject"] == "CN=BANCO_DEMO_001,O=SBS"


def test_parse_xfcc_picks_rightmost_element() -> None:
    # Two hops; the trusted proxy is the rightmost element.
    header = 'Hash=outer;Subject="CN=middlebox", Hash=inner;Subject="CN=BANCO_DEMO_001"'
    fields = _parse_xfcc(header)
    assert fields["Hash"] == "inner"
    assert fields["Subject"] == "CN=BANCO_DEMO_001"


def test_parse_xfcc_empty_returns_empty_dict() -> None:
    assert _parse_xfcc("") == {}
    assert _parse_xfcc("   ") == {}


def test_extract_cn_handles_rfc_2253_and_openssl_forms() -> None:
    assert _extract_cn("CN=BANCO_DEMO_001,O=SBS") == "BANCO_DEMO_001"
    assert _extract_cn("/C=PE/O=SBS/CN=COOPAC_DEMO_002") == "COOPAC_DEMO_002"
    assert _extract_cn("") is None
    assert _extract_cn("O=NoCN") is None


# ---------------------------------------------------------------------------
# Direct-mode tests against a real testcontainer
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def mtls_settings(test_database_url, monkeypatch):
    """Per-test Settings configured for mTLS direct mode."""

    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_MTLS_MODE", "direct")
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")

    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


async def _seed_cert_row(
    test_database_url: str,
    *,
    institution_id: str,
    cn: str,
    thumbprint: str,
    not_after_days: int = 365,
    revoked: bool = False,
) -> None:
    """Insert a row into institution_certificates for the test."""

    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO institution_certificates "
                "(sha256_thumbprint, institution_id, cn, not_before, "
                "not_after, revoked_at) VALUES "
                "(:tp, :iid, :cn, now() - interval '1 day', "
                "now() + (:days || ' days')::interval, "
                ":revoked) "
                "ON CONFLICT (sha256_thumbprint) DO NOTHING"
            ),
            {
                "tp": thumbprint,
                "iid": institution_id,
                "cn": cn,
                "days": str(not_after_days),
                "revoked": dt.datetime.now(dt.timezone.utc) if revoked else None,
            },
        )
    await engine.dispose()


def _make_app() -> FastAPI:
    """Build an app with a single route that depends on verified_mtls_subject."""

    app = FastAPI()

    @app.get("/whoami")
    async def whoami(subject: MtlsSubject = Depends(verified_mtls_subject)) -> dict:
        return {
            "institution_id": subject.institution_id,
            "cn": subject.cn,
            "cert_thumbprint": subject.cert_thumbprint,
        }

    from sbs_api.errors.handlers import install_exception_handlers

    install_exception_handlers(app)
    return app


def _pem_to_der(pem: str) -> bytes:
    """Convert PEM-encoded cert to DER bytes for request.state injection.

    The mTLS dependency reads peer cert DER from ``request.state.peer_cert_der``,
    which :class:`MtlsTransportCaptureMiddleware` populates from uvicorn's
    SSL transport in production. Tests use this helper plus a FastAPI
    middleware shim to simulate that injection over ASGITransport.
    """

    cert = x509.load_pem_x509_certificate(pem.encode("ascii"))
    return cert.public_bytes(serialization.Encoding.DER)


@pytest.mark.asyncio
async def test_direct_mode_resolves_known_cert(
    mtls_settings, db_schema, test_database_url
):
    pem, tp = _make_leaf_cert("BANCO_DEMO_001")
    await _seed_cert_row(
        test_database_url,
        institution_id="SBS-001234",
        cn="BANCO_DEMO_001",
        thumbprint=tp,
    )
    await reset_engine_for_test()

    app = _make_app()
    transport = ASGITransport(app=app)

    # httpx's ASGITransport does not run a real uvicorn protocol, so the
    # MtlsTransportCaptureMiddleware can't reach a RequestResponseCycle.
    # We inject the DER bytes onto request.state directly to simulate what
    # the middleware would have done in production.
    @app.middleware("http")
    async def inject_tls_state(request, call_next):
        request.scope.setdefault("state", {})["peer_cert_der"] = _pem_to_der(pem)
        return await call_next(request)

    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/whoami")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["institution_id"] == "SBS-001234"
    assert body["cn"] == "BANCO_DEMO_001"
    assert body["cert_thumbprint"] == tp


@pytest.mark.asyncio
async def test_direct_mode_rejects_unknown_cn(
    mtls_settings, db_schema, test_database_url
):
    pem, _tp = _make_leaf_cert("ROGUE_INSTITUTION")
    # Deliberately do NOT seed the cert row.
    await reset_engine_for_test()

    app = _make_app()

    @app.middleware("http")
    async def inject_tls_state(request, call_next):
        request.scope.setdefault("state", {})["peer_cert_der"] = _pem_to_der(pem)
        return await call_next(request)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/whoami")

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "SBS-403-001"
    assert body["type"].endswith("/CERT_CN_UNKNOWN")


@pytest.mark.asyncio
async def test_direct_mode_rejects_no_cert(mtls_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/whoami")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "SBS-401-001"
    assert body["type"].endswith("/CERT_REQUIRED")


@pytest.mark.asyncio
async def test_direct_mode_rejects_revoked_cert(
    mtls_settings, db_schema, test_database_url
):
    pem, tp = _make_leaf_cert("BANCO_DEMO_001")
    await _seed_cert_row(
        test_database_url,
        institution_id="SBS-001234",
        cn="BANCO_DEMO_001",
        thumbprint=tp,
        revoked=True,
    )
    await reset_engine_for_test()

    app = _make_app()

    @app.middleware("http")
    async def inject_tls_state(request, call_next):
        request.scope.setdefault("state", {})["peer_cert_der"] = _pem_to_der(pem)
        return await call_next(request)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/whoami")
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "SBS-403-002"
    assert body["type"].endswith("/CERT_REVOKED")


@pytest.mark.asyncio
async def test_direct_mode_rejects_expired_cert(
    mtls_settings, db_schema, test_database_url
):
    pem, tp = _make_leaf_cert("BANCO_DEMO_001")
    # Seed the row with an already-past not_after by using a negative
    # interval. _seed_cert_row uses `:days` days; negative days = past.
    await _seed_cert_row(
        test_database_url,
        institution_id="SBS-001234",
        cn="BANCO_DEMO_001",
        thumbprint=tp,
        not_after_days=-1,
    )
    await reset_engine_for_test()

    app = _make_app()

    @app.middleware("http")
    async def inject_tls_state(request, call_next):
        request.scope.setdefault("state", {})["peer_cert_der"] = _pem_to_der(pem)
        return await call_next(request)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/whoami")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "SBS-401-003"
    assert body["type"].endswith("/CERT_EXPIRED")


# ---------------------------------------------------------------------------
# Proxy-mode tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def proxy_settings(test_database_url, monkeypatch):
    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_MTLS_MODE", "proxy")
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_proxy_mode_resolves_via_xfcc_header(
    proxy_settings, db_schema, test_database_url
):
    tp = "a" * 64
    await _seed_cert_row(
        test_database_url,
        institution_id="SBS-001234",
        cn="BANCO_DEMO_001",
        thumbprint=tp,
    )
    await reset_engine_for_test()

    app = _make_app()
    xfcc = f'Hash={tp};Subject="CN=BANCO_DEMO_001,O=SBS";URI='

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/whoami", headers={"x-forwarded-client-cert": xfcc})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["institution_id"] == "SBS-001234"
    assert body["cn"] == "BANCO_DEMO_001"
    assert body["cert_thumbprint"] == tp


@pytest.mark.asyncio
async def test_proxy_mode_rejects_missing_xfcc(proxy_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/whoami")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "SBS-401-001"
    assert body["type"].endswith("/CERT_REQUIRED")


@pytest.mark.asyncio
async def test_proxy_mode_rejects_malformed_hash(proxy_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    bad_xfcc = 'Hash=not-hex;Subject="CN=BANCO_DEMO_001";URI='

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/whoami", headers={"x-forwarded-client-cert": bad_xfcc})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "SBS-401-002"
    assert body["type"].endswith("/CERT_INVALID")


@pytest.mark.asyncio
async def test_proxy_mode_rejects_missing_subject(proxy_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    no_subject = f'Hash={"a" * 64};URI='

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/whoami", headers={"x-forwarded-client-cert": no_subject})
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "SBS-401-002"
    assert body["type"].endswith("/CERT_INVALID")
