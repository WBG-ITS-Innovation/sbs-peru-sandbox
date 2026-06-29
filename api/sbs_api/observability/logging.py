# SPDX-License-Identifier: Apache-2.0
"""Structured logging via structlog.

Every log line carries three correlation identifiers when available:
``trace_id``, ``span_id`` (both from the active OpenTelemetry span), and
``correlation_id`` (the X-Correlation-Id header value, generated per request
if absent). ADR 0028 §5 documents why binding all three matters: the
Grafana-to-logs path lives off of ``trace_id``, while operations teams hunt
by ``correlation_id`` when the trace context was dropped upstream.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from opentelemetry import trace

from sbs_api.config import get_settings

_CORRELATION_ID: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_CONFIGURED: bool = False


def set_correlation_id(value: str | None) -> None:
    _CORRELATION_ID.set(value)


def get_correlation_id() -> str | None:
    return _CORRELATION_ID.get()


def _bind_otel_and_correlation(
    logger: logging.Logger, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.is_valid:
        event_dict.setdefault("trace_id", f"{ctx.trace_id:032x}")
        event_dict.setdefault("span_id", f"{ctx.span_id:016x}")
    cid = _CORRELATION_ID.get()
    if cid is not None:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


def configure_logging() -> None:
    """Wire structlog. Idempotent."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _bind_otel_and_correlation,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr if settings.log_format == "console" else sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr if settings.log_format == "console" else sys.stdout,
    )

    _CONFIGURED = True


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger.

    ``name`` is conventionally ``__name__`` of the calling module.
    """

    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name)
