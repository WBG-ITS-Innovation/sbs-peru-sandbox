# SPDX-License-Identifier: Apache-2.0
"""In-process Server-Sent Events bus.

ADR 0040 §D5 names the SSE refresh contract; this package implements
the demo-grade substrate. Production swaps the in-process backend for
Redis Streams under the same ``SSEBus`` interface (Part 9 deliverable).
"""

from sbs_api.sse.manager import SSEBus, SSEEvent, get_bus

__all__ = ["SSEBus", "SSEEvent", "get_bus"]
