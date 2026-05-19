"""Ensure YAML catalog item names exist as campaign ``Item`` rows."""

from __future__ import annotations

from typing import Dict, List, Optional

from app.models import Item
from app.services.shop_roll.catalog import ShopRollCatalog, get_catalog


def sync_catalog_items(
    campaign_id: int,
    catalog: Optional[ShopRollCatalog] = None,
    *,
    axis_position: int = 5,
) -> Dict[str, Item]:
    """Create missing pool items; return name -> Item for the campaign."""
    catalog = catalog or get_catalog()
    existing = {
        i.name: i
        for i in Item.query.filter_by(campaign_id=campaign_id).all()
    }
    created: List[Item] = []
    for pool_names in catalog.item_pools.values():
        for name in pool_names:
            if name in existing:
                continue
            base = catalog.base_prices_copper.get(name, 100)
            item = Item(
                name=name,
                type="General",
                rarity="Common",
                base_price=int(base),
                description=f"Catalog item: {name}",
                campaign_id=campaign_id,
                axis_position=axis_position,
            )
            created.append(item)
            existing[name] = item
    if created:
        from app.extensions import db

        db.session.add_all(created)
        db.session.flush()
    return existing
