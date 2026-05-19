"""Supply/demand tick and shop-roll catalog tests."""

from __future__ import annotations

import random
from datetime import datetime

import pytest
from flask import Flask

from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    Campaign,
    City,
    GMProfile,
    Item,
    Shop,
    ShopInventory,
    User,
)
from app.services.economy import calculate_dynamic_price
from app.services.economy.supply_demand import (
    apply_supply_demand_to_inventory_rows,
    calculate_elastic_demand,
    seed_next_restock_day,
)
from app.services.shop_roll.shop_type_map import validate_shop_type_map_coverage
from app.services.simulation import SimulationEngine
from app.services.world_generator import validator as wg_validator
from app.services.world_generator.defaults import RANGE_SETTINGS


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


def _gm_and_campaign(sim_app, *, supply_demand_enabled=True):
    with sim_app.app_context():
        user = User(username="gm-eco", password="x", role="GM")
        db.session.add(user)
        db.session.flush()
        gm = GMProfile(user_id=user.id)
        db.session.add(gm)
        db.session.flush()
        campaign = Campaign(
            gm_profile_id=gm.id,
            name="Eco Camp",
            system_type="generic",
            current_game_day=10,
        )
        db.session.add(campaign)
        db.session.flush()
        from app.models import CampaignWorldConfig

        db.session.add(
            CampaignWorldConfig(
                campaign_id=campaign.id,
                settings_json={
                    "schema_version": 2,
                    "supply_demand_enabled": supply_demand_enabled,
                    "inventory_mode": "axis",
                    "ranges": {},
                },
                schema_version=2,
            )
        )
        db.session.commit()
        return campaign.id


def _minimal_world_gen_form(**extra):
    form = {
        "campaign_name": "Test Camp",
        "system_type": "generic",
        "inventory_mode": "axis",
    }
    for key, (floor, ceiling, d_min, d_max) in RANGE_SETTINGS.items():
        form[f"{key}_min"] = str(d_min)
        form[f"{key}_max"] = str(d_max)
    form.update(extra)
    return form


def test_supply_demand_enabled_rejects_string_false():
  from app.services.world_generator.settings_resolve import supply_demand_enabled

  assert supply_demand_enabled({"supply_demand_enabled": True}) is True
  assert supply_demand_enabled({"supply_demand_enabled": False}) is False
  assert supply_demand_enabled({"supply_demand_enabled": "false"}) is False
  assert supply_demand_enabled({"supply_demand_enabled": "true"}) is True
  assert supply_demand_enabled({}) is True


def test_legacy_city_size_maps_to_catalog_demand(sim_app):
    from app.models import City, Shop, Item, ShopInventory
    from app.services.economy.supply_demand import (
        apply_supply_demand_to_inventory_rows,
        resolve_city_size_for_catalog,
    )
    from app.services.shop_roll.catalog import get_catalog

    catalog = get_catalog()
    assert resolve_city_size_for_catalog("Medium", catalog) == "Medium City"
    assert catalog.daily_demand_units["Medium City"] > catalog.daily_demand_units["Small Town"]

    with sim_app.app_context():
        campaign_id = _gm_and_campaign(sim_app)
        city = City(name="Old", size="Medium", population=50000, campaign_id=campaign_id)
        shop = Shop(name="S", type="General Store", campaign_id=campaign_id)
        db.session.add_all([city, shop])
        db.session.flush()
        shop.cities.append(city)
        item = Item(
            name="Goods",
            type="General",
            rarity="Common",
            base_price=50,
            campaign_id=campaign_id,
        )
        db.session.add(item)
        db.session.flush()
        inv = ShopInventory(
            shop_id=shop.shop_id,
            item_id=item.item_id,
            campaign_id=campaign_id,
            stock=30,
            dynamic_price=40,
        )
        seed_next_restock_day(shop, 1, random.Random(2))
        db.session.add(inv)
        db.session.commit()

        apply_supply_demand_to_inventory_rows(
            [inv], game_day=5, rng=random.Random(99)
        )
        assert inv.stock < 30


