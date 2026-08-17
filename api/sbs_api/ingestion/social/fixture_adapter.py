# SPDX-License-Identifier: Apache-2.0
"""FixtureSocialAdapter — reads seeded ``social_signals_fixture`` rows.

The fixture adapter is the production adapter shape minus the API call.
It is ALWAYS used in v1; when real credentials land, swap the
implementation (twitter_adapter / meta_adapter), not the interface.

# DEMO: production rollout requires real social API credentials.
# Adapter interface is production-ready; only the fixture is wired for
# the May/June sandbox. See ADR-0002 (credential plan, to be written).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.social_signal import SocialSignalFixture
from sbs_api.ingestion.social.adapter_base import SocialAdapter, SocialSignalRaw


class FixtureSocialAdapter(SocialAdapter):
    name = "fixture"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def fetch_recent(self, since: datetime) -> list[SocialSignalRaw]:
        rows = (
            await self._session.execute(
                select(SocialSignalFixture).where(
                    SocialSignalFixture.post_authored_at >= since
                )
            )
        ).scalars().all()
        # The fixture stores ALREADY-anonymized text + pre-resolved
        # institution codes / fraud indicators, but we round-trip through
        # the raw shape so the runner's anonymize + resolve + classify
        # path is exercised identically to a live adapter.
        out: list[SocialSignalRaw] = []
        for r in rows:
            out.append(
                SocialSignalRaw(
                    source=r.source,
                    source_post_id=r.source_post_id,
                    post_authored_at=r.post_authored_at,
                    text=r.post_text_es,
                    raw_url=r.raw_url,
                    engagement_score=(
                        float(r.engagement_score)
                        if r.engagement_score is not None
                        else None
                    ),
                )
            )
        return out
