"""Phase 5: deployment metrics — per-tick Redis telemetry and snapshot resilience."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.services import sim_metrics


class _FakePipeline:
    def __init__(self, client: "_FakeRedis"):
        self._client = client
        self._ops: list[tuple] = []

    def lpush(self, key, value):
        self._ops.append(("lpush", key, value))
        return self

    def ltrim(self, key, start, end):
        self._ops.append(("ltrim", key, start, end))
        return self

    def execute(self):
        for op in self._ops:
            if op[0] == "lpush":
                _, key, value = op
                self._client.lists.setdefault(key, []).insert(0, value)
            elif op[0] == "ltrim":
                _, key, start, end = op
                items = self._client.lists.get(key, [])
                self._client.lists[key] = items[start : end + 1]


class _FakeRedis:
    def __init__(self):
        self.lists: dict[str, list] = {}
        self.strings: dict[str, str | bytes] = {}

    def pipeline(self, transaction=False):
        return _FakePipeline(self)

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        items = self.lists.get(key, [])
        self.lists[key] = items[start : end + 1]

    def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        if end == -1:
            end = len(items) - 1
        return items[start : end + 1]

    def get(self, key):
        return self.strings.get(key)

    def llen(self, key):
        return len(self.lists.get(key, []))

    def incr(self, key):
        val = int(self.strings.get(key, 0) or 0) + 1
        self.strings[key] = str(val)
        return val

    def decr(self, key):
        val = int(self.strings.get(key, 0) or 0) - 1
        self.strings[key] = str(val)
        return val

    def expire(self, key, ttl):
        return True


@pytest.fixture
def fake_redis():
    return _FakeRedis()


def test_record_tick_duration_uses_tick_durations_key(fake_redis):
    with patch.object(sim_metrics, "get_redis_client", return_value=fake_redis):
        sim_metrics.record_tick_duration(0.0123)

    assert "metrics:sim:tick_durations" in fake_redis.lists
    assert fake_redis.lists["metrics:sim:tick_durations"][0] == "0.012300"


def test_record_tick_duration_does_not_touch_db(fake_redis):
    commit = MagicMock()
    flush = MagicMock()
    with patch.object(sim_metrics, "get_redis_client", return_value=fake_redis):
        with patch.object(db.session, "commit", commit):
            with patch.object(db.session, "flush", flush):
                sim_metrics.record_tick_duration(0.05)

    commit.assert_not_called()
    flush.assert_not_called()


def test_snapshot_skips_malformed_tick_samples(fake_redis):
    fake_redis.lists["metrics:sim:tick_durations"] = [
        b"0.010",
        b"not-a-float",
        "0.020",
        b"",
    ]

    with patch.object(sim_metrics, "get_redis_client", return_value=fake_redis):
        payload = sim_metrics.snapshot()

    tick = payload["tick_durations_seconds"]
    assert tick["samples"] == 2
    assert tick["p50"] == pytest.approx(0.010)
    assert tick["p90"] == pytest.approx(0.020)
    assert tick["p99"] == pytest.approx(0.020)


def test_snapshot_empty_tick_durations_returns_none_percentiles(fake_redis):
    with patch.object(sim_metrics, "get_redis_client", return_value=fake_redis):
        payload = sim_metrics.snapshot()

    tick = payload["tick_durations_seconds"]
    assert tick["samples"] == 0
    assert tick["p50"] is None
    assert tick["p90"] is None
    assert tick["p99"] is None


def test_snapshot_tick_percentiles_on_known_list(fake_redis):
    samples = [0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.010]
    fake_redis.lists["metrics:sim:tick_durations"] = [f"{s:.3f}" for s in reversed(samples)]

    with patch.object(sim_metrics, "get_redis_client", return_value=fake_redis):
        payload = sim_metrics.snapshot()

    tick = payload["tick_durations_seconds"]
    assert tick["samples"] == 10
    assert tick["p50"] == pytest.approx(0.005)
    assert tick["p90"] == pytest.approx(0.009)
    assert tick["p99"] == pytest.approx(0.010)


def test_record_tick_duration_noop_when_redis_unavailable():
    with patch.object(sim_metrics, "get_redis_client", return_value=None):
        sim_metrics.record_tick_duration(0.1)
