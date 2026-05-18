"""ETag helpers.

The ETag is a strong tag derived from the complaint's monotonic
``etag_version`` column plus the ``complaint_id``. Using a hash function
keeps the tag opaque to clients (they cannot reason backwards into the
version number) while remaining deterministic for the server.
"""

from __future__ import annotations

import hashlib


def compute_etag(complaint_id: str, etag_version: int) -> str:
    """Return the strong ETag value, including the surrounding double-quotes."""

    raw = f"{complaint_id}:{etag_version}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:24]
    return f'"{digest}"'
