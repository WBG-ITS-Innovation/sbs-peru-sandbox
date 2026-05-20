"""Developer portal HTML and vendored-asset routes.

ADR 0037 — Stoplight Elements vendored locally; portal served from
the same FastAPI process at ``/v1/portal/`` and
``/v1/portal/assets/{filename}``. Path-parameter route with explicit
allowlist (not StaticFiles). Both routes public (no auth dependency).

These tests exercise the ASGI in-process surface. The live-stack curl
checks (per the §3 exit-gate rule) live in ``scripts/smoke-test.sh``
and the workstream A acceptance log; the in-process tests cover the
allowlist, traversal posture, content types, and cache headers.
"""

from __future__ import annotations

import pathlib

import pytest

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


# --- /v1/portal/ HTML index ---------------------------------------------------


async def test_portal_index_returns_html_200(client):
    """GET /v1/portal/ returns the portal HTML."""

    r = await client.get("/v1/portal/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "<title>SBS SupTech Complaints API" in body
    assert 'apiDescriptionUrl="/v1/openapi.yaml"' in body
    assert 'tryItCredentialsPolicy="omit"' in body


async def test_portal_index_does_not_require_auth(client):
    """The portal route has no auth dependency.

    The test fixture installs bypass overrides for every authenticated
    dependency, but the portal route does not declare any. Verifying
    the route still works after the overrides are removed proves no
    silent dependency on the bypass.
    """

    from sbs_api.dependencies.mtls import verified_mtls_subject

    # Pop the mTLS override; if the portal route declared it, this would 401.
    client._transport.app.dependency_overrides.pop(verified_mtls_subject, None)

    r = await client.get("/v1/portal/")
    assert r.status_code == 200


async def test_portal_index_references_local_assets_only(client):
    """The HTML must not reference any CDN — local paths only.

    ADR 0037: no CDN dependency. A future contributor pulling in a CDN
    URL by accident would be caught by this assertion.
    """

    r = await client.get("/v1/portal/")
    assert r.status_code == 200
    body = r.text
    assert "unpkg.com" not in body
    assert "cdn.jsdelivr.net" not in body
    assert "cdnjs.cloudflare.com" not in body
    assert "/v1/portal/assets/web-components.min.js" in body
    assert "/v1/portal/assets/styles.min.css" in body


# --- /v1/portal/assets/{filename} allowlist ----------------------------------


@pytest.mark.parametrize(
    ("filename", "expected_content_type"),
    [
        ("web-components.min.js", "application/javascript"),
        ("styles.min.css", "text/css"),
        ("LICENSE", "text/plain"),
    ],
)
async def test_allowlisted_asset_returns_200_with_correct_content_type(
    client, filename, expected_content_type
):
    """Each allowlisted file serves with its declared media type."""

    r = await client.get(f"/v1/portal/assets/{filename}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(expected_content_type)


@pytest.mark.parametrize(
    "filename",
    [
        "web-components.min.js",
        "styles.min.css",
        "LICENSE",
    ],
)
async def test_allowlisted_asset_sets_immutable_cache_header(client, filename):
    """Vendored assets are immutable — long max-age + immutable directive."""

    r = await client.get(f"/v1/portal/assets/{filename}")
    assert r.status_code == 200
    cache = r.headers.get("cache-control", "")
    assert "max-age=31536000" in cache
    assert "immutable" in cache
    assert "public" in cache


@pytest.mark.parametrize(
    "filename",
    [
        # Direct path-traversal forms.
        "../etag.py",
        "..%2Fetag.py",  # URL-encoded slash
        "..%252Fetag.py",  # double-encoded slash
        "../../../etc/passwd",
        "etag.py%00.js",  # null-byte injection
        "..\\etag.py",  # backslash variant
        # Random non-allowlisted filenames.
        "package.json",
        "secrets.env",
        "robots.txt",
        "",  # empty filename (path becomes /v1/portal/assets/)
    ],
)
async def test_non_allowlisted_filename_returns_404(client, filename):
    """Anything not in VENDOR_ASSET_ALLOWLIST returns 404.

    The traversal-form parameter list covers the six forms named in
    ADR 0037 plus extras (random non-allowlisted, empty). The allowlist
    never resolves to a path so traversal cannot escape the vendor dir.
    """

    r = await client.get(f"/v1/portal/assets/{filename}")
    assert r.status_code == 404


async def test_allowlist_and_media_type_map_cover_same_filenames():
    """Sanity check — the two module-level constants are in sync.

    Re-vendoring requires updating BOTH the allowlist set AND the
    media-type map. The module-level assertion catches mismatch at
    import time; this test makes the failure visible in the test
    output too.
    """

    from sbs_api.routes.portal import (
        VENDOR_ASSET_ALLOWLIST,
        VENDOR_ASSET_MEDIA_TYPES,
    )

    assert set(VENDOR_ASSET_MEDIA_TYPES.keys()) == set(VENDOR_ASSET_ALLOWLIST)


async def test_vendored_files_exist_on_disk():
    """The committed bytes must be present.

    A re-vendoring step that accidentally removed a file would 500 the
    portal at boot. This test verifies the disk surface matches the
    allowlist before the route ever runs.
    """

    from sbs_api.routes.portal import VENDOR_ASSET_ALLOWLIST, _vendor_root

    root = _vendor_root()
    assert root.is_dir(), f"vendor dir missing: {root}"
    for filename in VENDOR_ASSET_ALLOWLIST:
        p = root / filename
        assert p.is_file(), f"vendored asset missing: {p}"
        assert p.stat().st_size > 0, f"vendored asset empty: {p}"


async def test_vendor_md_exists_with_provenance_table():
    """The VENDOR.md provenance record is present and non-empty.

    Re-vendoring without updating VENDOR.md leaves stale provenance.
    This test is a tripwire — it does not parse the file, just
    asserts it has the expected anchor headers.
    """

    from sbs_api.routes.portal import _vendor_root

    vendor_md = _vendor_root() / "VENDOR.md"
    assert vendor_md.is_file(), f"VENDOR.md missing at {vendor_md}"
    text = vendor_md.read_text(encoding="utf-8")
    assert "## Provenance" in text
    assert "## Files and checksums" in text
    assert "Apache-2.0" in text
