"""Demand modifiers load once per simulation tick via DemandContext."""

from __future__ import annotations

import random
from unittest.mock import patch

import pytest
from flask import Flask

from app.constants.simulation_flags import TICK_BUDGET_SECONDS
from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    Campaign,
    City,
    DemandModifier,
    GMProfile,
    Item,
    ModifierTarget,
    Shop,
    ShopInventory,
    User,
)
from app.services.economy import demand as demand_mod
from app.services.economy.demand import DemandContext
from app.services.simulation import SimulationEngine
from app.services.world_generator.defaults import RANGE_SETTINGS
from app.services.world_generator import validator as wg_validator


def _minimal_world_gen_form(**extra):
    form = {
        "campaign_name": "Preload Camp",
        "system_type": "generic",
        "inventory_mode": "axis",
    }
    for key, (floor, ceiling, d_min, d_max) in RANGE_SETTINGS.items():
        form[f"{key}_min"] = str(d_min)
        form[f"{key}_max"] = str(d_max)
    form.update(extra)
    return form


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


def _seed_campaign(sim_app, *, extra_cities=0):
    with sim_app.app_context():
        user = User(username="gm-preload", password="x", role="GM")
        db.session.add(user)
        db.session.flush()
        gm = GMProfile(user_id=user.id)
        db.session.add(gm)
        db.session.flush()
        campaign = Campaign(
            gm_profile_id=gm.id,
            name="Preload",
            system_type="generic",
            current_game_day=5,
        )
        db.session.add(campaign)
        db.session.flush()
        from app.models import CampaignWorldConfig

        settings = wg_validator.validate(_minimal_world_gen_form())
        db.session.add(
            CampaignWorldConfig(
                campaign_id=campaign.id,
                settings_json=settings,
                schema_version=2,
            )
        )
        city = City(name="C1", campaign_id=campaign.id)
        shop = Shop(name="S1", type="General Store", campaign_id=campaign.id)
        db.session.add_all([city, shop])
        db.session.flush()
        shop.cities.append(city)
        extra_city_objs = []
        for i in range(extra_cities):
            c = City(name=f"C-extra-{i}", campaign_id=campaign.id)
            extra_city_objs.append(c)
            shop.cities.append(c)
        db.session.add_all(extra_city_objs)
        item = Item(
            name="Widget",
            type="General",
            rarity="Common",
            base_price=50,
            campaign_id=campaign.id,
        )
        db.session.add(item)
        db.session.flush()
        inv = ShopInventory(
            shop_id=shop.shop_id,
            item_id=item.item_id,
            campaign_id=campaign.id,
            stock=30,
            dynamic_price=50.0,
        )
        db.session.add(inv)
        db.session.commit()
        return campaign.id


def test_load_active_modifiers_called_once_per_tick(sim_app):
    campaign_id = _seed_campaign(sim_app)
    with sim_app.app_context():
        with patch(
            "app.services.simulation.load_active_modifiers_for_campaign",
            wraps=demand_mod.load_active_modifiers_for_campaign,
        ) as loader:
            stats = SimulationEngine().run_tick(campaign_id, commit=True)
        assert loader.call_count == 1
        assert stats.get("tick_duration") is not None
        assert float(stats["tick_duration"]) < 5.0


def test_no_inner_modifier_db_load_during_pricing(sim_app):
    """DemandContext hot path must not re-query modifiers inside pricing loops."""
    campaign_id = _seed_campaign(sim_app, extra_cities=1)
    with sim_app.app_context():
        with patch(
            "app.services.simulation.load_active_modifiers_for_campaign",
            wraps=demand_mod.load_active_modifiers_for_campaign,
        ) as tick_loader:
            with patch(
                "app.services.economy.demand.load_active_modifiers_for_campaign",
                wraps=demand_mod.load_active_modifiers_for_campaign,
            ) as inner_loader:
                SimulationEngine().run_tick(campaign_id, commit=True)
        assert tick_loader.call_count == 1
        assert inner_loader.call_count == 0


def test_demand_context_matches_loose_preloaded_list(sim_app):
    with sim_app.app_context():
        campaign_id = _seed_campaign(sim_app)
        global_mod = DemandModifier(
            campaign_id=campaign_id,
            name="Global boom",
            scope="global",
            effect_value=0.25,
            is_active=True,
        )
        db.session.add(global_mod)
        db.session.flush()
        city = City.query.filter_by(campaign_id=campaign_id).first()
        shop = Shop.query.filter_by(campaign_id=campaign_id).first()
        item = Item.query.filter_by(campaign_id=campaign_id).first()
        db.session.add(
            ModifierTarget(
                modifier_id=global_mod.id,
                campaign_id=campaign_id,
                entity_type="city",
                entity_id=city.city_id,
            )
        )
        db.session.commit()

        modifiers = demand_mod.load_active_modifiers_for_campaign(campaign_id)
        ctx = DemandContext.from_modifiers(campaign_id, modifiers)
        loose = demand_mod._modifier_total_from_list(
            modifiers,
            campaign_id,
            city_id=city.city_id,
            shop_id=shop.shop_id,
            item_id=item.item_id,
        )
        indexed = ctx.modifier_total(
            city_id=city.city_id,
            shop_id=shop.shop_id,
            item_id=item.item_id,
        )
        assert indexed == loose


def test_phase_timing_keys_coherent(sim_app):
    campaign_id = _seed_campaign(sim_app)
    with sim_app.app_context():
        stats = SimulationEngine().run_tick(campaign_id, commit=True)

    for key in ("t_load", "t_compute", "t_flush", "t_persist", "tick_duration"):
        assert key in stats
        assert float(stats[key]) >= 0.0

    tick_duration = float(stats["tick_duration"])
    assert tick_duration >= float(stats["t_compute"])
    assert tick_duration < 5.0
    assert TICK_BUDGET_SECONDS == 0.033


def test_bounded_tick_on_small_fixture(sim_app):
    """P99 33ms is a prod goal; CI uses a loose ceiling on a tiny fixture."""
    campaign_id = _seed_campaign(sim_app)
    with sim_app.app_context():
        stats = SimulationEngine().run_tick(campaign_id, commit=True)
    duration = float(stats.get("tick_duration") or 0)
    assert duration < 2.0
