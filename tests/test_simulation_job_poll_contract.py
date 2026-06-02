"""Regression: job status contract for GM simulation polling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    Campaign,
    CampaignWorldConfig,
    City,
    GlobalMarket,
    GMProfile,
    Item,
    Shop,
    ShopInventory,
    SimulationState,
    User,
)
from app.routes.handlers import gm_simulation_handler
from app.services.economy.supply_demand import seed_next_restock_day
from app.services.market_overview import build_market_overview_payload
from app.tasks.simulation_tasks import SimJobStatus, run_period_task
import random


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def test_running_with_all_ticks_done_is_not_terminal_success():
    """UI must wait for status=success, not ticks_done >= ticks_total while running."""
    with flask_app.test_request_context():
        with patch.object(
            gm_simulation_handler,
            "get_redis_client",
            return_value=MagicMock(
                hgetall=MagicMock(
                    return_value={
                        "status": SimJobStatus.RUNNING,
                        "ticks_done": "30",
                        "ticks_total": "30",
                        "current_game_day": "40",
                    }
                )
            ),
        ):
            with patch.object(gm_simulation_handler, "handle_redis_outage", lambda f: f):
                resp = gm_simulation_handler.simulation_job_status("job-running")
                payload = resp.get_json()
                assert payload["status"] == SimJobStatus.RUNNING
                assert payload["ticks_done"] == 30
                assert payload["ticks_total"] == 30
                assert payload["terminal"] is False
                assert payload["world_changed"] is False


def test_success_job_status_includes_supply_totals():
    with flask_app.test_request_context():
        with patch.object(
            gm_simulation_handler,
            "get_redis_client",
            return_value=MagicMock(
                hgetall=MagicMock(
                    return_value={
                        "status": SimJobStatus.SUCCESS,
                        "ticks_done": "7",
                        "ticks_total": "7",
                        "units_sold_total": "42",
                        "shops_restocked_total": "3",
                    }
                )
            ),
        ):
            with patch.object(gm_simulation_handler, "handle_redis_outage", lambda f: f):
                resp = gm_simulation_handler.simulation_job_status("job-ok")
                payload = resp.get_json()
                assert payload["status"] == SimJobStatus.SUCCESS
                assert payload["units_sold_total"] == 42
                assert payload["shops_restocked_total"] == 3
                assert payload["world_changed"] is True
                assert payload["terminal"] is True


def test_paused_job_status_is_terminal_and_world_changed_flag_drives_payload():
    with flask_app.test_request_context():
        with patch.object(
            gm_simulation_handler,
            "get_redis_client",
            return_value=MagicMock(
                hgetall=MagicMock(
                    return_value={
                        "status": SimJobStatus.PAUSED,
                        "ticks_done": "3",
                        "ticks_total": "7",
                        "world_changed": "true",
                    }
                )
            ),
        ):
            with patch.object(gm_simulation_handler, "handle_redis_outage", lambda f: f):
                resp = gm_simulation_handler.simulation_job_status("job-paused")
                payload = resp.get_json()
                assert payload["status"] == SimJobStatus.PAUSED
                assert payload["ticks_done"] == 3
                assert payload["ticks_total"] == 7
                assert payload["world_changed"] is True
                assert payload["terminal"] is True


def _seed_supply_campaign():
    user = User(username="gm-period", password="x", role="GM")
    db.session.add(user)
    db.session.flush()
    gm = GMProfile(user_id=user.id)
    db.session.add(gm)
    db.session.flush()
    campaign = Campaign(
        gm_profile_id=gm.id,
        name="Supply Camp",
        system_type="generic",
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.flush()
    db.session.add(
        CampaignWorldConfig(
            campaign_id=campaign.id,
            settings_json={"supply_demand_enabled": True, "schema_version": 1},
        )
    )
    city = City(
        name="Town",
        size="Medium City",
        population=100_000,
        campaign_id=campaign.id,
    )
    shop = Shop(name="General", type="General Store", campaign_id=campaign.id)
    db.session.add_all([city, shop])
    db.session.flush()
    shop.cities.append(city)
    item = Item(
        name="Goods",
        type="General",
        rarity="Common",
        base_price=100,
        campaign_id=campaign.id,
    )
    db.session.add(item)
    db.session.flush()
    inv = ShopInventory(
        shop_id=shop.shop_id,
        item_id=item.item_id,
        campaign_id=campaign.id,
        stock=20,
        dynamic_price=80,
    )
    seed_next_restock_day(shop, 1, random.Random(1))
    db.session.add(inv)
    db.session.add(
        GlobalMarket(
            campaign_id=campaign.id,
            item_id=item.item_id,
            average_price=100.0,
            baseline_avg_stock=20.0,
        )
    )
    db.session.add(
        SimulationState(campaign_id=campaign.id, current_tick=0, speed="pause")
    )
    db.session.commit()
    return campaign.id, item.item_id, inv.inventory_id


@patch("app.tasks.simulation_tasks.record_job_finished")
@patch("app.tasks.simulation_tasks.record_job_started")
@patch("app.tasks.simulation_tasks.get_redis_client")
@patch("app.tasks.simulation_tasks.acquire_simulation_lock")
def test_run_period_with_supply_updates_stock_and_market_snapshot(
    mock_lock, mock_redis, mock_started, mock_finished
):
    mock_lock.return_value = MagicMock(refresh=MagicMock(return_value=True))
    redis = MagicMock()
    redis.hset.return_value = True
    redis.expire.return_value = True
    redis.hget.return_value = None
    mock_redis.return_value = redis

    with flask_app.app_context():
        campaign_id, item_id, inv_id = _seed_supply_campaign()
        inv_before = ShopInventory.query.get(inv_id)
        stock_before = inv_before.stock

        result = run_period_task.run(campaign_id, "day")

        assert result["status"] == SimJobStatus.SUCCESS
        assert result.get("units_sold_total", 0) > 0

        db.session.expire_all()
        inv_after = ShopInventory.query.get(inv_id)
        assert inv_after.stock != stock_before

        state = SimulationState.query.filter_by(campaign_id=campaign_id).first()
        assert state.last_market_run is not None
        assert state.last_market_run.get("period") == "day"
        snap_items = state.last_market_run.get("items") or {}
        assert str(item_id) in snap_items or item_id in snap_items

        payload = build_market_overview_payload(campaign_id)
        row = next(r for r in payload["items"] if r["item_id"] == item_id)
        assert row["last_run_stock_delta"] is not None
        assert row["last_run_price_delta"] is not None

        success_writes = [
            c[1].get("mapping", c[0])
            for c in redis.hset.call_args_list
            if isinstance(c[1].get("mapping", c[0]), dict)
            and c[1].get("mapping", c[0]).get("status") == SimJobStatus.SUCCESS
        ]
        assert success_writes
        assert success_writes[-1].get("units_sold_total", 0) > 0


@patch("app.tasks.simulation_tasks.record_job_finished")
@patch("app.tasks.simulation_tasks.record_job_started")
@patch("app.tasks.simulation_tasks.get_redis_client")
@patch("app.tasks.simulation_tasks.acquire_simulation_lock")
def test_run_period_pauses_between_ticks(
    mock_lock, mock_redis, mock_started, mock_finished
):
    mock_lock.return_value = MagicMock(refresh=MagicMock(return_value=True))
    redis = MagicMock()
    redis.hset.return_value = True
    redis.expire.return_value = True
    redis.hget.return_value = None
    redis.get.side_effect = [None, "1"]
    mock_redis.return_value = redis

    def fake_tick(campaign_id, flush_only=False, commit=True):
        camp = Campaign.query.get(campaign_id)
        camp.current_game_day = (camp.current_game_day or 0) + 1
        return {"current_game_day": camp.current_game_day}

    with flask_app.app_context():
        campaign_id, _item_id, _inv_id = _seed_supply_campaign()
        with patch("app.tasks.simulation_tasks.SimulationEngine") as mock_engine_cls:
            mock_engine_cls.return_value.run_tick.side_effect = fake_tick
            result = run_period_task.run(campaign_id, "week")

        assert result["status"] == SimJobStatus.PAUSED
        assert result["ticks_done"] == 1
        assert result["ticks_total"] == 7
        assert mock_engine_cls.return_value.run_tick.call_count == 1
        assert Campaign.query.get(campaign_id).current_game_day == 2

        hset_calls = [c[1].get("mapping", c[0]) for c in redis.hset.call_args_list]
        paused_writes = [
            m for m in hset_calls if isinstance(m, dict) and m.get("status") == SimJobStatus.PAUSED
        ]
        assert paused_writes
        assert paused_writes[-1]["ticks_done"] == 1
