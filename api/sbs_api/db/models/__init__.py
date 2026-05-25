"""ORM models — one module per aggregate.

Importing this package eagerly imports every model so Alembic's autogenerate
sees the full metadata graph.
"""

from sbs_api.db.models.agent_feedback import AgentFeedback
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.audit_event import AuditEvent
from sbs_api.db.models.batch import BatchRecord
from sbs_api.db.models.batch_row_rejection import BatchRowRejection
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.complaint_narrative_draft import ComplaintNarrativeDraft
from sbs_api.db.models.idempotency import IdempotencyRecord
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.db.models.institution_certificate import InstitutionCertificate
from sbs_api.db.models.institution_secret import InstitutionSecret
from sbs_api.db.models.institution_webhook_config import (
    InstitutionWebhookConfig,
)
from sbs_api.db.models.oauth_client import OAuthClient
from sbs_api.db.models.outbound_webhook_secret import OutboundWebhookSecret
from sbs_api.db.models.pending_approval import PendingApproval
from sbs_api.db.models.raw_complaint import RawComplaint
from sbs_api.db.models.supervisory_observation import SupervisoryObservation
from sbs_api.db.models.webhook_delivery import WebhookDelivery

__all__ = [
    "AgentFeedback",
    "AgentRun",
    "AuditEvent",
    "BatchRecord",
    "BatchRowRejection",
    "ComplaintRecord",
    "ComplaintNarrativeDraft",
    "IdempotencyRecord",
    "InstitutionRecord",
    "InstitutionCertificate",
    "InstitutionSecret",
    "InstitutionWebhookConfig",
    "OAuthClient",
    "OutboundWebhookSecret",
    "PendingApproval",
    "RawComplaint",
    "SupervisoryObservation",
    "WebhookDelivery",
]
