from .demand import calculate_demand

def calculate_dynamic_price(base_price, rarity, stock_level, shop_id, city_id):
    """
    Calculate a dynamic price based on various factors including demand, rarity, and stock levels.
    """
    # Calculate demand factor
    demand_factor = calculate_demand(rarity, stock_level, city_id, shop_id)
    
    # Apply demand factor to base price
    new_price = base_price * demand_factor
    
    # Ensure price doesn't go below a minimum threshold
    min_price = base_price * 0.5  # Minimum 50% of base price
    new_price = max(min_price, new_price)
    
    return round(new_price, 2)
