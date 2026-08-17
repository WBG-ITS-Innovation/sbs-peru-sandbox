# SPDX-License-Identifier: Apache-2.0
"""Redaction at the cloud egress boundary (v0.2.0).

``cloud`` is the only provider that sends complaint content to infrastructure
the supervisory authority does not run, so the guarantee under test is blunt:
**nothing the redaction engine recognises as PII appears in the payload handed
to the transport.** These tests assert it over the request body itself rather
than over any intermediate representation, because the request body is what
leaves the process.

The audit side is covered too: counts by kind are recorded, and no text —
neither raw nor redacted — is ever stored.
"""

from __future__ import annotations

import json

import pytest

from sbs_api.agents.providers.egress import redact_messages


# The canonical PII bundle, as it would arrive in a narrative.
DNI = "12345678"
RUC = "20512345678"
PHONE = "987 654 321"
EMAIL = "juan.perez@sandbox.example.com"
ACCOUNT = "0011-2233-4455-6677"
NAME = "Carlos Rodríguez Mendoza"

NARRATIVE = (
    f"El cliente {NAME}, DNI {DNI}, de la empresa RUC {RUC}, "
    f"reporta un cargo no autorizado de S/ 245.00 en la cuenta {ACCOUNT}. "
    f"Contacto: +51 {PHONE}, correo {EMAIL}."
)

ALL_PII = (DNI, RUC, PHONE, EMAIL, ACCOUNT, NAME)


def _payload(messages):
    """Serialise exactly what would go on the wire, for leak assertions."""
    return json.dumps(messages, ensure_ascii=False)


def test_no_pii_survives_in_the_outbound_payload():
    messages = [
        {"role": "system", "content": "You are the triage agent."},
        {"role": "user", "content": NARRATIVE},
    ]
    out, counts = redact_messages(messages)
    blob = _payload(out)

    for needle in ALL_PII:
        assert needle not in blob, f"{needle!r} egressed unredacted"

    # Every kind in the bundle was actually detected — a test that passed
    # because redaction deleted everything, or because detection silently
    # stopped working, would be worse than useless here.
    for kind in ("pii_id", "pii_ruc", "pii_phone", "pii_email", "pii_account", "pii_name"):
        assert counts.get(kind, 0) >= 1, f"{kind} not detected in the bundle"


def test_tool_results_and_tool_call_arguments_are_redacted():
    """PII can reach the wire through a tool result or a replayed tool call."""

    messages = [
        {"role": "user", "content": "Analiza el reclamo."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "arguments": json.dumps({"dni": DNI, "ruc": RUC}),
                    },
                }
            ],
        },
        {"role": "tool", "content": json.dumps({"holder": NAME, "account": ACCOUNT})},
    ]
    out, counts = redact_messages(messages)
    blob = _payload(out)

    for needle in (DNI, RUC, NAME, ACCOUNT):
        assert needle not in blob, f"{needle!r} egressed via a tool payload"
    assert counts.get("pii_id", 0) >= 1
    assert counts.get("pii_account", 0) >= 1


def test_multimodal_content_parts_are_redacted():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"DNI {DNI}"},
                {"type": "text", "text": f"RUC {RUC}"},
            ],
        }
    ]
    out, counts = redact_messages(messages)
    blob = _payload(out)

    assert DNI not in blob
    assert RUC not in blob
    assert counts["pii_id"] >= 1
    assert counts["pii_ruc"] >= 1


def test_the_agents_own_message_history_is_not_mutated():
    """Redaction must not change how a run behaves for other providers.

    The same agent code runs against on_prem, replay and cloud. If the cloud
    path rewrote the shared message list in place, an identical run would
    diverge depending on who served it.
    """

    original = NARRATIVE
    messages = [{"role": "user", "content": original}]
    redact_messages(messages)

    assert messages[0]["content"] == original
    assert DNI in messages[0]["content"]


def test_clean_payload_reports_no_entities():
    """An empty count dict must mean 'nothing detected', not 'not run'."""

    messages = [
        {"role": "system", "content": "You are the triage agent."},
        {"role": "user", "content": "El cliente reporta una demora en la atención."},
    ]
    out, counts = redact_messages(messages)

    assert counts == {}
    assert out[1]["content"] == "El cliente reporta una demora en la atención."


def test_counts_are_counts_and_carry_no_values():
    """The audit row's payload must be non-identifying by construction."""

    _, counts = redact_messages([{"role": "user", "content": NARRATIVE}])

    assert all(isinstance(k, str) for k in counts)
    assert all(isinstance(v, int) for v in counts.values())
    serialised = json.dumps(counts, ensure_ascii=False)
    for needle in ALL_PII:
        assert needle not in serialised


def test_audit_row_columns_cannot_hold_text():
    """No text column on cloud_inference_audit — enforced, not just intended.

    The table's whole justification is that it evidences the egress without
    becoming a second copy of the complaint. A future column called something
    like ``prompt`` or ``redacted_text`` would quietly undo that, so the shape
    is asserted here rather than left to review.
    """

    from sbs_api.db.models.cloud_inference_audit import CloudInferenceAudit

    allowed = {
        "id",
        "complaint_id",
        "agent_name",
        "model_id",
        "redaction_applied",
        "entity_counts",
        "message_count",
        "redacted_chars",
        "created_at",
    }
    actual = {c.name for c in CloudInferenceAudit.__table__.columns}
    assert actual == allowed, (
        f"cloud_inference_audit columns changed: {actual ^ allowed}. This table "
        f"must never gain a column that can hold narrative text, raw or "
        f"redacted — see the model docstring."
    )


@pytest.mark.parametrize(
    "separator_form",
    ["DNI 12345678", "DNI: 12345678", "DNI:12345678", "DNI.12345678", "dni 12345678"],
)
def test_every_documented_identifier_form_is_caught_at_egress(separator_form):
    """The bounded-separator fix must not have narrowed egress coverage."""

    out, counts = redact_messages([{"role": "user", "content": separator_form}])
    assert "12345678" not in _payload(out)
    assert counts.get("pii_id", 0) >= 1
