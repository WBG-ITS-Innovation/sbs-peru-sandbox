"""TwitterAdapter — STUB (P-RESHAPE-6).

Implementation skeleton for Twitter / X API v2 recent-search. NOT wired
in v1: ``fetch_recent`` raises ``NotImplementedError`` unless
``SBS_TWITTER_API_KEY`` is set, so a deployment slip cannot silently
issue live API calls. When credentials land, fill in the ``_search``
body — the interface and the runner do not change.
"""

from __future__ import annotations

import os
from datetime import datetime

from sbs_api.ingestion.social.adapter_base import SocialAdapter, SocialSignalRaw

_BEARER_ENV = "SBS_TWITTER_API_KEY"
# X API v2 recent-search endpoint (documented here so the skeleton is
# self-describing; not called in v1).
_RECENT_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


class TwitterAdapter(SocialAdapter):
    name = "twitter"

    def __init__(self) -> None:
        self._bearer = os.getenv(_BEARER_ENV)

    async def fetch_recent(self, since: datetime) -> list[SocialSignalRaw]:
        if not self._bearer:
            raise NotImplementedError(
                f"TwitterAdapter requires {_BEARER_ENV}. The Twitter/X API v2 "
                f"recent-search integration is stubbed for the sandbox; set "
                f"the bearer token and implement _search() to enable it. "
                f"See ADR-0002 (credential plan)."
            )
        # Production skeleton (not exercised in v1):
        #   query = "(banco OR estafa OR phishing) lang:es"
        #   params = {"query": query, "start_time": since.isoformat(),
        #             "tweet.fields": "created_at,public_metrics"}
        #   async with httpx.AsyncClient() as c:
        #       resp = await c.get(_RECENT_SEARCH_URL, params=params,
        #           headers={"Authorization": f"Bearer {self._bearer}"})
        #   ... map resp.json()["data"] → SocialSignalRaw ...
        raise NotImplementedError("Twitter live search not implemented in v1")
