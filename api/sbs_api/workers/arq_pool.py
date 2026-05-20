"""arq Redis pool lifecycle for the API process.

The API process holds one arq Redis pool for enqueueing jobs onto the
worker queue. Pool construction is lazy so processes that never enqueue
(unit tests, CLI helpers) do not need Redis. Tests inject a fake pool
via :func:`override_arq_pool_for_test`.
"""

from __future__ import annotations

from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool

from sbs_api.config import get_settings

_pool: ArqRedis | None = None


def _redis_settings_from_url(url: str) -> RedisSettings:
    """Convert a redis://host:port/db URL into arq's RedisSettings.

    Mirrors :func:`sbs_api.dependencies.hmac_verify.get_redis_client` so
    the worker and the API talk to the same Redis (different DBs
    optional in production, same DB in the sandbox).
    """

    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    db = int((parsed.path or "/0").lstrip("/") or "0")
    return RedisSettings(host=host, port=port, database=db)


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(
            _redis_settings_from_url(settings.redis_url)
        )
    return _pool


async def enqueue_job(function_name: str, *args: Any, **kwargs: Any) -> Any:
    """Enqueue a job onto the arq queue.

    Returns the arq :class:`Job` handle (or ``None`` if the job was
    deduplicated by arq's optional dedup key — not in use here).
    """

    pool = await get_arq_pool()
    return await pool.enqueue_job(function_name, *args, **kwargs)


def override_arq_pool_for_test(pool: ArqRedis | None) -> None:
    """Inject a fake / fakeredis-backed pool for tests."""

    global _pool
    _pool = pool


async def reset_arq_pool_for_test() -> None:
    """Drop the cached pool so the next get_arq_pool() rebuilds."""

    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = None