def test_simulation_skips_supply_when_config_string_false(sim_app):
    from app.models import CampaignWorldConfig
    from app.services.simulation import SimulationEngine

    with sim_app.app_context():
        campaign_id = _gm_and_campaign(sim_app, supply_demand_enabled=False)
        cfg = CampaignWorldConfig.query.filter_by(campaign_id=campaign_id).first()
        cfg.settings_json = {"supply_demand_enabled": "false"}
        db.session.commit()

        city = City(name="T", size="Small Town", population=2000, campaign_id=campaign_id)
        shop = Shop(name="TShop", type="General Store", campaign_id=campaign_id)
        db.session.add_all([city, shop])
        db.session.flush()
        shop.cities.append(city)
        item = Item(
            name="Sword",
            type="Melee",
            rarity="Common",
            base_price=80,
            campaign_id=campaign_id,
        )
        db.session.add(item)
        db.session.flush()
        inv = ShopInventory(
            shop_id=shop.shop_id,
            item_id=item.item_id,
            campaign_id=campaign_id,
            stock=10,
            dynamic_price=80.0,
        )
        db.session.add(inv)
        db.session.commit()

        stats = SimulationEngine().run_tick(campaign_id, commit=True)
        db.session.refresh(inv)
        assert stats["supply_demand_enabled"] is False
        assert stats.get("units_sold", 0) == 0
        assert inv.stock == 10


def test_rarity_for_simulation_maps_common_label():
    from app.services.world_generator.pricing import rarity_for_simulation

    assert rarity_for_simulation("Common") == 1
    assert rarity_for_simulation("common") == 1
    assert rarity_for_simulation("Legendary") == 4


def test_common_item_loses_stock_over_week_sim_ticks(sim_app):
    """Regression: string rarity must not inflate prices and zero-out elastic demand."""
    from app.services.simulation import SimulationEngine

    with sim_app.app_context():
        campaign_id = _gm_and_campaign(sim_app)
        city = City(
            name="Trade City",
            size="Medium City",
            population=50_000,
            campaign_id=campaign_id,
        )
        shop = Shop(name="Market", type="General Store", campaign_id=campaign_id)
        db.session.add_all([city, shop])
        db.session.flush()
        shop.cities.append(city)
        item = Item(
            name="Grain",
            type="General",
            rarity="Common",
            base_price=100,
            campaign_id=campaign_id,
        )
        db.session.add(item)
        db.session.flush()
        seed_next_restock_day(shop, 1, random.Random(3))
        inv = ShopInventory(
            shop_id=shop.shop_id,
            item_id=item.item_id,
            campaign_id=campaign_id,
            stock=50,
            dynamic_price=100.0,
        )
        db.session.add(inv)
        db.session.commit()

        engine = SimulationEngine()
        total_sold = 0
        for _ in range(7):
            stats = engine.run_tick(campaign_id, commit=True)
            total_sold += int(stats.get("units_sold") or 0)

        db.session.refresh(inv)
        assert total_sold > 0
        assert inv.stock < 50


def test_validate_supply_demand_defaults_enabled_on_world_gen():
    """World gen omits the flag; new campaigns default to sim enabled."""
    settings = wg_validator.validate(_minimal_world_gen_form())
    assert settings["supply_demand_enabled"] is True


def test_toggle_supply_demand_legacy_campaign_without_config(sim_app):
    with sim_app.app_context():
        user = User(username="gm-toggle", password="x", role="GM")
        db.session.add(user)
        db.session.flush()
        gm = GMProfile(user_id=user.id)
        db.session.add(gm)
        db.session.flush()
        campaign = Campaign(
            gm_profile_id=gm.id,
            name="Legacy",
            system_type="generic",
        )
        db.session.add(campaign)
        db.session.commit()

        from app.services.world_generator.campaign_settings import (
            read_supply_demand_flag,
            toggle_supply_demand,
        )

        assert read_supply_demand_flag(campaign.id) is True
        enabled, _ = toggle_supply_demand(campaign.id)
        db.session.commit()
        assert enabled is False
        assert read_supply_demand_flag(campaign.id) is False


def test_price_elasticity_clamping():
    massive = calculate_elastic_demand(
        2.0, base_price=100, dynamic_price=1, elasticity=1.5
    )
    assert massive <= 50


def test_strict_shop_type_map_coverage():
    validate_shop_type_map_coverage()


