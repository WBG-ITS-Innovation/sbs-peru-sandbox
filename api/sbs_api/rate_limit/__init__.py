"""Per-institution rate limiting — ADR 0033 (with pressure-test amendments).

The :mod:`token_bucket` module implements the atomic Redis Lua script
the dependency in :mod:`sbs_api.dependencies.rate_limit` wraps.
"""

from sbs_api.rate_limit.token_bucket import (
    BucketDecision,
    TOKEN_BUCKET_SCRIPT,
    decrement_bucket,
)

__all__ = [
    "BucketDecision",
    "TOKEN_BUCKET_SCRIPT",
    "decrement_bucket",
]
