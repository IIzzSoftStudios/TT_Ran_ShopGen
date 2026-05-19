"""Tests for last_market_run snapshot persistence."""

from __future__ import annotations

import pytest
from flask import Flask

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
from app.services.market_overview import (
    aggregate_item_metrics,
    build_market_overview_payload,
    persist_last_market_run_snapshot,
)


@pytest.fixture()
def snap_app():
    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SECRET_KEY"] = "test"
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


def _seed():
    user = User(username="gm-snap", password="x", role="GM")
    db.session.add(user)
    db.session.flush()
    gm = GMProfile(user_id=user.id)
    db.session.add(gm)
    db.session.flush()
    campaign = Campaign(
        gm_profile_id=gm.id,
        name="Snap Camp",
        system_type="generic",
        current_game_day=10,
    )
    db.session.add(campaign)
    db.session.flush()
    item = Item(
        campaign_id=campaign.id,
        name="Grain",
        type="Agricultural",
        rarity="common",
        base_price=2,
    )
    db.session.add(item)
    db.session.flush()
    shop = Shop(campaign_id=campaign.id, name="Farm", type="General")
    db.session.add(shop)
    db.session.flush()
    db.session.add(
        ShopInventory(
            campaign_id=campaign.id,
            shop_id=shop.shop_id,
            item_id=item.item_id,
            stock=10,
            dynamic_price=2.5,
        )
    )
    db.session.add(
        GlobalMarket(
            campaign_id=campaign.id,
            item_id=item.item_id,
            average_price=2.0,
            baseline_avg_stock=10.0,
        )
    )
    db.session.add(
        SimulationState(
            campaign_id=campaign.id,
            current_tick=0,
            speed="pause",
            last_market_run={
                "period": "week",
                "game_day_start": 1,
                "game_day_end": 7,
                "completed_at": "2020-01-01T00:00:00Z",
                "items": {},
            },
        )
    )
    db.session.commit()
    return campaign.id, item.item_id


def test_persist_last_market_run_snapshot_updates_state(snap_app):
    with snap_app.app_context():
        campaign_id, item_id = _seed()
        start = {item_id: {"avg_price": 2.5, "avg_stock": 10.0}}
        end = {item_id: {"avg_price": 3.0, "avg_stock": 8.0}}

        persist_last_market_run_snapshot(
            campaign_id, "day", 10, 11, start, end
        )

        state = SimulationState.query.filter_by(campaign_id=campaign_id).first()
        assert state.last_market_run["period"] == "day"
        assert state.last_market_run["game_day_start"] == 10
        assert state.last_market_run["game_day_end"] == 11
        assert state.last_market_run["completed_at"] != "2020-01-01T00:00:00Z"
        item_id = Item.query.first().item_id
        snap_item = state.last_market_run["items"][str(item_id)]
        assert "price_delta" in snap_item
        assert "stock_delta" in snap_item

        payload = build_market_overview_payload(campaign_id)
        row = next(r for r in payload["items"] if r["item_id"] == item_id)
        assert row["last_run_price_delta"] == pytest.approx(0.5)
        assert row["last_run_stock_delta"] == pytest.approx(-2.0)


def test_aggregate_metrics_reflect_inventory_changes(snap_app):
    """Simulates pre/post batch metrics without running the Celery task."""
    with snap_app.app_context():
        campaign_id, item_id = _seed()
        start_metrics = aggregate_item_metrics(campaign_id)

        inv = ShopInventory.query.filter_by(item_id=item_id).first()
        inv.dynamic_price = 4.0
        inv.stock = 6
        db.session.commit()

        end_metrics = aggregate_item_metrics(campaign_id)
        assert end_metrics[item_id]["avg_price"] > start_metrics[item_id]["avg_price"]
        assert end_metrics[item_id]["avg_stock"] < start_metrics[item_id]["avg_stock"]
