# SPDX-License-Identifier: Apache-2.0
"""Helper for testing SSE endpoints without blocking on the infinite body.

``httpx.ASGITransport`` runs the ASGI app to completion before returning a
``Response`` (it appends every body chunk into a list and waits for
``more_body=False``). SSE handlers never send ``more_body=False``, so any
plain ``client.get()`` or ``client.stream()`` test of an SSE endpoint
deadlocks the test runner. This helper drives the ASGI protocol
directly: it captures ``http.response.start`` to extract status + headers,
then signals ``http.disconnect`` and unwinds the route's generator.

Used by the SSE topic role-gate tests in
``test_audit_and_sse_completeness.py`` and ``test_findings_endpoints.py``.
"""

from __future__ import annotations

import asyncio
from typing import Mapping


async def open_sse_head_only(
    app,
    path: str,
    headers: Mapping[str, str],
    *,
    timeout: float = 2.0,
) -> tuple[int, dict[bytes, bytes]]:
    """Return ``(status, headers)`` from an SSE endpoint without reading the body.

    Parameters
    ----------
    app:
        The ASGI application (e.g. the FastAPI instance under test).
    path:
        Request path, e.g. ``"/v1/internal/sse/findings"``.
    headers:
        Request headers. Values are encoded as latin-1.
    timeout:
        Maximum seconds to wait for ``http.response.start``.

    Raises
    ------
    asyncio.TimeoutError:
        If the app does not emit ``http.response.start`` within ``timeout``.
    """

    scope: dict = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in headers.items()
        ],
        "state": {},
    }

    start_event = asyncio.Event()
    disconnect_event = asyncio.Event()
    request_delivered = False
    response_status: int | None = None
    response_headers: dict[bytes, bytes] = {}

    async def receive() -> dict:
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        # Subsequent calls (e.g. from StreamingResponse's listen_for_disconnect)
        # block until we signal disconnect, then surface it. This is the
        # same shape ASGI servers use to tell the app the client went away.
        await disconnect_event.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        nonlocal response_status, response_headers
        mtype = message["type"]
        if mtype == "http.response.start":
            response_status = int(message["status"])
            response_headers = {k: v for (k, v) in message.get("headers") or []}
            start_event.set()
        # Body chunks are discarded — we only care about the response head.

    task = asyncio.create_task(app(scope, receive, send))
    try:
        await asyncio.wait_for(start_event.wait(), timeout=timeout)
    finally:
        disconnect_event.set()
        # Give the route's finally-block a moment to clean up.
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    assert response_status is not None, "ASGI app never emitted http.response.start"
    return response_status, response_headers
