# SPDX-License-Identifier: Apache-2.0
"""FIBrandAlias — handle/brand lookup for social entity resolution.

Maps the surface forms an institution appears under on social media
(display name, @handle, web domain) to its SBS institution code. The
entity resolver consults this table after NER to confirm / supplement
matches.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sbs_api.db.base import Base

ALIAS_KINDS = ("DISPLAY_NAME", "HANDLE", "DOMAIN", "OTHER")


class FIBrandAlias(Base):
    __tablename__ = "fi_brand_aliases"

    alias_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    institution_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("institutions.institution_id"),
        nullable=False,
    )
    # Normalised (lower-cased, @ / scheme stripped) alias used for matching.
    alias_normalized: Mapped[str] = mapped_column(String(128), nullable=False)
    alias_kind: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        Index(
            "ix_fi_brand_aliases_normalized",
            "alias_normalized",
        ),
    )
