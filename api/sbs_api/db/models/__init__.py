# SPDX-License-Identifier: Apache-2.0
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
from sbs_api.db.models.digest_audit import DigestAudit
from sbs_api.db.models.fi_brand_alias import FIBrandAlias
from sbs_api.db.models.fi_circuit_breaker import FiCircuitBreaker
from sbs_api.db.models.idempotency import IdempotencyRecord
from sbs_api.db.models.incident_annotation import IncidentAnnotation
from sbs_api.db.models.indecopi_case import IndecopiCase
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.db.models.institution_certificate import InstitutionCertificate
from sbs_api.db.models.institution_secret import InstitutionSecret
from sbs_api.db.models.institution_webhook_config import (
    InstitutionWebhookConfig,
)
from sbs_api.db.models.manual_finding import ManualFinding
from sbs_api.db.models.oauth_client import OAuthClient
from sbs_api.db.models.outbound_webhook_secret import OutboundWebhookSecret
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.pending_approval import PendingApproval
from sbs_api.db.models.raw_complaint import RawComplaint
from sbs_api.db.models.social_signal import SocialSignal, SocialSignalFixture
from sbs_api.db.models.supervisory_observation import SupervisoryObservation
from sbs_api.db.models.validation_audit import (
    EnrichmentRequest,
    ValidationAudit,
    ValidationBatch,
)
from sbs_api.db.models.webhook_delivery import WebhookDelivery

__all__ = [
    "AgentFeedback",
    "AgentRun",
    "AuditEvent",
    "BatchRecord",
    "BatchRowRejection",
    "ComplaintRecord",
    "ComplaintNarrativeDraft",
    "DigestAudit",
    "EnrichmentRequest",
    "FIBrandAlias",
    "FiCircuitBreaker",
    "IdempotencyRecord",
    "IncidentAnnotation",
    "IndecopiCase",
    "InstitutionRecord",
    "InstitutionCertificate",
    "InstitutionSecret",
    "InstitutionWebhookConfig",
    "ManualFinding",
    "OAuthClient",
    "OutboundWebhookSecret",
    "PatternDetection",
    "PendingApproval",
    "RawComplaint",
    "SocialSignal",
    "SocialSignalFixture",
    "SupervisoryObservation",
    "ValidationAudit",
    "ValidationBatch",
    "WebhookDelivery",
]
