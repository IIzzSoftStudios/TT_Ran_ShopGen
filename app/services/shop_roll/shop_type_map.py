"""Map axis-generated shop type strings to roll catalog categories."""

from __future__ import annotations

from typing import Dict, Set

from app.services.world_generator import naming_logic

TYPE_TO_CATEGORY_MAP: Dict[str, str] = {
    # god_magic
    "Reliquary": "magic",
    "Sanctum": "magic",
    "Altar": "magic",
    "Shrine": "magic",
    # high_magic
    "Apothecary": "consumables",
    "Rune-Scribe": "magic",
    "Enchanter": "magic",
    "Spellwright": "magic",
    # low_magic
    "General Store": "general",
    "Smithy": "weapons",
    "Herbalist": "consumables",
    "Trading Post": "general",
    # medieval
    "Tavern": "tavern",
    "Fletcher": "weapons",
    "Armorer": "armor",
    # renaissance
    "Emporium": "general",
    "Artisan's Guild": "general",
    "Compass Works": "general",
    "Foundry": "weapons",
    # industrial
    "Rail Supply": "general",
    "Steel Works": "weapons",
    "Machinists": "weapons",
    # modern
    "Supply Depot": "general",
    "Tactical Outfitter": "weapons",
    "Logistics": "general",
    "Armory": "weapons",
    # post_apoc
    "Junk Heap": "general",
    "Scrap Exchange": "general",
    "Bullet & Bone": "weapons",
    "Salvage": "general",
}


def all_axis_shop_types() -> Set[str]:
    return {t for band in naming_logic._SHOP_TYPE_BY_BAND.values() for t in band}


def validate_shop_type_map_coverage() -> None:
    missing = sorted(all_axis_shop_types() - set(TYPE_TO_CATEGORY_MAP))
    if missing:
        raise ValueError(
            "TYPE_TO_CATEGORY_MAP is missing shop types from naming_logic: "
            + ", ".join(missing)
        )
