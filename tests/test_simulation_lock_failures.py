"""Simulation batch lock failure paths for run_period_task."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, GMProfile, SimulationState, User
from app.tasks.simulation_tasks import SimJobStatus, run_period_task


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _seed_campaign():
    user = User(username="gm-lock-fail", password="x", role="GM")
    db.session.add(user)
    db.session.flush()
    gm = GMProfile(user_id=user.id)
    db.session.add(gm)
    db.session.flush()
    campaign = Campaign(
        gm_profile_id=gm.id,
        name="Lock Fail Camp",
        system_type="generic",
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.flush()
    db.session.add(
        SimulationState(campaign_id=campaign.id, current_tick=0, speed="pause")
    )
    db.session.commit()
    return campaign.id


def _mock_redis_client():
    redis = MagicMock()
    redis.hset.return_value = True
    redis.expire.return_value = True
    redis.hget.return_value = None
    redis.delete.return_value = True
    return redis


@patch("app.tasks.simulation_tasks.record_job_rejected")
@patch("app.tasks.simulation_tasks.record_job_started")
@patch("app.tasks.simulation_tasks.get_redis_client")
@patch("app.tasks.simulation_tasks.acquire_simulation_lock")
def test_simulation_job_lock_not_acquired(
    mock_acquire, mock_redis, mock_started, mock_rejected
):
    mock_acquire.return_value = None
    mock_redis.return_value = _mock_redis_client()

    result = run_period_task.run(42, "day")

    assert result["status"] == SimJobStatus.BUSY
    assert result["error"] == "Simulation already running"
    mock_rejected.assert_called_once_with("day", SimJobStatus.BUSY)
    mock_started.assert_not_called()

    hset_calls = [
        c[1].get("mapping", c[0])
        for c in mock_redis.return_value.hset.call_args_list
    ]
    busy_writes = [
        m for m in hset_calls if isinstance(m, dict) and m.get("status") == SimJobStatus.BUSY
    ]
    assert busy_writes


@patch("app.tasks.simulation_tasks.get_redis_client")
@patch("app.tasks.simulation_tasks.acquire_simulation_lock")
def test_simulation_job_redis_down_on_acquire(mock_acquire, mock_redis):
    mock_acquire.side_effect = RedisConnectionError("Connection lost")
    mock_redis.return_value = _mock_redis_client()

    result = run_period_task.run(42, "day")

    assert result["status"] == SimJobStatus.ERROR
    assert "Redis unavailable while acquiring simulation lock" in result["error"]

    hset_calls = [
        c[1].get("mapping", c[0])
        for c in mock_redis.return_value.hset.call_args_list
    ]
    error_writes = [
        m for m in hset_calls if isinstance(m, dict) and m.get("status") == SimJobStatus.ERROR
    ]
    assert error_writes
    assert any("Redis unavailable while acquiring simulation lock" in (m.get("error") or "") for m in error_writes)


@patch("app.tasks.simulation_tasks.record_job_finished")
@patch("app.tasks.simulation_tasks.record_job_started")
@patch("app.tasks.simulation_tasks.get_redis_client")
@patch("app.tasks.simulation_tasks.acquire_simulation_lock")
def test_simulation_job_lock_stolen_mid_batch(
    mock_acquire, mock_redis, mock_started, mock_finished, monkeypatch
):
    monkeypatch.setenv("SIMULATION_LOCK_REFRESH_SECONDS", "0")

    mock_lock = MagicMock()
    mock_lock.refresh.return_value = False
    mock_acquire.return_value = mock_lock
    mock_redis.return_value = _mock_redis_client()
    mock_started.return_value = 0.0

    with flask_app.app_context():
        campaign_id = _seed_campaign()
        result = run_period_task.run(campaign_id, "day")

    assert result["status"] == SimJobStatus.LOCK_LOST
    assert "error" in result

    hset_calls = [
        c[1].get("mapping", c[0])
        for c in mock_redis.return_value.hset.call_args_list
    ]
    assert any(
        isinstance(m, dict) and m.get("status") == SimJobStatus.LOCK_LOST for m in hset_calls
    )
    assert not any(
        isinstance(m, dict) and m.get("status") == SimJobStatus.SUCCESS for m in hset_calls
    )
