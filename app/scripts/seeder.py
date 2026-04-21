"""World seeding for GM campaigns (expand as needed)."""


def seed_gm_data(
    gm_profile_id: int,
    *,
    num_cities: int = 10,
    num_shops_per_city: int = 10,
    num_global_items: int = 75,
    num_items_per_shop: int = 10,
) -> bool:
    """
    Populate demo content for a GM profile.
    Currently a no-op placeholder so imports and routes work; extend with Faker/SQLAlchemy as needed.
    """
    _ = (gm_profile_id, num_cities, num_shops_per_city, num_global_items, num_items_per_shop)
    return True
