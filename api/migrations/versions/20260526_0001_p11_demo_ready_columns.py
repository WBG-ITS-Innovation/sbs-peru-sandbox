# SPDX-License-Identifier: Apache-2.0
"""P11 demo-ready overlay — extend complaints + raw_complaints with the
Annex 1-A resolution-side columns the real SBS sample exercises.

Revision ID: 20260526_0001
Revises: 20260524_0001
Create Date: 2026-05-26

The real Annex 1-A sample (data/sbs_sample/SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx)
carries five resolution-side fields that the prior P11A canonical schema
did not store explicitly:

* ``fecha_resolucion``         — FEC_RES (Annex 1-A field 11). Date.
* ``tipo_resolucion``          — TIP_RES. ``favor_usuario`` / ``favor_entidad``.
* ``descripcion_resolucion``   — DET_RES. Redacted resolution narrative.
* ``estado_reclamo``           — EST_REC normalized
                                 (``atendido`` / ``en_proceso`` / ``pendiente``).
* ``monto_pendiente``          — MNT_PEN_REC. Pending amount in PEN.

All five are added as nullable so existing rows backfill to NULL and the
migration is reversible. ``raw_complaints`` gets the symmetric
``raw_descripcion_resolucion`` (the canonical-aligned name for the raw
DET_RES text; the legacy ``raw_response_detail`` column stays in place
during the transition).

No data migration is required. The orchestrator populates the new
columns when the demo / sandbox endpoints receive the corresponding
fields; for institutions that don't send them the columns remain NULL.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260526_0001"
down_revision: str | None = "20260524_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # complaints: five resolution-side columns, all nullable.
    op.add_column(
        "complaints",
        sa.Column("fecha_resolucion", sa.Date(), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("tipo_resolucion", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("descripcion_resolucion", sa.Text(), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("estado_reclamo", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("monto_pendiente", sa.Numeric(12, 2), nullable=True),
    )

    # raw_complaints: symmetrical raw text for the resolution narrative.
    op.add_column(
        "raw_complaints",
        sa.Column("raw_descripcion_resolucion", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("raw_complaints", "raw_descripcion_resolucion")

    op.drop_column("complaints", "monto_pendiente")
    op.drop_column("complaints", "estado_reclamo")
    op.drop_column("complaints", "descripcion_resolucion")
    op.drop_column("complaints", "tipo_resolucion")
    op.drop_column("complaints", "fecha_resolucion")
