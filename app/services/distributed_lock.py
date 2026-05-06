"""Per-GM distributed lock backed by Redis SET NX EX.

A single shared lazy client is reused across requests/tasks. Cloud Run
aggressively reaps idle TCP connections, so `health_check_interval=30` plus
`socket_keepalive=True` keep pooled sockets fresh and surface dead peers
before the next command crashes with `ConnectionError: Broken pipe`.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

import redis

RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
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


class _RedisSimLock:
    def __init__(self, lock_key: str, token: str, ttl_seconds: int):
        self.lock_key = lock_key
        self.token = token
        self.ttl_seconds = ttl_seconds

    def release(self) -> int:
        """Token-checked release; another worker cannot delete our lock."""
        client = get_redis_client()
        return int(client.eval(RELEASE_LUA, 1, self.lock_key, self.token))


def acquire_simulation_lock(
    gm_profile_id: int,
    *,
    ttl_seconds: int,
    blocking: bool = False,
) -> Optional[_RedisSimLock]:
    """Acquire the per-GM simulation lock.

    Returns the lock handle on success, `None` if not acquired and
    `blocking=False`. Callers should wrap critical sections in try/finally
    and call `release()` to surrender the lock early.
    """
    client = get_redis_client()
    lock_key = f"lock:sim:{int(gm_profile_id)}"
    token = str(uuid.uuid4())

    acquired = bool(client.set(lock_key, token, nx=True, ex=int(ttl_seconds)))
    if acquired:
        return _RedisSimLock(lock_key=lock_key, token=token, ttl_seconds=int(ttl_seconds))

    if blocking:
        raise TimeoutError(f"Could not acquire simulation lock for gm_profile_id={gm_profile_id}")

    return None
