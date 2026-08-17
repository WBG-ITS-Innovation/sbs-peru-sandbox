# SPDX-License-Identifier: Apache-2.0
"""Tests for the in-process SSE bus.

The bus is the substrate ADR 0040 §D5 names. These tests cover the
three behaviours that matter for the SSE refresh contract: publish +
subscribe, replay from ``Last-Event-ID``, and bounded ring-buffer
overflow (so a long-disconnected client cannot tie the server up by
asking for events that have aged out).
"""

from __future__ import annotations

import asyncio

import pytest

from sbs_api.sse.manager import SSEBus


@pytest.mark.asyncio
async def test_publish_and_subscribe_delivers_event() -> None:
    bus = SSEBus()
    received: list = []

    async def consumer() -> None:
        async for evt in bus.subscribe("cockpit"):
            received.append(evt)
            if len(received) >= 1:
                return

    task = asyncio.create_task(consumer())
    # Yield so the consumer is registered as a subscriber.
    await asyncio.sleep(0)
    eid = await bus.publish("cockpit", "complaint.received", '{"x":1}')
    await asyncio.wait_for(task, timeout=1.0)

    assert len(received) == 1
    assert received[0].id == eid
    assert received[0].event == "complaint.received"
    assert received[0].data == '{"x":1}'


@pytest.mark.asyncio
async def test_replay_from_last_event_id_only_delivers_newer() -> None:
    bus = SSEBus()
    for _ in range(5):
        await bus.publish("cockpit", "ping", "x")

    received: list = []

    async def consumer() -> None:
        async for evt in bus.subscribe("cockpit", last_event_id=3):
            received.append(evt)
            if len(received) >= 2:
                return

    await asyncio.wait_for(consumer(), timeout=1.0)
    ids = [e.id for e in received]
    assert ids == [4, 5]


@pytest.mark.asyncio
async def test_ring_buffer_drops_oldest_when_capacity_exceeded() -> None:
    bus = SSEBus()
    # Buffer cap is 500; publish 600 events and expect the oldest 100
    # to be dropped from the backlog.
    for _ in range(600):
        await bus.publish("cockpit", "ping", "x")

    received: list = []

    async def consumer() -> None:
        async for evt in bus.subscribe("cockpit", last_event_id=0):
            received.append(evt)
            if len(received) >= 500:
                return

    await asyncio.wait_for(consumer(), timeout=2.0)
    ids = [e.id for e in received]
    # Events 1..100 should have been evicted; we get 101..600.
    assert ids[0] == 101
    assert ids[-1] == 600
    assert len(ids) == 500


@pytest.mark.asyncio
async def test_subscriber_removed_after_iterator_exits() -> None:
    bus = SSEBus()

    async def consumer() -> None:
        # Use `async with` so the generator's finally runs deterministically
        # when we exit — `async for` + return defers cleanup until the
        # generator is garbage-collected, which races the assertion below.
        gen = bus.subscribe("cockpit")
        try:
            await gen.__anext__()
        finally:
            await gen.aclose()

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)
    await bus.publish("cockpit", "ping", "x")
    await asyncio.wait_for(task, timeout=1.0)

    # After explicit aclose() the finally clause has run; subscriber list empty.
    state = bus._topics["cockpit"]
    assert state.subscribers == []


@pytest.mark.asyncio
async def test_publish_to_unknown_topic_creates_topic() -> None:
    """Publishing to a topic that has never been subscribed-to is a no-op
    against subscribers but should not raise."""

    bus = SSEBus()
    eid = await bus.publish("findings", "finding.published", "x")
    assert eid == 1
