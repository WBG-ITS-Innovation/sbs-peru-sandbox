# SPDX-License-Identifier: Apache-2.0
"""ASGI middleware.

Order at request time, outermost to innermost:
``traceparent`` → ``correlation_id`` → ``body_size_limit``. ADR 0028
§3 with the F.2 amendment records why — putting body-size innermost
means 413 responses carry ``traceparent`` and ``X-Correlation-Id``.
"""

from sbs_api.middleware.body_size_limit import BodySizeLimitMiddleware
from sbs_api.middleware.correlation_id import CorrelationIdMiddleware
from sbs_api.middleware.traceparent import TraceparentMiddleware

__all__ = [
    "BodySizeLimitMiddleware",
    "CorrelationIdMiddleware",
    "TraceparentMiddleware",
]
