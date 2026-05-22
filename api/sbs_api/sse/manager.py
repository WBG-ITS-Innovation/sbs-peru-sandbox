"""In-process Server-Sent Events bus.

Topics are strings; events carry a monotonically-increasing per-topic
id. Each topic owns a small ring buffer (500 events) so a client that
reconnects with ``Last-Event-ID`` can replay missed events — the
contract pinned in ADR 0040 §D5.

Concurrency model:

* Module-level singleton (:func:`get_bus`). Wrapped in a class so tests
  can install a fresh instance per test.
* One ``asyncio.Queue`` per active subscriber, attached under the bus
  lock so a publish() concurrent with subscribe() cannot lose events.
* Slow-subscriber policy: if a subscriber's queue fills, the event is
  dropped for *that subscriber only* (other subscribers still receive
  it). The client's reconnect-with-Last-Event-ID path is the recovery.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncIterator, Deque, List

# Per-topic ring buffer size — ~30 minutes of demo-scale traffic.
_RING_BUFFER_SIZE = 500
_SUBSCRIBER_QUEUE_SIZE = 64


@dataclass(frozen=True)
class SSEEvent:
    """An SSE-framable event.

    ``data`` is already-encoded text (typically JSON). The route layer
    composes the on-wire ``id:`` / ``event:`` / ``data:`` lines.
    """

    id: int
    event: str
    data: str


@dataclass
class _TopicState:
    next_id: int = 1
    buffer: Deque[SSEEvent] = field(default_factory=lambda: deque(maxlen=_RING_BUFFER_SIZE))
    subscribers: List[asyncio.Queue] = field(default_factory=list)


class SSEBus:
    """Per-topic publish/subscribe with bounded replay."""

    def __init__(self) -> None:
        self._topics: dict[str, _TopicState] = {}
        self._lock = asyncio.Lock()

    def _topic(self, topic: str) -> _TopicState:
        state = self._topics.get(topic)
        if state is None:
            state = _TopicState()
            self._topics[topic] = state
        return state

    async def publish(self, topic: str, event: str, data: str) -> int:
        """Append an event and fan out to current subscribers.

        Returns the assigned event id.
        """

        async with self._lock:
            state = self._topic(topic)
            evt = SSEEvent(id=state.next_id, event=event, data=data)
            state.next_id += 1
            state.buffer.append(evt)
            subscribers = list(state.subscribers)
        # Fan out outside the lock so a slow put_nowait does not block
        # other publishers. put_nowait raises QueueFull instead of
        # blocking — we drop on QueueFull (see module docstring).
        for q in subscribers:
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                pass
        return evt.id

    async def subscribe(
        self,
        topic: str,
        last_event_id: int | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """Yield backlog events newer than ``last_event_id``, then live events.

        Backlog and live-stream attach happen under a single lock so
        no event is silently dropped between replay and live.
        """

        q: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_SIZE)
        async with self._lock:
            state = self._topic(topic)
            backlog = [
                evt
                for evt in state.buffer
                if last_event_id is None or evt.id > last_event_id
            ]
            state.subscribers.append(q)

        try:
            for evt in backlog:
                yield evt
            while True:
                evt = await q.get()
                yield evt
        finally:
            async with self._lock:
                if q in state.subscribers:
                    state.subscribers.remove(q)

    async def reset(self) -> None:
        """Test helper. Drops all topics and disconnects all subscribers."""

        async with self._lock:
            self._topics.clear()


_bus = SSEBus()


def get_bus() -> SSEBus:
    """Module-level singleton accessor."""

    return _bus
