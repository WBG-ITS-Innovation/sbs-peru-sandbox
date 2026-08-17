# SPDX-License-Identifier: Apache-2.0
"""Redaction at the egress boundary — what leaves the process for the cloud.

Every other provider keeps prompt content inside the trust boundary:
``on_prem`` talks to a vLLM the authority runs, ``replay`` reads a committed
fixture, ``mock`` computes. ``cloud`` is the one that puts complaint narratives
on someone else's infrastructure, and it is therefore the one place where "the
agent layer redacts PII" has to be enforced rather than assumed.

**Why here and not upstream.** The agents already redact: the live-ingestion
orchestrator anonymises before writing, and the investigation agent works from
redacted narratives. But that is a property of individual call sites, and a new
agent, a new tool result, or a reordered prompt can quietly reintroduce raw
text. Placing the redaction pass at the provider boundary makes it structural:
the last thing that happens before the HTTP request is built is a redaction
sweep over every string in the payload, whatever assembled it. A missed call
site upstream becomes a redundant redaction rather than a disclosure.

**What it covers.** Every ``content`` string on every message, and the
``arguments`` blob of any assistant tool call carried in the history. That is
the whole of what the Chat Completions request body carries from us.

**What it costs.** Redaction is deterministic and bounded (see
``redaction/engine.py``); over-redaction is the safe failure mode. A model that
sees ``<DNI_1>`` where a document number was is being asked to reason about a
complaint, not to know the number, which is the posture ADR 0001 describes. It
does mean a tool-result JSON blob carrying an 11-digit unquoted number can come
back with a ``<RUC_1>`` token in place of the digits, so the payload is no
longer strictly parseable JSON — the model reads it as text and we never
re-parse it, but it is worth knowing before debugging a prompt.

The audit trail for what this produced is ``cloud_inference_audit``, one row per
outbound call, carrying counts by entity kind and **never** the text — neither
the raw text nor the redacted text. A table that stored the redacted narrative
would be a second copy of the complaint, and a table that stored the raw one
would defeat the point of the exercise.
"""

from __future__ import annotations

from typing import Any

from sbs_api.redaction import redact


def _redact_str(text: str, counts: dict[str, int]) -> str:
    """Redact one string, accumulating entity counts by kind."""

    result = redact(text)
    for entity in result.entities:
        counts[entity.kind] = counts.get(entity.kind, 0) + 1
    return result.redacted_text


def redact_messages(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return ``(redacted_messages, entity_counts_by_kind)``.

    The input is never mutated: agents keep their own message history, and
    silently rewriting it under them would make the same run behave differently
    depending on which provider served it. Only the copy handed to the
    transport is redacted.

    ``entity_counts_by_kind`` is keyed by the redaction engine's kinds
    (``pii_id``, ``pii_ruc``, ``pii_phone``, ``pii_email``, ``pii_account``,
    ``pii_name``) and omits kinds with no detections, so an empty dict means
    the payload carried nothing the engine recognises as PII.
    """

    counts: dict[str, int] = {}
    out: list[dict[str, Any]] = []

    for message in messages:
        copy = dict(message)

        content = copy.get("content")
        if isinstance(content, str):
            copy["content"] = _redact_str(content, counts)
        elif isinstance(content, list):
            # Multimodal / content-part form: redact the text parts, leave
            # anything else untouched rather than guessing at its shape.
            parts: list[Any] = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    part = dict(part)
                    part["text"] = _redact_str(part["text"], counts)
                parts.append(part)
            copy["content"] = parts

        # Assistant turns replay the model's own tool calls back to it. The
        # arguments were generated from already-redacted input, so this is
        # belt-and-braces — but a tool call that echoed a narrative fragment
        # would otherwise egress unredacted on the *next* turn.
        tool_calls = copy.get("tool_calls")
        if isinstance(tool_calls, list):
            rewritten: list[Any] = []
            for call in tool_calls:
                if isinstance(call, dict) and isinstance(call.get("function"), dict):
                    call = dict(call)
                    fn = dict(call["function"])
                    if isinstance(fn.get("arguments"), str):
                        fn["arguments"] = _redact_str(fn["arguments"], counts)
                    call["function"] = fn
                rewritten.append(call)
            copy["tool_calls"] = rewritten

        out.append(copy)

    return out, counts
