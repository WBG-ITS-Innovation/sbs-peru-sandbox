# SPDX-License-Identifier: Apache-2.0
"""Reject oversize request bodies before route dispatch.

Uvicorn's default body size is generous; this middleware caps it at
``MAX_REQUEST_BODY_BYTES`` (default 256 KiB) and returns 413 with the
stable code ``REQUEST_BODY_TOO_LARGE``. The 413 ProblemDetail is emitted
directly through the ASGI ``send`` channel (no ``JSONResponse``) because
the middleware sits outside FastAPI's exception-handler chain.

ADR 0028 amendment notes:

* **F.2** — The 413 response carries ``X-Correlation-Id`` and
  ``traceparent``. With the pure-ASGI conversion (P10 SSE close-out)
  those headers are added by the surrounding middlewares' wrapped
  ``send`` callbacks; this middleware does not need to write them
  manually.
* **F.3** — Bodyful requests are read chunk-by-chunk and the size cap
  is enforced on the running total, so a client lying about
  ``Content-Length`` cannot force a full-body allocation.
* **P10 SSE close-out** — Pure ASGI shape (not ``BaseHTTPMiddleware``).
  ``receive()`` is never called for bodyless methods (GET, HEAD,
  OPTIONS, DELETE, TRACE), which is what kept the SSE
  ``listen_for_disconnect`` task from getting a spurious
  ``http.request`` message when stacked under other middlewares.
"""

from __future__ import annotations

import json
from typing import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sbs_api.config import Settings, get_settings
from sbs_api.errors.exceptions import BatchFileTooLarge, RequestBodyTooLarge, SBSAPIException

PROBLEM_CONTENT_TYPE = b"application/problem+json"

# ADR 0034: the Tier 2 multipart upload may carry up to
# `settings.max_batch_file_bytes` of CSV, which is two orders of magnitude
# larger than the general default. The middleware applies a per-path cap
# on these endpoints and uses BATCH_FILE_TOO_LARGE as the error code so
# the integrator's error handler can distinguish "your batch is too big"
# from "your JSON payload was wrong".
_BATCH_UPLOAD_PATH = "/v1/batches"

# Methods that semantically carry no request body. We never call
# ``receive()`` on these — SSE handlers (GET /v1/internal/sse/*) rely on
# this so their StreamingResponse's listen_for_disconnect task observes
# a clean receive channel.
_BODYLESS_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE", "TRACE"})


def _limit_for(path: str, method: str, settings: Settings) -> tuple[int, type[SBSAPIException]]:
    """Return (max_bytes, exception_class) for the request shape."""

    if method == "POST" and path == _BATCH_UPLOAD_PATH:
        return settings.max_batch_file_bytes, BatchFileTooLarge
    return settings.max_request_body_bytes, RequestBodyTooLarge


def _read_header(
    headers: Iterable[tuple[bytes, bytes]], name_lower: bytes
) -> bytes | None:
    for raw_name, raw_value in headers:
        if raw_name.lower() == name_lower:
            return raw_value
    return None


async def _send_413(
    send: Send, exc: SBSAPIException, *, settings: Settings
) -> None:
    """Emit the 413 ProblemDetail directly via the ASGI send channel.

    ``X-Correlation-Id`` and ``traceparent`` are not written here — the
    surrounding pure-ASGI middlewares wrap ``send`` and add those
    headers on the outbound ``http.response.start``.
    """

    body = json.dumps(
        {
            "type": f"{settings.problem_type_namespace}/{exc.type_suffix}",
            "title": exc.title,
            "status": exc.status,
            "code": exc.code,
            "detail": exc.detail,
        }
    ).encode("utf-8")
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", PROBLEM_CONTENT_TYPE),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    await send(
        {
            "type": "http.response.start",
            "status": exc.status,
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


class BodySizeLimitMiddleware:
    """Enforce per-path body-size caps as a pure ASGI middleware.

    Install order (outer → inner at request time):
        traceparent → correlation_id → body_size_limit

    The 413 ProblemDetail therefore inherits ``X-Correlation-Id`` and
    ``traceparent`` from the surrounding middlewares' wrapped ``send``.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int | None = None) -> None:
        self.app = app
        self._override_max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        method: str = scope.get("method", "GET")
        path: str = scope.get("path", "")
        max_bytes, exc_cls = _limit_for(path, method, settings)
        if self._override_max is not None:
            # Test override: same cap on every route.
            max_bytes = self._override_max
            exc_cls = RequestBodyTooLarge

        headers = scope.get("headers", [])
        raw_cl = _read_header(headers, b"content-length")
        declared: int | None
        if raw_cl is None:
            declared = None
        else:
            try:
                declared = int(raw_cl.decode("ascii"))
            except (ValueError, UnicodeDecodeError):
                declared = None

        # Fast path: Content-Length over the cap is rejected without
        # touching receive(). Works for any method.
        if declared is not None and declared > max_bytes:
            await _send_413(
                send,
                exc_cls(
                    detail=(
                        f"Request body declared {declared} bytes; "
                        f"server maximum is {max_bytes} bytes."
                    )
                ),
                settings=settings,
            )
            return

        # Bodyless methods: never consume receive(). SSE handlers
        # depend on this — see module docstring.
        if method in _BODYLESS_METHODS:
            await self.app(scope, receive, send)
            return

        # Bodyful methods: buffer the body chunk-by-chunk so we can
        # enforce the cap on the running total, then replay it
        # downstream via a wrapped receive().
        accumulated = bytearray()
        # We collect each message; the last one carries more_body=False.
        # ``http.disconnect`` mid-read means the client gave up — we
        # forward it to the app via the wrapped receive once the app
        # starts; here we just stop reading.
        saw_disconnect = False
        while True:
            message = await receive()
            mtype = message["type"]
            if mtype == "http.disconnect":
                saw_disconnect = True
                break
            if mtype != "http.request":
                # Unknown message — pass through to the app verbatim
                # by buffering it and continuing. ASGI does not define
                # other message types for HTTP scope today.
                continue
            chunk = message.get("body", b"") or b""
            accumulated.extend(chunk)
            if len(accumulated) > max_bytes:
                await _send_413(
                    send,
                    exc_cls(
                        detail=(
                            f"Request body exceeded {max_bytes} bytes "
                            f"after streaming (declared "
                            f"{declared if declared is not None else 'unknown'} "
                            f"bytes)."
                        )
                    ),
                    settings=settings,
                )
                # Drain remaining body chunks so the client's
                # connection state matches what we just sent.
                if message.get("more_body", False):
                    while True:
                        m = await receive()
                        if m["type"] != "http.request":
                            break
                        if not m.get("more_body", False):
                            break
                return
            if not message.get("more_body", False):
                break

        body_bytes = bytes(accumulated)

        if saw_disconnect:
            # Client disconnected before sending the full body. We
            # still hand control to the app with a receive() that
            # surfaces the disconnect so the route can shut down
            # cleanly.
            async def disconnect_receive() -> Message:
                return {"type": "http.disconnect"}

            await self.app(scope, disconnect_receive, send)
            return

        body_emitted = False

        async def replay_receive() -> Message:
            nonlocal body_emitted
            if not body_emitted:
                body_emitted = True
                return {
                    "type": "http.request",
                    "body": body_bytes,
                    "more_body": False,
                }
            # Body already replayed — pass through to the real
            # receive so ``http.disconnect`` (and any future ASGI
            # message types) reach the app unchanged.
            return await receive()

        await self.app(scope, replay_receive, send)
