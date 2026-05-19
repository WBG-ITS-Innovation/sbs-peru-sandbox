"""OAuth 2.0 client_credentials registry — ADR 0032.

One row per (institution_id, client_id) tuple. ``client_secret_hash`` is
a salted hash (Argon2id) — the plain secret is never stored. The
``cert_thumbprint_required`` column carries the SHA-256 thumbprint the
issued token will be bound to; when the institution rotates its cert,
the row is updated. Multiple rows per institution are supported so an
institution can run a phased rollout (old cert and new cert both able to
fetch tokens) during cert rotation.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("institutions.institution_id"),
        nullable=False,
    )
    client_secret_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    cert_thumbprint_required: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
