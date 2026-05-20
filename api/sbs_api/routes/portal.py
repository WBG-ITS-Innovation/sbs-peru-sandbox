"""Developer portal routes.

Two public routes serve the developer portal, both registered under
the v1 prefix:

- ``GET /v1/portal/`` returns the portal HTML template that points
  Stoplight Elements at the canonical ``/v1/openapi.yaml``.
- ``GET /v1/portal/assets/{filename}`` returns one of the vendored
  Stoplight Elements asset files.

Both routes are public per ADR 0037: no ``OAuthDependency``, no
``MtlsSubject``, no scope check. The OpenAPI spec declares them with
``security: []``.

The asset route is a path-parameter route with an explicit allowlist,
not a ``StaticFiles`` mount. Anything not in ``VENDOR_ASSET_ALLOWLIST``
returns 404, the same defensive 404 posture institution-binding uses.

Re-vendoring (see ``vendor/stoplight-elements/VENDOR.md``) requires
updating the allowlist AND the media-type map below when filenames
change. The Cache-Control is set to immutable because the vendored
assets are immutable for the lifetime of a deployment.
"""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["Meta"])

VENDOR_ASSET_ALLOWLIST: frozenset[str] = frozenset(
    {"web-components.min.js", "styles.min.css", "LICENSE"}
)
"""Files served by ``/v1/portal/assets/{filename}``.

Anything else returns 404. When re-vendoring Stoplight Elements adds
or renames files, update this set AND ``VENDOR_ASSET_MEDIA_TYPES``.
"""

VENDOR_ASSET_MEDIA_TYPES: dict[str, str] = {
    "web-components.min.js": "application/javascript",
    "styles.min.css": "text/css",
    "LICENSE": "text/plain",
}
"""Explicit Content-Type per allowlisted filename.

``mimetypes.guess_type`` resolves ``.min.js`` inconsistently across
systems, which produces environment-dependent test flake. The
explicit map removes that variance. The dict keys must match the
allowlist set exactly; the startup-time sanity check below enforces
this.
"""

assert set(VENDOR_ASSET_MEDIA_TYPES.keys()) == set(VENDOR_ASSET_ALLOWLIST), (
    "VENDOR_ASSET_MEDIA_TYPES must cover exactly the allowlist; "
    "update both when re-vendoring."
)

_IMMUTABLE_CACHE_HEADER = "public, max-age=31536000, immutable"


def _vendor_root() -> pathlib.Path:
    """Project-root-relative path to the vendored Stoplight directory.

    The routes module sits at ``api/sbs_api/routes/portal.py`` so the
    project root is three parents up.
    """

    return pathlib.Path(__file__).resolve().parents[3] / "vendor" / "stoplight-elements"


def _template_path() -> pathlib.Path:
    """Filesystem path to the portal HTML template."""

    return pathlib.Path(__file__).resolve().parent.parent / "templates" / "portal.html"


@router.get(
    "/portal/",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def portal_index() -> HTMLResponse:
    """Render the portal HTML template.

    The template references local asset paths only; Stoplight Elements
    initialises against ``/v1/openapi.yaml``. The HTML itself is
    served with ``Content-Type: text/html``.
    """

    path = _template_path()
    if not path.is_file():
        raise HTTPException(status_code=500, detail="portal template not found")
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


@router.get(
    "/portal/assets/{filename}",
    include_in_schema=False,
)
async def portal_asset(filename: str) -> FileResponse:
    """Serve one of the allowlisted vendored Stoplight Elements files.

    The allowlist check is positive (the filename must appear in
    ``VENDOR_ASSET_ALLOWLIST``); anything else returns 404. This is
    deliberately conservative against URL-encoding tricks, double-
    encoding, null-byte injection, and Unicode normalisation — the
    allowlist never resolves to a path, so traversal attempts cannot
    escape the vendored directory.
    """

    if filename not in VENDOR_ASSET_ALLOWLIST:
        raise HTTPException(status_code=404, detail="not found")

    asset_path = _vendor_root() / filename
    if not asset_path.is_file():
        raise HTTPException(status_code=500, detail="vendored asset missing on disk")

    return FileResponse(
        path=asset_path,
        media_type=VENDOR_ASSET_MEDIA_TYPES[filename],
        headers={"Cache-Control": _IMMUTABLE_CACHE_HEADER},
    )
