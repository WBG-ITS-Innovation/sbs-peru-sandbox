"""Redis token-bucket implementation — ADR 0033.

A single Lua script performs the atomic check-and-decrement. The script
is the *only* mutation path for the bucket; without it, two concurrent
requests can both read the same "remaining" value and double-spend the
budget.

Bucket semantics (per the ADR):
- Capacity = ``limit`` (requests per minute).
- Refill = ``limit`` tokens over ``window_ms`` (default 60_000 ms),
  linearly.
- A fully-empty bucket recovers to full in ``window_ms``.

The script stores two fields in a Redis HASH at ``KEYS[1]``:
- ``tokens``: current token count (float, since refill is fractional).
- ``ts``:     last update time (ms since epoch).

Returns a Lua table ``{allowed, remaining, reset_ms, retry_after_s}``:
- ``allowed``       — 1 if the request consumes a token, 0 if denied.
- ``remaining``     — integer floor of tokens after this call.
- ``reset_ms``      — unix ms at which the bucket reaches ``limit``.
- ``retry_after_s`` — seconds the client should wait before retry. 0
  when allowed.
"""

from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as redis_async

TOKEN_BUCKET_SCRIPT = """
-- KEYS[1] = bucket key
-- ARGV[1] = current unix ms
-- ARGV[2] = limit (requests / window)
-- ARGV[3] = window ms
-- Returns { allowed, remaining, reset_ms, retry_after_s }
local key = KEYS[1]
local now = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local refill = limit / window  -- tokens per ms

local data = redis.call("HMGET", key, "tokens", "ts")
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil or ts == nil then
  tokens = limit
  ts = now
end

-- Refill since last update.
local elapsed = math.max(0, now - ts)
tokens = math.min(limit, tokens + elapsed * refill)
ts = now

local allowed = 0
local retry_after_s = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  -- Time until next full token (in ms).
  local needed = 1 - tokens
  retry_after_s = math.ceil(needed / refill / 1000)
  if retry_after_s < 1 then retry_after_s = 1 end
end

-- TTL on the key: enough to cover a full refill plus headroom so the
-- key never lingers indefinitely after an institution goes quiet.
local ttl_s = math.ceil(window / 1000) + 60
redis.call("HMSET", key, "tokens", tokens, "ts", ts)
redis.call("EXPIRE", key, ttl_s)

-- reset_ms: time at which the bucket is full again
local missing = limit - tokens
local reset_ms = now + math.ceil(missing / refill)

return { allowed, math.floor(tokens), reset_ms, retry_after_s }
"""


@dataclass(frozen=True)
class BucketDecision:
    allowed: bool
    remaining: int
    reset_unix_ms: int
    retry_after_seconds: int
    limit: int


async def decrement_bucket(
    redis_client: redis_async.Redis,
    *,
    key: str,
    limit: int,
    window_ms: int = 60_000,
    now_ms: int | None = None,
) -> BucketDecision:
    """Atomically check-and-decrement the bucket at ``key``.

    ``now_ms`` is overridable so tests can drive deterministic clocks.
    """

    import time

    when = now_ms if now_ms is not None else int(time.time() * 1000)
    raw = await redis_client.eval(
        TOKEN_BUCKET_SCRIPT,
        1,
        key,
        when,
        limit,
        window_ms,
    )
    # redis-py returns a list of bytes/ints; decode.
    allowed_i, remaining_i, reset_ms, retry_after_s = (int(x) for x in raw)
    return BucketDecision(
        allowed=allowed_i == 1,
        remaining=remaining_i,
        reset_unix_ms=reset_ms,
        retry_after_seconds=retry_after_s,
        limit=limit,
    )
