"""Social ingestion runner (P-RESHAPE-6).

For each configured adapter: fetch recent posts, **anonymize** the text
(strip handles + reuse the Triage redaction engine), **resolve** the
mentioned institution codes, **classify** fraud indicators by keyword,
and persist to ``social_signals`` (idempotent on (source, source_post_id)).

Configured via ``SBS_SOCIAL_ADAPTERS`` (comma list). Demo: ``fixture``.
Production: ``twitter,meta,fixture`` etc. Runs every 5 minutes as an arq
cron job.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.social_signal import FRAUD_INDICATORS, SocialSignal
from sbs_api.ingestion.social.adapter_base import SocialAdapter, SocialSignalRaw
from sbs_api.ingestion.social.entity_resolver import resolve_institution_codes
from sbs_api.redaction.engine import redact

log = logging.getLogger(__name__)

_HANDLE = re.compile(r"@\w+")
_LOOKBACK = timedelta(hours=72)

# Deterministic keyword → fraud-indicator-code map (Spanish). The codes
# are the fixed enum in social_signal.FRAUD_INDICATORS.
_FRAUD_KEYWORDS: dict[str, str] = {
    "phishing": "PHISHING_KEYWORD",
    "suplantaci": "PHISHING_KEYWORD",  # suplantación / suplantacion
    "estafa": "SCAM_KEYWORD",
    "fraude": "SCAM_KEYWORD",
    "app falsa": "FAKE_APP_KEYWORD",
    "aplicación falsa": "FAKE_APP_KEYWORD",
    "aplicacion falsa": "FAKE_APP_KEYWORD",
    "falso agente": "FAKE_AGENT_KEYWORD",
    "agente falso": "FAKE_AGENT_KEYWORD",
    "comisión no": "UNAUTHORIZED_FEE_KEYWORD",
    "comision no": "UNAUTHORIZED_FEE_KEYWORD",
    "cobro no autorizado": "UNAUTHORIZED_FEE_KEYWORD",
    "cargo no reconocido": "UNAUTHORIZED_CHARGE_KEYWORD",
    "cargo no autorizado": "UNAUTHORIZED_CHARGE_KEYWORD",
}


@dataclass(frozen=True)
class IngestRunResult:
    adapter: str
    fetched: int
    inserted: int
    reused: int


def anonymize_post_text(text: str) -> str:
    """Strip user handles then run the Triage redaction engine. Handle
    stripping happens first so an @handle is never even seen by NER."""
    handled = _HANDLE.sub("[HANDLE]", text)
    return redact(handled).redacted_text


def classify_fraud_indicators(text: str) -> list[str]:
    lowered = text.lower()
    found: set[str] = set()
    for needle, code in _FRAUD_KEYWORDS.items():
        if needle in lowered:
            found.add(code)
    # Only emit codes from the fixed enum.
    return sorted(c for c in found if c in FRAUD_INDICATORS)


async def _persist_signal(
    session: AsyncSession, *, raw: SocialSignalRaw, now: datetime
) -> bool:
    """Insert one signal. Returns False when (source, source_post_id)
    already exists (idempotent)."""
    existing = (
        await session.execute(
            select(SocialSignal.signal_id).where(
                SocialSignal.source == raw.source,
                SocialSignal.source_post_id == raw.source_post_id,
            )
        )
    ).first()
    if existing is not None:
        return False

    anonymized = anonymize_post_text(raw.text)
    institution_codes = await resolve_institution_codes(session, text=raw.text)
    indicators = classify_fraud_indicators(raw.text)

    session.add(
        SocialSignal(
            signal_id=str(uuid.uuid4()),
            source=raw.source,
            source_post_id=raw.source_post_id,
            captured_at=now,
            post_authored_at=raw.post_authored_at,
            post_text_es=anonymized,
            detected_institution_codes=institution_codes,
            detected_fraud_indicators=indicators,
            engagement_score=raw.engagement_score,
            raw_url=raw.raw_url,
        )
    )
    return True


async def run_social_ingestion(
    session: AsyncSession,
    *,
    adapters: list[SocialAdapter],
    now: datetime | None = None,
) -> list[IngestRunResult]:
    """Run every adapter once and persist new signals."""
    now = now or datetime.now(tz=timezone.utc)
    since = now - _LOOKBACK
    results: list[IngestRunResult] = []
    for adapter in adapters:
        raws = await adapter.fetch_recent(since)
        inserted = 0
        reused = 0
        for raw in raws:
            if await _persist_signal(session, raw=raw, now=now):
                inserted += 1
            else:
                reused += 1
        await session.flush()
        results.append(
            IngestRunResult(
                adapter=adapter.name,
                fetched=len(raws),
                inserted=inserted,
                reused=reused,
            )
        )
    return results


def configured_adapter_names() -> list[str]:
    raw = os.getenv("SBS_SOCIAL_ADAPTERS", "fixture")
    return [a.strip() for a in raw.split(",") if a.strip()]


async def social_ingestion_job(ctx: dict) -> dict:  # pragma: no cover - arq entry
    """arq cron entry — runs every 5 minutes. Builds the configured
    adapters and persists. The fixture adapter needs a session; live
    adapters are constructed without one."""
    from sbs_api.db.session import get_sessionmaker
    from sbs_api.ingestion.social.fixture_adapter import FixtureSocialAdapter
    from sbs_api.ingestion.social.meta_adapter import MetaAdapter
    from sbs_api.ingestion.social.twitter_adapter import TwitterAdapter

    names = configured_adapter_names()
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as session:
        adapters: list[SocialAdapter] = []
        for name in names:
            if name == "fixture":
                adapters.append(FixtureSocialAdapter(session))
            elif name == "twitter":
                adapters.append(TwitterAdapter())
            elif name == "meta":
                adapters.append(MetaAdapter())
        results = await run_social_ingestion(session, adapters=adapters)
        await session.commit()
    return {
        "adapters": [
            {"adapter": r.adapter, "fetched": r.fetched, "inserted": r.inserted}
            for r in results
        ]
    }
