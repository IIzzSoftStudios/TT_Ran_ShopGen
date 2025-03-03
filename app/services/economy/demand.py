# app/services/economy/demand.py

import random
from app.models import DemandModifier, ModifierTarget
from app.extensions import db

def get_active_modifiers(city_id=None, shop_id=None, item_id=None):
    """
    Retrieves all active demand modifiers affecting the current calculation.
    Filters based on scope (global, region, city, shop, or item).
    """
    active_modifiers = DemandModifier.query.filter(DemandModifier.is_active == True).all()
    
    total_modifier = 1.0  # Start with base demand of 1.0

    for mod in active_modifiers:
        # Apply global modifiers
        if mod.scope == "global":
            total_modifier += mod.effect_value

        # Apply city/shop/item-specific modifiers
        for target in mod.targets:
            if target.entity_type == "city" and target.entity_id == city_id:
                total_modifier += mod.effect_value
            elif target.entity_type == "shop" and target.entity_id == shop_id:
                total_modifier += mod.effect_value
            elif target.entity_type == "item" and target.entity_id == item_id:
                total_modifier += mod.effect_value

    return total_modifier

def calculate_demand(rarity, stock_level, city_id=None, shop_id=None, item_id=None):
    """
    Calculates demand dynamically using active modifiers and external factors.
    """
    # Fetch dynamic demand modifier
    demand_modifier = get_active_modifiers(city_id, shop_id, item_id)

    # Stock and rarity influences
    rarity_effect = rarity * 0.2
    stock_effect = max(0.1, (stock_level / 100) * 0.1)
    random_fluctuation = random.uniform(0.9, 1.1)  # Small variation

    demand = demand_modifier * (1 + rarity_effect - stock_effect) * random_fluctuation
    return round(demand, 2)
