"""Capture uvicorn's SSL transport on every request.

Uvicorn 0.47 does not implement the ASGI TLS extension. The peer cert
IS available on the underlying ``_SSLProtocolTransport`` held by
``RequestResponseCycle.transport``. This middleware walks the asyncio
task at request entry to find that transport, extracts the DER bytes
of the verified peer cert, and stashes them on ``request.state``.

The mTLS dependency (`sbs_api.dependencies.mtls`) then reads from
``request.state.peer_cert_der``.

The frame walk runs OUTSIDE FastAPI's dependency-injection stack
(this is an ASGI middleware, not a FastAPI dependency), so the call
stack is short enough that ``RequestResponseCycle`` is reliably 1-2
frames up.

The dependency on uvicorn-internal class names is acknowledged as a
known-fragile seam. Part 9 will either upgrade to a uvicorn release
that ships the standard ASGI TLS extension, or migrate the serve
layer to hypercorn (which already exposes scope['extensions']['tls']).
Until then this middleware is the bridge.
"""

from __future__ import annotations

import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send


def _extract_peer_cert_der() -> bytes | None:
    task = asyncio.current_task()
    if task is None:
        return None
    coro = task.get_coro()
    if coro is None:
        return None
    frame = getattr(coro, "cr_frame", None)
    depth = 0
    while frame is not None and depth < 200:
        for name, val in list(frame.f_locals.items()):
            if val is None:
                continue
            if type(val).__name__ != "RequestResponseCycle":
                continue
            transport = getattr(val, "transport", None)
            if transport is None:
                continue
            try:
                ssl_object = transport.get_extra_info("ssl_object")
            except Exception:
                ssl_object = None
            if ssl_object is None:
                continue
            try:
                der = ssl_object.getpeercert(binary_form=True)
            except Exception:
                der = None
            if der:
                return der
        frame = frame.f_back
        depth += 1
    return None


class MtlsTransportCaptureMiddleware:
    """ASGI middleware that captures the peer cert DER on request entry."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            der = _extract_peer_cert_der()
            if der is not None:
                state = scope.setdefault("state", {})
                state["peer_cert_der"] = der
        await self.app(scope, receive, send)
