# SPDX-License-Identifier: Apache-2.0
"""Alembic environment.

Wires async SQLAlchemy and Pydantic Settings into Alembic's offline / online
migration modes. The ``target_metadata`` points at :data:`sbs_api.db.base.Base.metadata`;
importing :mod:`sbs_api.db.models` is enough to populate it because each
ORM module declares its tables at import time.
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# Make ``sbs_api`` importable when Alembic runs from the ``api/`` directory.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import engine_from_config, pool  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: E402

from sbs_api.config import get_settings  # noqa: E402
from sbs_api.db.base import Base  # noqa: E402
from sbs_api.db import models  # noqa: F401,E402  -- import for side-effects

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from runtime settings so test runs and Compose
# both pick up the right DSN.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without a live database connection."""

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""

    url = config.get_main_option("sqlalchemy.url") or ""
    if url.startswith("postgresql+asyncpg") or "asyncpg" in url:
        asyncio.run(run_async_migrations())
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
