# SPDX-License-Identifier: Apache-2.0
"""SocialAdapter ABC + the raw signal shape.

Every adapter (fixture, Twitter, Meta, …) returns a list of
:class:`SocialSignalRaw` from ``fetch_recent``. The runner anonymizes,
resolves entities, classifies fraud indicators, and persists — so the
adapter's only job is to fetch + normalise platform shape.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SocialSignalRaw:
    """Platform-normalised social post, pre-anonymization.

    ``text`` may still contain user handles — the runner strips them
    before storage. ``raw_url`` is audit-only.
    """

    source: str  # one of social_signal.SOCIAL_SOURCES
    source_post_id: str
    post_authored_at: datetime
    text: str
    raw_url: str | None = None
    engagement_score: float | None = None
    # Optional adapter-provided hints; the entity resolver still runs.
    author_handle: str | None = None
    extra: dict = field(default_factory=dict)


class SocialAdapter(abc.ABC):
    """Fetch recent social posts for fraud cross-source detection."""

    name: str

    @abc.abstractmethod
    async def fetch_recent(self, since: datetime) -> list[SocialSignalRaw]:
        """Return posts authored at/after ``since``. Implementations must
        not raise on an empty window — return ``[]``."""
        raise NotImplementedError
