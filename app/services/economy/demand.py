# app/services/economy/demand.py

import random
from typing import Optional

from app.models import DemandModifier


def get_active_modifiers(
    campaign_id: int,
    city_id=None,
    shop_id=None,
    item_id=None,
):
    """
    Retrieves active demand modifiers for one campaign.
    Filters based on scope (global, region, city, shop, or item) and target rows.
    """
    active_modifiers = (
        DemandModifier.query.filter(
            DemandModifier.is_active == True,
            DemandModifier.campaign_id == campaign_id,
        ).all()
    )

    total_modifier = 1.0

    for mod in active_modifiers:
        if mod.scope == "global":
            total_modifier += mod.effect_value

        for target in mod.targets:
            if target.campaign_id != campaign_id:
                continue
            if target.entity_type == "city" and target.entity_id == city_id:
                total_modifier += mod.effect_value
            elif target.entity_type == "shop" and target.entity_id == shop_id:
                total_modifier += mod.effect_value
            elif target.entity_type == "item" and target.entity_id == item_id:
                total_modifier += mod.effect_value

    return total_modifier


def calculate_demand(
    rarity,
    stock_level,
    campaign_id: int,
    city_id=None,
    shop_id=None,
    item_id=None,
    rng: Optional[random.Random] = None,
):
    """
    Demand strength as a multiplier (~0.5–3+) from DB modifiers, rarity, stock, and RNG.
    """
    rng = rng or random
    modifier_base = get_active_modifiers(
        campaign_id, city_id=city_id, shop_id=shop_id, item_id=item_id
    )
    rarity_effect = rarity * 0.2
    stock_effect = max(0.1, (stock_level / 100) * 0.1)
    random_fluctuation = rng.uniform(0.9, 1.1)

    demand = modifier_base * (1 + rarity_effect - stock_effect) * random_fluctuation
    return round(demand, 4)
