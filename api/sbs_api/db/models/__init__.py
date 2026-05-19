"""ORM models — one module per aggregate.

Importing this package eagerly imports every model so Alembic's autogenerate
sees the full metadata graph.
"""

from sbs_api.db.models.batch import BatchRecord
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.idempotency import IdempotencyRecord
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.db.models.institution_certificate import InstitutionCertificate
from sbs_api.db.models.institution_secret import InstitutionSecret
from sbs_api.db.models.oauth_client import OAuthClient

__all__ = [
    "BatchRecord",
    "ComplaintRecord",
    "IdempotencyRecord",
    "InstitutionRecord",
    "InstitutionCertificate",
    "InstitutionSecret",
    "OAuthClient",
]
