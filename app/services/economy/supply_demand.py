"""Daily simulated sales and periodic shop restocks (supply/demand tick)."""

from __future__ import annotations

import logging
import math
import random
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.extensions import db
from app.models import Shop, ShopInventory
from app.services.shop_roll.catalog import ShopRollCatalog, get_catalog
from app.services.shop_roll.shop_type_map import TYPE_TO_CATEGORY_MAP

log = logging.getLogger(__name__)

_DEFAULT_SIZE = "Small Town"

# Legacy world-gen sizes (population bands) -> catalog settlement tiers.
_CITY_SIZE_ALIASES = {
    "Small": "Small Town",
    "Medium": "Medium City",
    "Large": "Large City",
}


def resolve_city_size_for_catalog(
    city_size: str,
    catalog: Optional[ShopRollCatalog] = None,
) -> str:
    """Map city.size to a key present in ``shop_roll_catalog.yaml`` demand tables."""
    catalog = catalog or get_catalog()
    if city_size in catalog.daily_demand_units:
        return city_size
    aliased = _CITY_SIZE_ALIASES.get(city_size or "")
    if aliased and aliased in catalog.daily_demand_units:
        return aliased
    return _DEFAULT_SIZE


def calculate_elastic_demand(
    base_units: float,
    base_price: int,
    dynamic_price: int,
    elasticity: float,
    *,
    price_ratio_floor: float = 0.2,
    max_demand_multiplier: float = 5.0,
    min_demand_multiplier: float = 0.01,
) -> int:
    """Bounded constant-elasticity daily demand (Q scales as P^-e with clamps)."""
    if base_price <= 0:
        return max(0, int(base_units))

    price_ratio = float(dynamic_price) / float(base_price)
    safe_ratio = max(price_ratio_floor, price_ratio)
    demand_modifier = safe_ratio ** (-float(elasticity))
    demand_modifier = min(
        max_demand_multiplier,
        max(min_demand_multiplier, demand_modifier),
    )
    # Ceil so fractional demand (e.g. 0.3 units/day) still moves stock when
    # elasticity suppresses sales at high prices.
    return max(0, int(math.ceil(base_units * demand_modifier - 1e-9)))


def _primary_city_size(shop: Shop, catalog: Optional[ShopRollCatalog] = None) -> str:
    if not shop.cities:
        return _DEFAULT_SIZE
    city = sorted(shop.cities, key=lambda c: c.city_id)[0]
    return resolve_city_size_for_catalog(city.size or _DEFAULT_SIZE, catalog)


def backfill_shop_restock_schedules(
    campaign_id: int,
    game_day: int,
    rng: random.Random,
    catalog: Optional[ShopRollCatalog] = None,
) -> int:
    """Assign ``next_restock_day`` for shops that never received a schedule (legacy DBs)."""
    catalog = catalog or get_catalog()
    shops = Shop.query.filter_by(campaign_id=campaign_id).filter(
        Shop.next_restock_day.is_(None)
    ).all()
    for shop in shops:
        seed_next_restock_day(shop, game_day, rng, catalog)
    return len(shops)


def seed_next_restock_day(
    shop: Shop,
    game_day: int,
    rng: random.Random,
    catalog: Optional[ShopRollCatalog] = None,
) -> int:
    catalog = catalog or get_catalog()
    lo, hi = catalog.restock_interval_days
    shop.next_restock_day = int(game_day) + rng.randint(lo, hi)
    return shop.next_restock_day


def apply_supply_demand_to_inventory_rows(
    inventory_rows: List[ShopInventory],
    game_day: int,
    rng: random.Random,
    catalog: Optional[ShopRollCatalog] = None,
) -> Dict[str, Any]:
    """Mutate loaded ORM rows in place; return tick stats."""
    catalog = catalog or get_catalog()
    t0 = perf_counter()
    units_sold_total = 0
    shops_restocked: set = set()
    var_lo, var_hi = catalog.daily_variance
    restock_lo, restock_hi = catalog.restock_variance

    shops_due: Dict[int, Shop] = {}
    for inv in inventory_rows:
        shop = inv.shop
        if not shop or shop.shop_id is None:
            continue
        if shop.next_restock_day is None:
            seed_next_restock_day(shop, game_day, rng, catalog)
            continue
        if game_day >= shop.next_restock_day:
            shops_due[shop.shop_id] = shop

    for shop in shops_due.values():
        seed_next_restock_day(shop, game_day, rng, catalog)
        shops_restocked.add(shop.shop_id)

    for inv in inventory_rows:
        if not inv.item or not inv.shop:
            continue
        shop = inv.shop
        city_size = _primary_city_size(shop, catalog)
        base_demand = catalog.daily_demand_units.get(city_size, 1.0)
        elasticity = catalog.elasticity_for_shop_type(shop.type, TYPE_TO_CATEGORY_MAP)
        base_price = int(inv.item.base_price)
        dynamic_price = int(max(1, round(float(inv.dynamic_price))))

        units = calculate_elastic_demand(
            base_demand,
            base_price,
            dynamic_price,
            elasticity,
            price_ratio_floor=catalog.price_ratio_floor,
            max_demand_multiplier=catalog.demand_multiplier_max,
            min_demand_multiplier=catalog.demand_multiplier_min,
        )
        scaled = units * rng.uniform(var_lo, var_hi)
        units = max(0, int(math.floor(scaled)))
        if units == 0 and scaled >= 0.25:
            units = 1
        stock = int(inv.stock or 0)
        sold = min(stock, max(0, units))
        inv.stock = stock - sold
        units_sold_total += sold

        if shop.shop_id in shops_due:
            restock_base = catalog.restock_units.get(city_size, 6)
            cap = catalog.stock_cap.get(city_size, 20)
            add = int(restock_base * rng.uniform(restock_lo, restock_hi))
            inv.stock = min(cap, int(inv.stock or 0) + add)

    elapsed_ms = (perf_counter() - t0) * 1000.0
    return {
        "units_sold": units_sold_total,
        "shops_restocked": len(shops_restocked),
        "supply_demand_ms": round(elapsed_ms, 3),
    }


def run_supply_demand_tick(
    campaign_id: int,
    game_day: int,
    rng: random.Random,
    catalog: Optional[ShopRollCatalog] = None,
) -> Dict[str, Any]:
    """Load campaign inventory and apply supply/demand (batch path for standalone use)."""
    from app.models import Shop as ShopModel

    catalog = catalog or get_catalog()
    rows = (
        ShopInventory.query.join(ShopModel, ShopInventory.shop_id == ShopModel.shop_id)
        .filter(ShopModel.campaign_id == campaign_id)
        .options(
            db.joinedload(ShopInventory.item),
            db.joinedload(ShopInventory.shop).joinedload(ShopModel.cities),
        )
        .all()
    )
    return apply_supply_demand_to_inventory_rows(rows, game_day, rng, catalog)


def batch_persist_stock_updates(
    inventory_updates: List[Dict[str, Any]],
    shop_restock_updates: List[Dict[str, Any]],
) -> None:
    """Optional executemany path when rows were computed outside the ORM session."""
    if inventory_updates:
        db.session.execute(
            text(
                "UPDATE shop_inventory SET stock = :stock "
                "WHERE inventory_id = :inv_id"
            ),
            inventory_updates,
        )
    if shop_restock_updates:
        db.session.execute(
            text(
                "UPDATE shops SET next_restock_day = :next_day "
                "WHERE shop_id = :shop_id"
            ),
            shop_restock_updates,
        )
