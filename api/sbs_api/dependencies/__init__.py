"""FastAPI dependencies.

``auth`` is the tenancy-binding stub (Prompt 7 replaces it with real mTLS +
OAuth + HMAC). ``db`` yields the per-request async session. ``idempotency``
and ``etag`` are the helpers route handlers compose.
"""

from sbs_api.dependencies.auth import AuthContext, get_auth_context
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.etag import compute_etag
from sbs_api.dependencies.idempotency import (
    IdempotencyContext,
    get_idempotency_context,
)
from sbs_api.dependencies.mtls import MtlsSubject, verified_mtls_subject

__all__ = [
    "AuthContext",
    "IdempotencyContext",
    "MtlsSubject",
    "compute_etag",
    "get_auth_context",
    "get_idempotency_context",
    "get_session",
    "verified_mtls_subject",
]
