"""YAML-driven shop slot rolls and city-size helpers for world generation."""

from app.services.shop_roll.catalog import ShopRollCatalog, get_catalog, load_catalog
from app.services.shop_roll.city_size import pick_city_size_and_population, variation_slider_to_tier
from app.services.shop_roll.shop_type_map import TYPE_TO_CATEGORY_MAP, validate_shop_type_map_coverage

__all__ = [
    "ShopRollCatalog",
    "get_catalog",
    "load_catalog",
    "pick_city_size_and_population",
    "variation_slider_to_tier",
    "TYPE_TO_CATEGORY_MAP",
    "validate_shop_type_map_coverage",
]
