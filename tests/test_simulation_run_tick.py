"""Regression tests for ``SimulationEngine.run_tick`` (canonical tick path).

Scheduling uses Celery + per-campaign Redis locks; there is no in-process
auto-tick loop. These tests assert engine behavior on a minimal in-memory
schema.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    Campaign,
    GMProfile,
    GMWorldState,
    PriceHistory,
    ShopInventory,
    SimulationState,
    User,
)
from app.services.economy import calculate_dynamic_price
from app.services.simulation import SimulationEngine
from app.services.world_generator.defaults import RANGE_SETTINGS
from app.services.world_generator import validator as wg_validator


@pytest.fixture()
def sim_app():
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


def _make_gm(username: str) -> GMProfile:
    user = User(username=username, password="x", role="GM")
    db.session.add(user)
    db.session.flush()
    gm = GMProfile(user_id=user.id)
    db.session.add(gm)
    db.session.commit()
    return gm


def _make_campaign(gm: GMProfile, name: str = "Test Campaign") -> Campaign:
    campaign = Campaign(
        gm_profile_id=gm.id,
        name=name,
        system_type="generic",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def _minimal_world_gen_form(**extra):
    form = {
        "campaign_name": "Tick Camp",
        "system_type": "generic",
        "inventory_mode": "axis",
    }
    for key, (floor, ceiling, d_min, d_max) in RANGE_SETTINGS.items():
        form[f"{key}_min"] = str(d_min)
        form[f"{key}_max"] = str(d_max)
    form.update(extra)
    return form


def _seed_tick_world(sim_app, *, current_game_day=3, extra_cities=1):
    """Minimal shop + inventory for rollback and reconciliation tests."""
    with sim_app.app_context():
        gm = _make_gm("gm-tick-world")
        campaign = Campaign(
            gm_profile_id=gm.id,
            name="Tick World",
            system_type="generic",
            current_game_day=current_game_day,
        )
        db.session.add(campaign)
        db.session.flush()
        from app.models import CampaignWorldConfig, City, Item, Shop

        settings = wg_validator.validate(_minimal_world_gen_form())
        db.session.add(
            CampaignWorldConfig(
                campaign_id=campaign.id,
                settings_json=settings,
                schema_version=2,
            )
        )
        city = City(name="Rollback City", campaign_id=campaign.id)
        shop = Shop(name="Rollback Shop", type="General Store", campaign_id=campaign.id)
        db.session.add_all([city, shop])
        db.session.flush()
        shop.cities.append(city)
        for i in range(extra_cities):
            extra = City(name=f"Extra-{i}", campaign_id=campaign.id)
            db.session.add(extra)
            db.session.flush()
            shop.cities.append(extra)
        item = Item(
            name="Rollback Item",
            type="General",
            rarity="Common",
            base_price=40,
            campaign_id=campaign.id,
        )
        db.session.add(item)
        db.session.flush()
        inv = ShopInventory(
            shop_id=shop.shop_id,
            item_id=item.item_id,
            campaign_id=campaign.id,
            stock=20,
            dynamic_price=40.0,
        )
        db.session.add(inv)
        db.session.flush()
        db.session.add(
            GMWorldState(
                campaign_id=campaign.id,
                state_json={
                    str(inv.inventory_id): {"dynamic_price": 40.0, "stock": 20}
                },
                tick_seq=current_game_day,
            )
        )
        db.session.add(
            SimulationState(
                campaign_id=campaign.id,
                current_tick=current_game_day,
                speed="pause",
            )
        )
        db.session.commit()
        return {
            "campaign_id": campaign.id,
            "inventory_id": inv.inventory_id,
        }


def test_run_tick_unknown_campaign_raises(sim_app):
    with sim_app.app_context():
        engine = SimulationEngine()
        with pytest.raises(ValueError, match="No Campaign"):
            engine.run_tick(999, commit=True)


def test_run_tick_advances_calendar_and_sim_state(sim_app):
    with sim_app.app_context():
        gm = _make_gm("gm-one")
        campaign = _make_campaign(gm)
        engine = SimulationEngine()
        stats = engine.run_tick(campaign.id, commit=True)

        db.session.refresh(campaign)
        assert campaign.current_game_day == 2
        assert stats.get("current_game_day") == 2

        state = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign.id)
            .first()
        )
        assert state is not None
        assert state.current_tick == 2


def test_run_tick_isolates_campaigns_under_same_gm(sim_app):
    """Ticking one campaign must not advance another campaign owned by the same GM."""
    with sim_app.app_context():
        gm = _make_gm("gm-multi")
        campaign_a = _make_campaign(gm, name="Camp A")
        campaign_b = _make_campaign(gm, name="Camp B")

        engine = SimulationEngine()
        engine.run_tick(campaign_a.id, commit=True)

        db.session.refresh(campaign_a)
        db.session.refresh(campaign_b)
        assert campaign_a.current_game_day == 2
        assert campaign_b.current_game_day == 1

        state_a = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign_a.id)
            .first()
        )
        state_b = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign_b.id)
            .first()
        )
        assert state_a is not None and state_a.current_tick == 2
        assert state_b is None or state_b.current_tick == 0


def test_run_tick_mid_failure_rolls_back_all_mutations(sim_app, monkeypatch):
    """Forced exception after dirty rows must restore pre-tick authority tables."""
    monkeypatch.setenv("WORLD_STATE_ENABLED", "true")
    seeded = _seed_tick_world(sim_app)
    campaign_id = seeded["campaign_id"]
    inventory_id = seeded["inventory_id"]

    with sim_app.app_context():
        campaign = db.session.get(Campaign, campaign_id)
        sim_state = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign_id)
            .first()
        )
        inv = db.session.get(ShopInventory, inventory_id)
        gws = db.session.query(GMWorldState).filter_by(campaign_id=campaign_id).first()
        pre_day = campaign.current_game_day
        pre_tick = sim_state.current_tick
        pre_price = inv.dynamic_price
        pre_stock = inv.stock
        pre_history = PriceHistory.query.filter_by(campaign_id=campaign_id).count()
        pre_blob = dict(gws.state_json or {})
        pre_gws_tick = gws.tick_seq

        original = calculate_dynamic_price
        calls = {"n": 0}

        def boom(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("forced mid-tick failure")
            return original(*args, **kwargs)

        with patch(
            "app.services.simulation.calculate_dynamic_price",
            side_effect=boom,
        ):
            with pytest.raises(RuntimeError, match="forced mid-tick"):
                SimulationEngine().run_tick(campaign_id, commit=True)

        db.session.expire_all()
        campaign = db.session.get(Campaign, campaign_id)
        sim_state = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign_id)
            .first()
        )
        inv = db.session.get(ShopInventory, inventory_id)
        gws = db.session.query(GMWorldState).filter_by(campaign_id=campaign_id).first()

        assert campaign.current_game_day == pre_day
        assert sim_state.current_tick == pre_tick
        assert inv.dynamic_price == pre_price
        assert inv.stock == pre_stock
        assert PriceHistory.query.filter_by(campaign_id=campaign_id).count() == pre_history
        assert gws.state_json == pre_blob
        assert gws.tick_seq == pre_gws_tick


def test_run_tick_world_state_blob_matches_rows_after_commit(sim_app, monkeypatch):
    """Post-tick GMWorldState snapshot must mirror row prices/stock when writes enabled."""
    monkeypatch.setenv("WORLD_STATE_ENABLED", "true")
    seeded = _seed_tick_world(sim_app)
    campaign_id = seeded["campaign_id"]
    inventory_id = seeded["inventory_id"]

    with sim_app.app_context():
        SimulationEngine().run_tick(campaign_id, commit=True)
        db.session.expire_all()

        inv = db.session.get(ShopInventory, inventory_id)
        gws = db.session.query(GMWorldState).filter_by(campaign_id=campaign_id).first()
        assert gws is not None
        entry = (gws.state_json or {}).get(str(inventory_id))
        assert isinstance(entry, dict)
        assert float(entry["dynamic_price"]) == float(inv.dynamic_price)
        assert int(entry["stock"]) == int(inv.stock)
        campaign = db.session.get(Campaign, campaign_id)
        assert gws.tick_seq == campaign.current_game_day

