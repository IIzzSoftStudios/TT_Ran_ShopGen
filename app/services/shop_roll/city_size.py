"""Map City Size Variation slider values to settlement tiers."""

from __future__ import annotations

import random
from typing import Dict, Tuple

from app.services.shop_roll.catalog import ShopRollCatalog, get_catalog


def variation_slider_to_tier(slider_value: int, catalog: ShopRollCatalog | None = None) -> int:
    catalog = catalog or get_catalog()
    clamped = max(1, min(20, int(slider_value)))
    return int(catalog.variation_tier_steps.get(clamped, 0))


def pick_city_size_and_population(
    rng: random.Random,
    variation_min: int,
    variation_max: int,
    catalog: ShopRollCatalog | None = None,
) -> Tuple[str, int]:
    """Roll a slider in [variation_min, variation_max] and return GM-aligned size + population."""
    catalog = catalog or get_catalog()
    lo = max(1, min(20, int(variation_min)))
    hi = max(1, min(20, int(variation_max)))
    if lo > hi:
        lo, hi = hi, lo
    slider = rng.randint(lo, hi)
    tier = variation_slider_to_tier(slider, catalog)
    tier = max(0, min(len(catalog.city_sizes) - 1, tier))
    size = catalog.city_sizes[tier]
    pop_lo, pop_hi = catalog.population_bands[size]
    population = rng.randint(int(pop_lo), int(pop_hi))
    return size, population
