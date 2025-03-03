# app/services/economy.py

from app.services.economy.demand import calculate_demand
from app.models import ShopInventory, Shop
from app.extensions import db
import random

def calculate_dynamic_price(base_price, rarity, stock_level, shop_id, city_id):
    """
    Calculates dynamic price using the demand system and real-time modifiers.
    """
    # Fetch demand modifier based on city/shop conditions
    demand_modifier = calculate_demand(rarity, stock_level, city_id=city_id, shop_id=shop_id)

    # Stock effect (Higher stock = lower price)
    stock_modifier = max(0.1, (stock_level / 100))

    # Event effect (e.g., seasonal pricing fluctuations)
    event_modifier = random.choice([-0.1, 0, 0.2])

    # Final dynamic price calculation
    return round(base_price * (1 + demand_modifier - stock_modifier + event_modifier), 2)

def update_shop_prices():
    """
    Loops through all shop inventories and updates prices dynamically.
    """
    shops = Shop.query.all()  # Fetch all shops
    
    for shop in shops:
        city_id = shop.cities[0].city_id if shop.cities else None  # Get city ID if available
        
        for inventory in shop.inventory:
            base_price = inventory.item.base_price
            rarity = int(inventory.item.rarity) if inventory.item.rarity.isdigit() else 5  # Convert rarity
            stock_level = inventory.stock

            # Calculate new price
            new_price = calculate_dynamic_price(base_price, rarity, stock_level, shop.shop_id, city_id)

            # Update item price
            inventory.dynamic_price = new_price

    db.session.commit()
