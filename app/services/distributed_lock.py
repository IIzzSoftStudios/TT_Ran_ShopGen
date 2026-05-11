"""Per-campaign distributed lock backed by Redis SET NX EX.

A single shared lazy client is reused across requests/tasks. Cloud Run
aggressively reaps idle TCP connections, so `health_check_interval=30` plus
`socket_keepalive=True` keep pooled sockets fresh and surface dead peers
before the next command crashes with `ConnectionError: Broken pipe`.

Lock holders that run longer than the initial TTL (e.g. a 365-tick Year
batch) MUST call ``lock.refresh()`` periodically to extend the TTL while
they still own the token. Without refresh, the key can expire mid-batch
and a second worker will acquire the lock for the same campaign — the
exact split-brain the lock is meant to prevent.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

import redis

logger = logging.getLogger(__name__)

RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Compare-and-extend: only re-arm the TTL when we still own the lock token.
# Returns 1 on success, 0 if another worker has stolen the key.
REFRESH_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""

_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Create (once) a Redis client from `REDIS_URL`."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _redis_client = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        socket_keepalive=True,
        health_check_interval=30,
    )
    return _redis_client


class LockLost(RuntimeError):
    """Raised when a refresh discovers the lock token has been overwritten."""


class _RedisSimLock:
    def __init__(self, lock_key: str, token: str, ttl_seconds: int):
        self.lock_key = lock_key
        self.token = token
        self.ttl_seconds = int(ttl_seconds)

    def refresh(self, ttl_seconds: Optional[int] = None) -> bool:
        """Extend the TTL only if we still own the lock.

        Returns True on success. Returns False if another worker has stolen
        the key (caller should treat the batch as failed and abort).
        """
        client = get_redis_client()
        ttl = int(ttl_seconds if ttl_seconds is not None else self.ttl_seconds)
        ok = int(client.eval(REFRESH_LUA, 1, self.lock_key, self.token, ttl))
        if not ok:
            logger.warning(
                "Lock %s refresh failed: token mismatch (lock stolen or expired)",
                self.lock_key,
            )
        return bool(ok)

    def release(self) -> int:
        """Token-checked release; another worker cannot delete our lock."""
        client = get_redis_client()
        return int(client.eval(RELEASE_LUA, 1, self.lock_key, self.token))


def acquire_simulation_lock(
    campaign_id: int,
    *,
    ttl_seconds: int,
    blocking: bool = False,
) -> Optional[_RedisSimLock]:
    """Acquire the per-campaign simulation lock.

    Returns the lock handle on success, `None` if not acquired and
    `blocking=False`. Callers should wrap critical sections in try/finally
    and call `release()` to surrender the lock early.
    """
    client = get_redis_client()
    lock_key = f"lock:sim:{int(campaign_id)}"
    token = str(uuid.uuid4())

    acquired = bool(client.set(lock_key, token, nx=True, ex=int(ttl_seconds)))
    if acquired:
        return _RedisSimLock(lock_key=lock_key, token=token, ttl_seconds=int(ttl_seconds))

    if blocking:
        raise TimeoutError(
            f"Could not acquire simulation lock for campaign_id={campaign_id}"
        )

    return None
