"""Regression: snapshot persistence failure must not report SUCCESS."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    Campaign,
    GlobalMarket,
    GMProfile,
    Item,
    Shop,
    ShopInventory,
    SimulationState,
    User,
)
from app.routes.handlers import gm_simulation_handler
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


def _seed():
    user = User(username="gm-snap-err", password="x", role="GM")
    db.session.add(user)
    db.session.flush()
    gm = GMProfile(user_id=user.id)
    db.session.add(gm)
    db.session.flush()
    campaign = Campaign(
        gm_profile_id=gm.id,
        name="Snap Err Camp",
        system_type="generic",
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.flush()
    item = Item(
        campaign_id=campaign.id,
        name="Ore",
        type="Mineral",
        rarity="common",
        base_price=5,
    )
    db.session.add(item)
    db.session.flush()
    shop = Shop(campaign_id=campaign.id, name="Mine", type="General")
    db.session.add(shop)
    db.session.flush()
    db.session.add(
        ShopInventory(
            campaign_id=campaign.id,
            shop_id=shop.shop_id,
            item_id=item.item_id,
            stock=5,
            dynamic_price=5.0,
        )
    )
    db.session.add(
        GlobalMarket(
            campaign_id=campaign.id,
            item_id=item.item_id,
            average_price=5.0,
            baseline_avg_stock=5.0,
        )
    )
    db.session.add(
        SimulationState(campaign_id=campaign.id, current_tick=0, speed="pause")
    )
    db.session.commit()
    return campaign.id


@patch("app.tasks.simulation_tasks.record_job_finished")
@patch("app.tasks.simulation_tasks.record_job_started")
@patch("app.tasks.simulation_tasks.get_redis_client")
@patch("app.tasks.simulation_tasks.acquire_simulation_lock")
@patch("app.tasks.simulation_tasks.persist_last_market_run_snapshot")
def test_snapshot_failure_returns_error_not_success(
    mock_persist, mock_lock, mock_redis, mock_started, mock_finished
):
    mock_persist.side_effect = RuntimeError("db write failed")
    mock_lock.return_value = MagicMock(refresh=MagicMock(return_value=True))
    redis = MagicMock()
    redis.hset.return_value = True
    redis.expire.return_value = True
    mock_redis.return_value = redis

    def fake_tick(campaign_id, flush_only=False, commit=True):
        camp = Campaign.query.get(campaign_id)
        camp.current_game_day = (camp.current_game_day or 0) + 1
        return {"current_game_day": camp.current_game_day}

    with flask_app.app_context():
        campaign_id = _seed()
        with patch("app.tasks.simulation_tasks.SimulationEngine") as mock_engine_cls:
            mock_engine_cls.return_value.run_tick.side_effect = fake_tick
            result = run_period_task.run(campaign_id, "day")

        assert result["status"] == SimJobStatus.ERROR
        assert "error" in result
        assert Campaign.query.get(campaign_id).current_game_day == 2

        hset_calls = [c[1].get("mapping", c[0]) for c in redis.hset.call_args_list]
        terminal_writes = [
            m for m in hset_calls if isinstance(m, dict) and m.get("status") == SimJobStatus.ERROR
        ]
        assert terminal_writes, "Redis job hash should record ERROR terminal status"
        assert terminal_writes[-1].get("world_changed") == "true"


def test_job_status_honors_world_changed_flag():
    with flask_app.test_request_context():
        with patch.object(
            gm_simulation_handler,
            "get_redis_client",
            return_value=MagicMock(
                hgetall=MagicMock(
                    return_value={
                        "status": SimJobStatus.ERROR,
                        "error": "snapshot failed",
                        "world_changed": "true",
                        "ticks_done": "1",
                        "ticks_total": "1",
                    }
                )
            ),
        ):
            with patch.object(gm_simulation_handler, "handle_redis_outage", lambda f: f):
                resp = gm_simulation_handler.simulation_job_status("job-1")
                payload = resp.get_json()
                assert payload["status"] == SimJobStatus.ERROR
                assert payload["world_changed"] is True
