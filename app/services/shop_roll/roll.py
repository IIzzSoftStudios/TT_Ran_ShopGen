"""Slot-roll inventory lines for a shop at world generation."""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Set

from app.models import Item, Shop, ShopInventory
from app.services.shop_roll.catalog import ShopRollCatalog, get_catalog
from app.services.shop_roll.shop_type_map import TYPE_TO_CATEGORY_MAP
from app.services.world_generator import pricing


def roll_shop_inventory_rows(
    *,
    shop: Shop,
    city_size: str,
    campaign_id: int,
    items_by_name: Dict[str, Item],
    rng: random.Random,
    catalog: Optional[ShopRollCatalog] = None,
    n_slots: Optional[int] = None,
) -> List[ShopInventory]:
    """Build ``ShopInventory`` rows (not yet added to session) for one shop."""
    catalog = catalog or get_catalog()
    category = TYPE_TO_CATEGORY_MAP.get(shop.type, "general")
    pool = list(catalog.item_pools.get(category, catalog.item_pools.get("general", [])))
    if not pool:
        pool = list(catalog.item_pools.get("general", []))

    lo, hi = catalog.slot_count_range(city_size)
    count = n_slots if n_slots is not None else rng.randint(lo, hi)
    picked: Set[str] = set()
    rows: List[ShopInventory] = []
    attempts = 0
    max_attempts = max(count * 4, 4)

    while len(rows) < count and attempts < max_attempts:
        attempts += 1
        name = rng.choice(pool)
        if name in picked:
            continue
        item = items_by_name.get(name)
        if item is None:
            continue
        picked.add(name)
        base = int(item.base_price)
        variance = rng.uniform(0.75, 1.25)
        dynamic = pricing.dynamic_price_arithmetic(
            base,
            region_mult=1.0,
            axis_distance_mult=variance,
        )
        cap = catalog.stock_cap.get(city_size, 20)
        stock = rng.randint(1, min(10, cap))
        rows.append(
            ShopInventory(
                shop_id=shop.shop_id,
                item_id=item.item_id,
                campaign_id=campaign_id,
                stock=stock,
                dynamic_price=dynamic,
            )
        )
    return rows
