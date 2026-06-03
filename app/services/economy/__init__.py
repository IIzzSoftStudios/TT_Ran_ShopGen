"""Economy helpers: dynamic pricing (package replaces legacy ``services/economy.py``)."""

import random
from typing import Optional

from app.extensions import db
from app.models import Shop

from app.services.economy.demand import DemandContext, calculate_demand
from app.services.world_generator.pricing import rarity_for_simulation

_PRICE_FLOOR_MULTIPLIER = 0.20
_PRICE_CEILING_MULTIPLIER = 5.00


def calculate_dynamic_price(
    base_price,
    rarity,
    stock_level,
    shop_id,
    city_id,
    campaign_id: int,
    item_id=None,
    rng: Optional[random.Random] = None,
    preloaded_modifiers=None,
    demand_context=None,
):
    rng = rng or random
    demand_m = calculate_demand(
        rarity,
        stock_level,
        campaign_id,
        city_id=city_id,
        shop_id=shop_id,
        item_id=item_id,
        rng=rng,
        preloaded_modifiers=preloaded_modifiers,
        demand_context=demand_context,
    )
    stock_modifier = max(0.1, (stock_level / 100) * 0.1)
    event_modifier = rng.choice([-0.1, 0, 0.2])
    raw = float(base_price) * float(demand_m) * (1 - stock_modifier + event_modifier)
    lo = float(base_price) * _PRICE_FLOOR_MULTIPLIER
    hi = float(base_price) * _PRICE_CEILING_MULTIPLIER
    return round(max(lo, min(hi, raw)), 2)


def update_shop_prices(campaign_id: int):
    """Recompute dynamic_price for all inventory in one campaign. Prefer SimulationEngine for production."""
    shops = Shop.query.filter_by(campaign_id=campaign_id).all()
    for shop in shops:
        city_id = shop.cities[0].city_id if shop.cities else None
        for inventory in shop.inventory:
            if not inventory.item:
                continue
            base_price = inventory.item.base_price
            rarity = rarity_for_simulation(inventory.item.rarity)
            stock_level = inventory.stock
            new_price = calculate_dynamic_price(
                base_price,
                rarity,
                stock_level,
                shop.shop_id,
                city_id,
                campaign_id,
                item_id=inventory.item_id,
            )
            inventory.dynamic_price = new_price
    db.session.commit()
