"""HTTP route groupings.

Each router file corresponds to a section of the canonical OpenAPI spec.
``meta`` exposes ``/health``, ``/health/{live,ready,startup}``, and
``/version``. ``openapi`` serves the canonical YAML at
``/v1/openapi.yaml`` so the contract is reachable from the running app.
"""

from fastapi import APIRouter

from sbs_api.routes.agents_divalevale import router as agents_divalevale_router
from sbs_api.routes.agents_unified import router as agents_unified_router
from sbs_api.routes.approvals import router as approvals_router
from sbs_api.routes.audit import router as audit_router
from sbs_api.routes.batches import router as batches_router
from sbs_api.routes.cockpit import router as cockpit_router
from sbs_api.routes.cockpit_actions import router as cockpit_actions_router
from sbs_api.routes.cockpit_tasks import router as cockpit_tasks_router
from sbs_api.routes.chatbot import router as chatbot_router
from sbs_api.routes.complaints import router as complaints_router
from sbs_api.routes.exec import router as exec_router
from sbs_api.routes.exec_tasking import router as exec_tasking_router
from sbs_api.routes.explain import router as explain_router
from sbs_api.routes.fi_briefs import router as fi_briefs_router
from sbs_api.routes.findings import router as findings_router
from sbs_api.routes.findings_manual import router as findings_manual_router
from sbs_api.routes.institutions import router as institutions_router
from sbs_api.routes.internal import router as internal_router
from sbs_api.routes.meta import router as meta_router
from sbs_api.routes.oauth import router as oauth_router
from sbs_api.routes.openapi import router as openapi_router
from sbs_api.routes.ops import router as ops_router
from sbs_api.routes.ops_incidents import router as ops_incidents_router
from sbs_api.routes.ops_remediation import router as ops_remediation_router
from sbs_api.routes.persona import router as persona_router
from sbs_api.routes.portal import router as portal_router
from sbs_api.routes.sandbox_complaints import router as sandbox_complaints_router
from sbs_api.routes.sector_broadcast_approvals import (
    router as sector_broadcast_approvals_router,
)
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
v1_router.include_router(approvals_router)
v1_router.include_router(fi_briefs_router)
v1_router.include_router(audit_router)
v1_router.include_router(sse_router)
v1_router.include_router(sandbox_complaints_router)
v1_router.include_router(ops_router)
v1_router.include_router(exec_router)
v1_router.include_router(explain_router)
v1_router.include_router(persona_router)
v1_router.include_router(sector_broadcast_approvals_router)
v1_router.include_router(chatbot_router)
# DIValeVale-specific router BEFORE the unified router so
# /agents/divalevale/runs/{id} resolves to its richer validation_audit
# detail; other agent ids fall through to the unified agent_runs handlers.
v1_router.include_router(agents_divalevale_router)
v1_router.include_router(agents_unified_router)
# P-RESHAPE-8.5 action surface + task inbox/outbox.
v1_router.include_router(cockpit_actions_router)
v1_router.include_router(cockpit_tasks_router)
v1_router.include_router(findings_manual_router)
v1_router.include_router(exec_tasking_router)
v1_router.include_router(ops_incidents_router)
v1_router.include_router(ops_remediation_router)

__all__ = ["v1_router"]
