"""MetaAdapter — STUB (P-RESHAPE-6).

Skeleton for Meta (Facebook/Instagram) Graph API public-content search.
NOT wired in v1: ``fetch_recent`` raises ``NotImplementedError`` unless
``SBS_META_API_KEY`` is set. Same treatment as the Twitter stub — the
interface is production-ready, only the API call is deferred.
"""

from __future__ import annotations

import os
from datetime import datetime

from sbs_api.ingestion.social.adapter_base import SocialAdapter, SocialSignalRaw

_TOKEN_ENV = "SBS_META_API_KEY"


class MetaAdapter(SocialAdapter):
    name = "meta"

    def __init__(self) -> None:
        self._token = os.getenv(_TOKEN_ENV)

    async def fetch_recent(self, since: datetime) -> list[SocialSignalRaw]:
        if not self._token:
            raise NotImplementedError(
                f"MetaAdapter requires {_TOKEN_ENV}. Meta Graph API public-"
                f"content search is stubbed for the sandbox. See ADR-0002 "
                f"(credential plan)."
            )
        raise NotImplementedError("Meta live search not implemented in v1")
