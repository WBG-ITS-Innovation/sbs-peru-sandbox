# SPDX-License-Identifier: Apache-2.0
"""SQLAlchemy 2.0 declarative base shared by every ORM model.

ADR 0028 keeps the ORM thin: each model is a simple ``DeclarativeBase``
subclass with type-annotated columns. Custom mixins are avoided until a
genuine reuse pattern emerges.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every SBS SupTech ORM model."""

    pass
