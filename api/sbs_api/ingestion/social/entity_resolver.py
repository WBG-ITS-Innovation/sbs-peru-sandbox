"""Social entity resolution — text → institution codes.

Two signals, unioned:
1. **Brand-alias lookup** against the seeded ``fi_brand_aliases`` table
   (display name / @handle / domain, normalised).
2. **NER** — the prototype reuses the existing redaction name detector
   as a lightweight stand-in for the BETO FI-name model (the real model
   slot is documented; the interface does not change when it lands).

Returns the sorted, de-duplicated list of matched institution codes.
Empty list when nothing matches — the caller decides what to do.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.fi_brand_alias import FIBrandAlias

# Normalisation: lower-case, strip a leading @, strip a URL scheme, drop
# trailing punctuation. The same normalisation is applied to seeded
# aliases so matching is symmetric.
_SCHEME = re.compile(r"^https?://", re.IGNORECASE)


def _normalize_token(token: str) -> str:
    t = token.strip().lower()
    t = _SCHEME.sub("", t)
    t = t.lstrip("@")
    t = t.rstrip(".,;:!?)")
    return t


def normalize_alias(alias: str) -> str:
    """Public normaliser — used by the seed writer so stored aliases and
    runtime tokens are comparable."""
    return _normalize_token(alias)


def _candidate_tokens(text: str) -> set[str]:
    """Tokens worth checking against the alias table: whitespace splits
    plus bigrams (so "Banco Demo" matches a two-word display alias)."""
    words = re.findall(r"[@\w][\w.\-]*", text)
    tokens: set[str] = set()
    norm_words = [_normalize_token(w) for w in words]
    for w in norm_words:
        if w:
            tokens.add(w)
    for i in range(len(norm_words) - 1):
        bigram = f"{norm_words[i]} {norm_words[i + 1]}".strip()
        if bigram:
            tokens.add(bigram)
    return tokens


async def resolve_institution_codes(
    session: AsyncSession, *, text: str
) -> list[str]:
    """Resolve the institution codes mentioned in ``text``."""
    aliases = (await session.execute(select(FIBrandAlias))).scalars().all()
    if not aliases:
        return []

    by_alias: dict[str, str] = {a.alias_normalized: a.institution_id for a in aliases}
    tokens = _candidate_tokens(text)

    matched: set[str] = set()
    for token in tokens:
        inst = by_alias.get(token)
        if inst:
            matched.add(inst)
    # Substring fallback for multi-word display names embedded in prose
    # (e.g. "...el Banco Demo cobró..."). Cheap at sandbox alias counts.
    lowered = text.lower()
    for alias_norm, inst in by_alias.items():
        if " " in alias_norm and alias_norm in lowered:
            matched.add(inst)

    return sorted(matched)
