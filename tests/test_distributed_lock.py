"""Distributed simulation lock acquire, refresh, and release."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import distributed_lock as dl


@pytest.fixture(autouse=True)
def _reset_redis_client():
    dl._redis_client = None
    yield
    dl._redis_client = None


def test_acquire_returns_none_when_not_acquired(monkeypatch):
    client = MagicMock()
    client.set.return_value = False
    monkeypatch.setattr(dl, "get_redis_client", lambda: client)
    handle = dl.acquire_simulation_lock(42, ttl_seconds=30)
    assert handle is None
    client.set.assert_called_once()


def test_acquire_and_release_with_token_check(monkeypatch):
    store = {}

    def _set(key, value, nx=False, ex=None):
        if nx and key in store:
            return False
        store[key] = value
        return True

    def _eval(script, numkeys, key, token, ttl=None):
        if script == dl.RELEASE_LUA:
            if store.get(key) == token:
                del store[key]
                return 1
            return 0
        if script == dl.REFRESH_LUA:
            if store.get(key) == token:
                return 1
            return 0
        return 0

    client = MagicMock()
    client.set.side_effect = _set
    client.eval.side_effect = _eval

    monkeypatch.setattr(dl, "get_redis_client", lambda: client)
    handle = dl.acquire_simulation_lock(99, ttl_seconds=60)
    assert handle is not None
    assert handle.refresh(ttl_seconds=120) is True
    assert handle.release() == 1
    assert "lock:sim:99" not in store


def test_refresh_fails_when_token_stolen(monkeypatch):
    client = MagicMock()
    client.set.return_value = True
    client.eval.return_value = 0

    monkeypatch.setattr(dl, "get_redis_client", lambda: client)
    handle = dl.acquire_simulation_lock(1, ttl_seconds=10)
    assert handle is not None
    assert handle.refresh() is False


def test_release_does_not_delete_when_token_mismatches(monkeypatch):
    store = {}

    def _set(key, value, nx=False, ex=None):
        if nx and key in store:
            return False
        store[key] = value
        return True

    def _eval(script, numkeys, key, token, ttl=None):
        if script == dl.RELEASE_LUA:
            if store.get(key) == token:
                del store[key]
                return 1
            return 0
        return 0

    client = MagicMock()
    client.set.side_effect = _set
    client.eval.side_effect = _eval

    monkeypatch.setattr(dl, "get_redis_client", lambda: client)
    handle = dl.acquire_simulation_lock(7, ttl_seconds=30)
    assert handle is not None
    store["lock:sim:7"] = "stolen-token"
    assert handle.release() == 0
    assert "lock:sim:7" in store


def test_second_acquire_returns_none_while_held(monkeypatch):
    store = {}

    def _set(key, value, nx=False, ex=None):
        if nx and key in store:
            return False
        store[key] = value
        return True

    client = MagicMock()
    client.set.side_effect = _set
    monkeypatch.setattr(dl, "get_redis_client", lambda: client)

    first = dl.acquire_simulation_lock(55, ttl_seconds=30)
    second = dl.acquire_simulation_lock(55, ttl_seconds=30)
    assert first is not None
    assert second is None


def test_acquire_blocking_raises_timeout(monkeypatch):
    client = MagicMock()
    client.set.return_value = False
    monkeypatch.setattr(dl, "get_redis_client", lambda: client)

    with pytest.raises(TimeoutError, match="campaign_id=999"):
        dl.acquire_simulation_lock(999, ttl_seconds=10, blocking=True)
