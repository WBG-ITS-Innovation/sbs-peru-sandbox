"""Institution certificate registry — ADR 0031.

Each row maps a leaf certificate (identified by its SHA-256 thumbprint)
to the institution that holds the private key. The CN is denormalised so
the mTLS dependency can resolve institution_id from either the cert
itself (direct mode) or the XFCC ``Subject="CN=..."`` field (proxy mode)
without re-parsing the full X.509 envelope.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class InstitutionCertificate(Base):
    __tablename__ = "institution_certificates"

    sha256_thumbprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("institutions.institution_id"),
        nullable=False,
    )
    cn: Mapped[str] = mapped_column(String(64), nullable=False)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
