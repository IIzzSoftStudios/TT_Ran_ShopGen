"""Tests for GM market overview aggregation and payload building."""

from __future__ import annotations

import pytest
from flask import Flask

from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    Campaign,
    CampaignWorldConfig,
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
)


@pytest.fixture()
def market_app():
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


def _seed_campaign_with_items():
    user = User(username="gm-mkt", password="x", role="GM")
    db.session.add(user)
    db.session.flush()
    gm = GMProfile(user_id=user.id)
    db.session.add(gm)
    db.session.flush()
    campaign = Campaign(
        gm_profile_id=gm.id,
        name="Market Camp",
        system_type="generic",
        current_game_day=5,
    )
    db.session.add(campaign)
    db.session.flush()

    item_a = Item(
        campaign_id=campaign.id,
        name="Iron Sword",
        type="Weapon",
        rarity="common",
        base_price=100,
    )
    item_b = Item(
        campaign_id=campaign.id,
        name="Healing Herb",
        type="Consumable",
        rarity="common",
        base_price=10,
    )
    db.session.add_all([item_a, item_b])
    db.session.flush()

    shop = Shop(campaign_id=campaign.id, name="General Store", type="General")
    db.session.add(shop)
    db.session.flush()

    db.session.add_all(
        [
            ShopInventory(
                campaign_id=campaign.id,
                shop_id=shop.shop_id,
                item_id=item_a.item_id,
                stock=8,
                dynamic_price=110.0,
            ),
            ShopInventory(
                campaign_id=campaign.id,
                shop_id=shop.shop_id,
                item_id=item_b.item_id,
                stock=4,
                dynamic_price=9.0,
            ),
        ]
    )
    db.session.add_all(
        [
            GlobalMarket(
                campaign_id=campaign.id,
                item_id=item_a.item_id,
                average_price=100.0,
                baseline_avg_stock=6.0,
            ),
            GlobalMarket(
                campaign_id=campaign.id,
                item_id=item_b.item_id,
                average_price=10.0,
                baseline_avg_stock=5.0,
            ),
        ]
    )
    sim = SimulationState(campaign_id=campaign.id, current_tick=0, speed="pause")
    sim.last_market_run = {
        "period": "day",
        "game_day_start": 4,
        "game_day_end": 5,
        "completed_at": "2026-05-19T12:00:00Z",
        "items": {
            str(item_a.item_id): {
                "avg_price_start": 100.0,
                "avg_price_end": 110.0,
                "avg_stock_start": 10.0,
                "avg_stock_end": 8.0,
            },
        },
    }
    db.session.add(sim)
    db.session.commit()
    return campaign.id, item_a.item_id, item_b.item_id


def test_aggregate_in_stock_only_excludes_zero_stock_rows(market_app):
    with market_app.app_context():
        campaign_id, item_a_id, _item_b_id = _seed_campaign_with_items()
        ghost = Item(
            campaign_id=campaign_id,
            name="Ghost SKU",
            type="General",
            rarity="common",
            base_price=1,
        )
        db.session.add(ghost)
        db.session.flush()
        shop = Shop.query.filter_by(campaign_id=campaign_id).first()
        db.session.add(
            ShopInventory(
                campaign_id=campaign_id,
                shop_id=shop.shop_id,
                item_id=ghost.item_id,
                stock=0,
                dynamic_price=1.0,
            )
        )
        db.session.commit()

        all_metrics = aggregate_item_metrics(campaign_id, in_stock_only=False)
        in_stock = aggregate_item_metrics(campaign_id, in_stock_only=True)
        assert ghost.item_id in all_metrics
        assert ghost.item_id not in in_stock
        assert item_a_id in in_stock
        assert in_stock[item_a_id]["avg_price"] == pytest.approx(110.0)
        assert in_stock[item_a_id]["avg_stock"] == pytest.approx(8.0)


def test_build_market_overview_payload_shape_and_deltas(market_app):
    with market_app.app_context():
        campaign_id, item_a_id, item_b_id = _seed_campaign_with_items()
        payload = build_market_overview_payload(campaign_id)

        assert "items" in payload
        assert payload["market_volatility"] == 5
        assert payload["stocked_item_count"] == 2
        assert payload["last_run"] is not None
        assert payload["last_run"]["period"] == "day"

        by_id = {row["item_id"]: row for row in payload["items"]}
        assert len(by_id) == 2

        sword = by_id[item_a_id]
        assert sword["price_vs_base"] == "higher"
        assert sword["last_run_price_delta"] == pytest.approx(10.0)
        assert sword["last_run_stock_delta"] == pytest.approx(-2.0)

        herb = by_id[item_b_id]
        assert herb["stock_vs_base"] == "lower"
        assert herb["last_run_price_delta"] is None


def test_market_overview_payload_includes_configured_volatility(market_app):
    with market_app.app_context():
        campaign_id, _item_a_id, _item_b_id = _seed_campaign_with_items()
        db.session.add(
            CampaignWorldConfig(
                campaign_id=campaign_id,
                settings_json={
                    "schema_version": 2,
                    "inventory_mode": "axis",
                    "supply_demand_enabled": True,
                    "market_volatility": 9,
                    "ranges": {},
                },
                schema_version=2,
            )
        )
        db.session.commit()

        payload = build_market_overview_payload(campaign_id)
        assert payload["market_volatility"] == 9


def test_precomputed_price_delta_in_snapshot(market_app):
    with market_app.app_context():
        from sqlalchemy.orm.attributes import flag_modified

        campaign_id, item_a_id, _ = _seed_campaign_with_items()
        sim = SimulationState.query.filter_by(campaign_id=campaign_id).first()
        entry = dict(sim.last_market_run["items"][str(item_a_id)])
        entry["price_delta"] = 99.0
        entry.pop("avg_price_start", None)
        entry.pop("avg_price_end", None)
        sim.last_market_run["items"][str(item_a_id)] = entry
        flag_modified(sim, "last_market_run")
        db.session.commit()
        row = next(
            r for r in build_market_overview_payload(campaign_id)["items"]
            if r["item_id"] == item_a_id
        )
        assert row["last_run_price_delta"] == pytest.approx(99.0)
