"""Canonical OAuth scope set per ADR 0032.

Adding a scope is an ADR amendment; renaming one is a breaking change.
The mapping from scope → endpoints is documented in the OpenAPI spec
and the developer portal, not enforced here — this module is just the
authoritative list.
"""

from __future__ import annotations

COMPLAINTS_WRITE = "complaints:write"
COMPLAINTS_READ = "complaints:read"
BATCH_UPLOAD = "batch:upload"
STATUS_READ = "status:read"

ALL_SCOPES: frozenset[str] = frozenset(
    {COMPLAINTS_WRITE, COMPLAINTS_READ, BATCH_UPLOAD, STATUS_READ}
)


def parse_scope_param(value: str) -> set[str]:
    """Parse the ``scope`` form field per RFC 6749 §3.3 (space-separated)."""

    return {token for token in value.strip().split() if token}


def is_known(scope: str) -> bool:
    return scope in ALL_SCOPES
