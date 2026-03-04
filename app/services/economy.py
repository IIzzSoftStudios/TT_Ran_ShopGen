# app/services/economy.py

from app.services.economy.demand import calculate_demand
from app.models import ShopInventory, Shop
from app.extensions import db
import random

# Economic safety rails: final price must stay within 20%–500% of base price
_PRICE_FLOOR_MULTIPLIER = 0.20
_PRICE_CEILING_MULTIPLIER = 5.00


def calculate_dynamic_price(base_price, rarity, stock_level, shop_id, city_id):
    """
    Calculates dynamic price using rarity, stock, and random factors.
    Result is clamped to 20%–500% of base_price and rounded to 2 decimals.
    """
    demand_factor = calculate_demand(rarity, stock_level, city_id=city_id, shop_id=shop_id)

    # Stock effect (higher stock = lower price)
    stock_modifier = max(0.1, (stock_level / 100))

    # Event effect (e.g., seasonal pricing fluctuations)
    event_modifier = random.choice([-0.1, 0, 0.2])

    # Single multiplicative-style factor, then clamp and round
    raw_price = base_price * (1 + demand_factor - stock_modifier + event_modifier)
    floor = base_price * _PRICE_FLOOR_MULTIPLIER
    ceiling = base_price * _PRICE_CEILING_MULTIPLIER
    clamped = max(floor, min(ceiling, raw_price))
    return round(clamped, 2)


def update_shop_prices():
    """
    Loops through all shop inventories and updates prices dynamically.
    Loads all inventory with item and shop eager-loaded to avoid N+1.
    """
    inventory_list = (
        ShopInventory.query
        .options(
            db.joinedload(ShopInventory.item),
            db.joinedload(ShopInventory.shop).joinedload(Shop.cities),
        )
        .all()
    )

    for inventory in inventory_list:
        shop = inventory.shop
        city_id = shop.cities[0].city_id if shop.cities else None

        base_price = inventory.item.base_price
        rarity = int(inventory.item.rarity) if inventory.item.rarity.isdigit() else 5
        stock_level = inventory.stock

        new_price = calculate_dynamic_price(
            base_price, rarity, stock_level, shop.shop_id, city_id
        )
        inventory.dynamic_price = new_price

    db.session.commit()
