# SPDX-License-Identifier: Apache-2.0
"""Structured logging and OpenTelemetry wiring.

Imported by :mod:`sbs_api.app` at create-app time so logging and tracing are
ready before the first request lands. Idempotent: each ``configure_*`` call
checks for prior configuration and returns early on a second invocation
inside the same process.
"""

from sbs_api.observability.logging import configure_logging, get_logger
from sbs_api.observability.tracing import configure_tracing

__all__ = ["configure_logging", "configure_tracing", "get_logger"]
