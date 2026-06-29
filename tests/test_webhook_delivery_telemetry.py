# SPDX-License-Identifier: Apache-2.0
"""Webhook delivery telemetry — Workstream F.3 (non-droppable).

Workstream G's smoke test asserts that retry behaviour is observable
via the canonical structlog event schema named in ADR 0035:

    webhook.delivery.attempt   delivery_id  attempt_num  http_status
                               latency_ms   outcome      next_retry_at

    webhook.delivery.dead_letter   delivery_id  attempt_count  failure_reason

This test pins the canonical schema at source level so a refactor that
renames a field is caught here instead of breaking the smoke test.
The runtime emission is exercised by test_webhook_delivery.py.
"""

from __future__ import annotations

from pathlib import Path

_DELIVERY_SRC = (
    Path(__file__).resolve().parents[1]
    / "api/sbs_api/webhook/delivery.py"
)


def _src() -> str:
    return _DELIVERY_SRC.read_text(encoding="utf-8")


def test_attempt_event_name_present():
    assert "webhook.delivery.attempt" in _src()


def test_dead_letter_event_name_present():
    assert "webhook.delivery.dead_letter" in _src()


def test_attempt_event_carries_canonical_fields():
    src = _src()
    # The `_record_attempt` helper builds the event; the kwargs passed
    # to ``_logger.info("webhook.delivery.attempt", ...)`` are the
    # canonical schema.
    for field in (
        "delivery_id",
        "attempt_num",
        "http_status",
        "latency_ms",
        "outcome",
        "next_retry_at",
    ):
        assert field in src, f"webhook.delivery.attempt missing field {field!r}"


def test_dead_letter_event_carries_canonical_fields():
    src = _src()
    for field in ("delivery_id", "attempt_count", "failure_reason"):
        assert field in src, f"webhook.delivery.dead_letter missing field {field!r}"


def test_attempt_history_json_schema_documented():
    """The webhook_deliveries.attempt_history JSON shape is in the model docstring.

    ADR 0035 §webhook-deliveries-telemetry: the schema is documented
    on the SQLAlchemy model so SDK writers can replicate it.
    """

    model_src = (
        Path(__file__).resolve().parents[1]
        / "api/sbs_api/db/models/webhook_delivery.py"
    ).read_text(encoding="utf-8")
    for field in ("attempt_num", "http_status", "latency_ms", "outcome"):
        assert field in model_src
