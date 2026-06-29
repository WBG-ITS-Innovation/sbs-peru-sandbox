# SPDX-License-Identifier: Apache-2.0
"""Observability: structlog binds trace_id / span_id / correlation_id.

ADR 0028 §5 — every log line must carry all three identifiers when
available. This test exercises the structlog processor chain directly
(no HTTP layer needed); the integration with an active span comes
through :mod:`opentelemetry.trace`.
"""

from __future__ import annotations

import io
import json

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from sbs_api.observability.logging import (
    _bind_otel_and_correlation,
    configure_logging,
    set_correlation_id,
)


def _capture_log_event(span_active: bool, correlation_id: str | None) -> dict:
    """Run a record through the binding processor and return the merged dict."""

    set_correlation_id(correlation_id)

    if span_active:
        provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("obs"):
            event = _bind_otel_and_correlation(None, "info", {"event": "hello"})
    else:
        event = _bind_otel_and_correlation(None, "info", {"event": "hello"})

    set_correlation_id(None)
    return event


def test_log_line_carries_trace_and_span_ids_when_span_active():
    event = _capture_log_event(span_active=True, correlation_id="ops-1")
    assert "trace_id" in event
    assert "span_id" in event
    assert event["correlation_id"] == "ops-1"
    # 32-hex trace_id, 16-hex span_id, both lowercase.
    assert len(event["trace_id"]) == 32
    assert len(event["span_id"]) == 16


def test_log_line_omits_trace_id_when_no_span_active():
    event = _capture_log_event(span_active=False, correlation_id="ops-2")
    # trace.get_current_span returns INVALID_SPAN when nothing is active.
    # The binder must not emit trace_id / span_id in that case.
    assert "trace_id" not in event
    assert "span_id" not in event
    assert event["correlation_id"] == "ops-2"


def test_log_line_omits_correlation_id_when_none_bound():
    event = _capture_log_event(span_active=True, correlation_id=None)
    assert "trace_id" in event  # span context present
    assert "correlation_id" not in event


def test_json_renderer_outputs_single_line_per_record(monkeypatch):
    """Smoke test: when LOG_FORMAT=json structlog emits valid JSON."""

    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")

    from sbs_api.config import get_settings
    import sbs_api.observability.logging as logging_module

    get_settings.cache_clear()
    logging_module._CONFIGURED = False

    buffer = io.StringIO()
    structlog.reset_defaults()
    configure_logging()
    # Re-point the configured PrintLogger at the in-memory buffer.
    structlog.configure(
        processors=[
            _bind_otel_and_correlation,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=buffer),
        cache_logger_on_first_use=False,
    )

    log = structlog.get_logger("test")
    log.info("hello_observability", custom_field="x")
    line = buffer.getvalue().strip()
    parsed = json.loads(line)
    assert parsed["event"] == "hello_observability"
    assert parsed["custom_field"] == "x"

    # Restore defaults so other tests see a clean structlog state.
    structlog.reset_defaults()
    logging_module._CONFIGURED = False
    get_settings.cache_clear()
