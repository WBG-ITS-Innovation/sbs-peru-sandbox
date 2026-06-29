# SPDX-License-Identifier: Apache-2.0
"""GET /v1/internal/sse/{topic} — server-sent events for the supervisor UI.

The Next.js server is the only client; it proxies the byte-stream
through to the browser. The browser's EventSource handles
``Last-Event-ID`` natively; the Next.js proxy forwards that header so
the server replays from the ring buffer.

Snapshot-then-delta protocol (ADR 0040 §D5):

1. On connect (no ``Last-Event-ID``), the server emits one
   ``event: snapshot`` carrying the full cockpit payload as `data:`.
   That event's ``id:`` is the high-water mark — the client treats
   everything in the snapshot as "already applied" up to that id.
2. After the snapshot, the server streams ``event: delta`` events
   produced by upstream activity (complaint.received,
   anomaly.detected, signal.threshold.crossed).
3. On reconnect with ``Last-Event-ID: N``, the server skips the
   snapshot and replays buffered events with id > N. If the buffer
   has expired the missed window, the server emits a
   ``event: resync-required`` and the client re-fetches the snapshot.
4. The server emits an SSE comment heartbeat every 25 seconds so
   proxies do not idle the connection out.

Authentication: shared-secret Bearer same as ``/v1/internal/audit``.
Role-scoping per topic is reserved for ADR 0043 (WS7); today the
``cockpit`` topic is the only one configured and any authenticated
caller can subscribe.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.cockpit import build_cockpit_snapshot
from sbs_api.dependencies.db import get_session
from sbs_api.routes._internal_auth import (
    parse_roles_header,
    verify_internal_secret,
)
from sbs_api.sse import get_bus

router = APIRouter(prefix="/internal", tags=["Internal"])

# Topics the supervisor UI subscribes to. Role-scoping per topic is
# inline below until WS7 + ADR 0043 lifts it to a declarative table.
_ALLOWED_TOPICS = frozenset({"cockpit", "findings", "approvals"})

# Per-topic minimum-required-role set — the caller must hold at least
# one of the listed roles on the X-SBS-Role header.
_TOPIC_ROLES: dict[str, frozenset[str]] = {
    "cockpit": frozenset(
        {"sbs:conduct:supervisor", "sbs:conduct:analyst", "sbs:conduct:head"}
    ),
    "findings": frozenset(
        {"sbs:conduct:supervisor", "sbs:conduct:analyst", "sbs:conduct:head"}
    ),
    # Approvals topic restricted to head + analyst — supervisor (María)
    # does not subscribe per ADR 0040 §D7's demo-scope outline.
    "approvals": frozenset({"sbs:conduct:analyst", "sbs:conduct:head"}),
}
_HEARTBEAT_SECONDS = 25.0


@router.get(
    "/sse/{topic}",
    dependencies=[Depends(verify_internal_secret)],
)
async def sse_stream(
    topic: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    if topic not in _ALLOWED_TOPICS:
        raise HTTPException(status_code=404, detail=f"Unknown topic: {topic}")

    granted_roles = parse_roles_header(x_sbs_role)
    required_roles = _TOPIC_ROLES.get(topic, frozenset())
    if granted_roles.isdisjoint(required_roles):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        parsed_last = int(last_event_id) if last_event_id else None
    except ValueError:
        parsed_last = None

    snapshot_payload = (
        await build_cockpit_snapshot(session) if topic == "cockpit" else None
    )

    async def stream() -> AsyncIterator[bytes]:
        yield _frame_comment("connected").encode("utf-8")

        bus = get_bus()
        # On a fresh connection (no Last-Event-ID), emit one snapshot
        # so the client renders a stable initial state. On reconnect
        # the snapshot is skipped — the buffer-replay is the deltas
        # the client missed.
        if parsed_last is None and snapshot_payload is not None:
            # The snapshot is its own event with id=0 by convention —
            # the next delta the bus emits will be id>=1, and the
            # client treats id<=0 as "already applied".
            yield _frame_event(
                event_id=0,
                event_name="snapshot",
                data=json.dumps(snapshot_payload, default=str),
            ).encode("utf-8")

        # Keep the stream open even when there are no live events.
        #
        # Do not poll request.is_disconnected() here. Under the current
        # middleware stack it can report a disconnect after the snapshot and
        # close the stream. StreamingResponse cancels this generator on a real
        # client disconnect, and the subscriber is cleaned up in finally.
        last_seen = parsed_last
        subscriber = bus.subscribe(topic, last_event_id=last_seen)
        next_event_task = asyncio.create_task(anext(subscriber))

        try:
            while True:
                done, _pending = await asyncio.wait(
                    {next_event_task}, timeout=_HEARTBEAT_SECONDS
                )

                if next_event_task not in done:
                    yield _frame_comment("heartbeat").encode("utf-8")
                    continue

                try:
                    evt = next_event_task.result()
                except StopAsyncIteration:
                    await asyncio.sleep(0.1)
                    subscriber = bus.subscribe(topic, last_event_id=last_seen)
                    next_event_task = asyncio.create_task(anext(subscriber))
                    continue

                last_seen = evt.id
                yield _frame_event(
                    event_id=evt.id, event_name=evt.event, data=evt.data
                ).encode("utf-8")
                next_event_task = asyncio.create_task(anext(subscriber))
        finally:
            next_event_task.cancel()
            try:
                await subscriber.aclose()
            except Exception:
                pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable nginx/proxy buffering so events land at the
            # client as they're emitted.
            "X-Accel-Buffering": "no",
        },
    )


def _frame_event(event_id: int, event_name: str, data: str) -> str:
    """Compose one SSE-framed event.

    Per W3C EventSource spec each event ends in a blank line. Each
    ``data:`` line carries one line of payload; we encode the JSON as
    a single line so a single ``data:`` line is sufficient.
    """

    safe_data = data.replace("\r\n", "\n").replace("\n", "\\n")
    return f"id: {event_id}\nevent: {event_name}\ndata: {safe_data}\n\n"


def _frame_comment(text: str) -> str:
    """SSE comment line — ignored by EventSource, used for heartbeats."""

    return f": {text}\n\n"
