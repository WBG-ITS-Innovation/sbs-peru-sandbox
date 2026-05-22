"""HTTP route groupings.

Each router file corresponds to a section of the canonical OpenAPI spec.
``meta`` exposes ``/health``, ``/health/{live,ready,startup}``, and
``/version``. ``openapi`` serves the canonical YAML at
``/v1/openapi.yaml`` so the contract is reachable from the running app.
"""

from fastapi import APIRouter

from sbs_api.routes.batches import router as batches_router
from sbs_api.routes.cockpit import router as cockpit_router
from sbs_api.routes.complaints import router as complaints_router
from sbs_api.routes.findings import router as findings_router
from sbs_api.routes.institutions import router as institutions_router
from sbs_api.routes.internal import router as internal_router
from sbs_api.routes.meta import router as meta_router
from sbs_api.routes.oauth import router as oauth_router
from sbs_api.routes.openapi import router as openapi_router
from sbs_api.routes.portal import router as portal_router
from sbs_api.routes.sse import router as sse_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(complaints_router)
v1_router.include_router(batches_router)
v1_router.include_router(institutions_router)
v1_router.include_router(meta_router)
v1_router.include_router(oauth_router)
v1_router.include_router(openapi_router)
v1_router.include_router(portal_router)
v1_router.include_router(internal_router)
v1_router.include_router(cockpit_router)
v1_router.include_router(findings_router)
v1_router.include_router(sse_router)

__all__ = ["v1_router"]
