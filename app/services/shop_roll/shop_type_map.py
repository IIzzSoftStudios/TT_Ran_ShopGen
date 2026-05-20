"""Map axis-generated shop type strings to roll catalog categories."""

from __future__ import annotations

from typing import Dict, List, Sequence, Set, TypeVar

from app.services.world_generator import naming_logic

T = TypeVar("T")

# Single-assignment: each shop type resolves to exactly one broad stocking category.
TYPE_TO_CATEGORY_MAP: Dict[str, str] = {
    # god_magic
    "Reliquary": "magic",
    "Sanctum": "magic",
    "Altar": "magic",
    "Shrine": "magic",
    "Temple": "magic",
    "Chantry": "magic",
    "Sacristy": "magic",
    "Vestry": "magic",
    "Oracle Post": "magic",
    "Lightward Trading": "general",
    "Sacred Vault": "magic",
    "Dawn Chapel": "magic",
    # high_magic
    "Apothecary": "consumables",
    "Rune-Scribe": "magic",
    "Enchanter": "magic",
    "Spellwright": "magic",
    "Thaumaturgist": "magic",
    "Alchemist": "consumables",
    "Arcane Exchange": "magic",
    "Scroll Vault": "magic",
    "Focus Foundry": "magic",
    "Grimoire Library": "magic",
    "Scriptorium": "magic",
    "Ley-Ward Shop": "magic",
    # low_magic
    "General Store": "general",
    "Smithy": "weapons",
    "Herbalist": "consumables",
    "Trading Post": "general",
    "Chandler": "general",
    "Cooper": "general",
    "Wheelwright": "general",
    "Carpenter": "general",
    "Weaver": "general",
    "Tanner": "general",
    "Shoemaker": "general",
    "Hedge Apothecary": "consumables",
    # medieval
    "Tavern": "tavern",
    "Fletcher": "weapons",
    "Armorer": "armor",
    "Bowyer": "weapons",
    "Bladesmith": "weapons",
    "Blacksmith": "weapons",
    "Locksmith": "general",
    "Farrier": "general",
    "Tailor": "general",
    "Mercer": "general",
    "Inn": "tavern",
    "Alehouse": "tavern",
    # renaissance
    "Emporium": "general",
    "Artisan's Guild": "general",
    "Compass Works": "general",
    "Foundry": "weapons",
    "Atelier": "general",
    "Workshop": "general",
    "Observatory": "general",
    "Bookshop": "general",
    "Printing House": "general",
    "Clockmaker": "general",
    "Glassworks": "general",
    "Cartographer": "general",
    # industrial
    "Rail Supply": "general",
    "Steel Works": "weapons",
    "Machinists": "weapons",
    "Mill": "general",
    "Factory": "general",
    "Plant": "general",
    "Machine Shop": "general",
    "Boiler House": "general",
    "Pump House": "general",
    "Warehouse": "general",
    "Gasworks": "general",
    # modern
    "Supply Depot": "general",
    "Tactical Outfitter": "weapons",
    "Logistics": "general",
    "Armory": "weapons",
    "Hardware Depot": "general",
    "Surplus Store": "armor",
    "Pharmacy": "consumables",
    "Automotive Hub": "general",
    "Electronics Hub": "general",
    "Wholesaler": "general",
    "Showroom": "general",
    "Distribution Complex": "general",
    # post_apoc
    "Junk Heap": "general",
    "Scrap Exchange": "general",
    "Bullet & Bone": "weapons",
    "Salvage": "general",
    "Trade Post": "general",
    "Barter Town": "general",
    "Scavenger Den": "general",
    "Rust Market": "general",
    "Fuel Barter": "consumables",
    "Scrap Yard": "general",
    "Outlaw Bazaar": "general",
    "Casing Press": "weapons",
}

CATEGORY_TO_ITEM_TYPES: Dict[str, List[str]] = {
    "weapons": ["Melee", "Ranged"],
    "armor": ["Armor"],
    "consumables": ["Consumable"],
    "magic": ["Consumable", "General"],
    "general": ["General", "Consumable"],
    "tavern": ["Consumable", "General"],
}


def preferred_item_types_for_shop(shop_type: str) -> List[str]:
    """Resolve shop type to procedural item types; default to general."""
    category = TYPE_TO_CATEGORY_MAP.get(shop_type, "general")
    return list(CATEGORY_TO_ITEM_TYPES.get(category, ["General"]))


def get_biased_shop_pool(
    age_compatible_items: Sequence[T],
    shop_type: str,
    min_pool_size: int,
) -> List[T]:
    """Prefer category-matching items; fall back if the preferred pool is too small."""
    if not age_compatible_items:
        return []

    preferred_types = preferred_item_types_for_shop(shop_type)
    preferred_pool = [
        item for item in age_compatible_items if getattr(item, "type", None) in preferred_types
    ]

    threshold = max(1, int(min_pool_size))
    if len(preferred_pool) >= threshold:
        return preferred_pool

    return list(age_compatible_items)


def all_axis_shop_types() -> Set[str]:
    return {t for band in naming_logic._SHOP_TYPE_BY_BAND.values() for t in band}


def validate_shop_type_map_coverage() -> None:
    missing = sorted(all_axis_shop_types() - set(TYPE_TO_CATEGORY_MAP))
    if missing:
        raise ValueError(
            "TYPE_TO_CATEGORY_MAP is missing shop types from naming_logic: "
            + ", ".join(missing)
        )
