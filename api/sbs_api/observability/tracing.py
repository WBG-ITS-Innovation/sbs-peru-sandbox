"""OpenTelemetry SDK wiring.

ADR 0028 §4 makes OpenTelemetry the single owner of W3C trace context.
The custom ``traceparent`` middleware observes the OTel-managed context and
echoes it on the response; it does **not** parse or generate trace context
independently. That decision avoids a class of dual-context bugs in which
the ProblemDetail's ``trace_id`` disagrees with the exporter's span
``trace_id``.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from sbs_api.config import get_settings

_CONFIGURED: bool = False


def configure_tracing() -> None:
    """Configure the OTel tracer provider. Idempotent across invocations."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    if settings.otel_traces_exporter == "none":
        # Set a no-op provider so the API call sites do not need to branch.
        # The default global provider raises noisy warnings when un-set; we
        # install a minimal provider with no processors.
        trace.set_tracer_provider(
            TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
        )
        _CONFIGURED = True
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )

    if settings.otel_traces_exporter == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    elif settings.otel_traces_exporter == "otlp":
        # OTLP HTTP exporter; the gRPC one is left to Part 9. Endpoint is
        # configurable and only required when this branch is selected.
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        endpoint = settings.otel_exporter_otlp_endpoint
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )

    trace.set_tracer_provider(provider)
    _CONFIGURED = True


def reset_tracing_for_test() -> None:
    """Test-only hook: reset module state so a fresh ``configure_tracing`` runs.

    OTel's global provider survives between tests by design; for tests that
    assert tracer-provider state, call this in the fixture's teardown.
    """

    global _CONFIGURED
    _CONFIGURED = False