def test_daily_sales_reduce_stock(sim_app):
    with sim_app.app_context():
        campaign_id = _gm_and_campaign(sim_app)
        city = City(
            name="Testburg",
            size="Medium City",
            population=100_000,
            campaign_id=campaign_id,
        )
        shop = Shop(name="S1", type="General Store", campaign_id=campaign_id)
        db.session.add_all([city, shop])
        db.session.flush()
        shop.cities.append(city)
        cheap_item = Item(
            name="Cheap",
            type="General",
            rarity="Common",
            base_price=100,
            campaign_id=campaign_id,
        )
        pricey_item = Item(
            name="Pricey",
            type="General",
            rarity="Common",
            base_price=100,
            campaign_id=campaign_id,
        )
        db.session.add_all([cheap_item, pricey_item])
        db.session.flush()
        inv_cheap = ShopInventory(
            shop_id=shop.shop_id,
            item_id=cheap_item.item_id,
            campaign_id=campaign_id,
            stock=20,
            dynamic_price=50,
        )
        inv_pricey = ShopInventory(
            shop_id=shop.shop_id,
            item_id=pricey_item.item_id,
            campaign_id=campaign_id,
            stock=20,
            dynamic_price=500,
        )
        seed_next_restock_day(shop, 100, random.Random(1))
        db.session.add_all([inv_cheap, inv_pricey])
        db.session.commit()

        apply_supply_demand_to_inventory_rows(
            [inv_cheap, inv_pricey],
            game_day=10,
            rng=random.Random(42),
        )
        cheap_sold = 20 - inv_cheap.stock
        pricey_sold = 20 - inv_pricey.stock
        assert cheap_sold > 0
        assert cheap_sold >= pricey_sold


def test_restock_day_advancement(sim_app):
    with sim_app.app_context():
        campaign_id = _gm_and_campaign(sim_app)
        city = City(name="R", size="Village", population=500, campaign_id=campaign_id)
        shop = Shop(name="RShop", type="Tavern", campaign_id=campaign_id)
        db.session.add_all([city, shop])
        db.session.flush()
        shop.cities.append(city)
        item = Item(
            name="Ale",
            type="Consumable",
            rarity="Common",
            base_price=10,
            campaign_id=campaign_id,
        )
        db.session.add(item)
        db.session.flush()
        shop.next_restock_day = 5
        inv = ShopInventory(
            shop_id=shop.shop_id,
            item_id=item.item_id,
            campaign_id=campaign_id,
            stock=1,
            dynamic_price=10.0,
        )
        db.session.add(inv)
        db.session.commit()

        apply_supply_demand_to_inventory_rows(
            [inv], game_day=10, rng=random.Random(7)
        )
        assert shop.next_restock_day is not None
        assert shop.next_restock_day >= 25
        assert shop.next_restock_day <= 40
        assert inv.stock > 1


def test_price_reacts_to_stock(sim_app):
    with sim_app.app_context():
        campaign_id = _gm_and_campaign(sim_app)
        city = City(name="P", size="Hamlet", population=50, campaign_id=campaign_id)
        shop = Shop(name="PShop", type="General Store", campaign_id=campaign_id)
        db.session.add_all([city, shop])
        db.session.flush()
        shop.cities.append(city)
        item = Item(
            name="Rope",
            type="General",
            rarity="5",
            base_price=100,
            campaign_id=campaign_id,
        )
        db.session.add(item)
        db.session.flush()
        shop.next_restock_day = 999
        inv = ShopInventory(
            shop_id=shop.shop_id,
            item_id=item.item_id,
            campaign_id=campaign_id,
            stock=50,
            dynamic_price=100.0,
        )
        db.session.add(inv)
        db.session.commit()

        high_stock_price = calculate_dynamic_price(
            item.base_price,
            5,
            500,
            shop.shop_id,
            city.city_id,
            campaign_id,
            item_id=item.item_id,
            rng=random.Random(1),
        )
        low_stock_price = calculate_dynamic_price(
            item.base_price,
            5,
            1,
            shop.shop_id,
            city.city_id,
            campaign_id,
            item_id=item.item_id,
            rng=random.Random(1),
        )
        assert low_stock_price > high_stock_price


def test_run_tick_supply_demand(sim_app):
    with sim_app.app_context():
        campaign_id = _gm_and_campaign(sim_app)
        city = City(name="T", size="Small Town", population=2000, campaign_id=campaign_id)
        shop = Shop(name="TShop", type="Smithy", campaign_id=campaign_id)
        db.session.add_all([city, shop])
        db.session.flush()
        shop.cities.append(city)
        item = Item(
            name="Sword",
            type="Melee",
            rarity="Common",
            base_price=80,
            campaign_id=campaign_id,
        )
        db.session.add(item)
        db.session.flush()
        seed_next_restock_day(shop, 1, random.Random(0))
        inv = ShopInventory(
            shop_id=shop.shop_id,
            item_id=item.item_id,
            campaign_id=campaign_id,
            stock=10,
            dynamic_price=80.0,
        )
        db.session.add(inv)
        db.session.commit()

        engine = SimulationEngine()
        stats = engine.run_tick(campaign_id, commit=True)
        db.session.refresh(inv)
        campaign = Campaign.query.get(campaign_id)
        assert campaign.current_game_day == 11
        assert stats.get("units_sold", 0) >= 0
        assert inv.stock <= 10
