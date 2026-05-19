"""Single source of truth for Phase 1 world-gen floors, ceilings, and enum
whitelists. Read by both the validator and the GET handler that renders
`GM_generate_world.html`.

Any change here must also update `validator.DEFAULT_SETTINGS` assumptions.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple


# Schema version stamped into CampaignWorldConfig.settings_json.
# Phase 1 = 1; city_size_variation + supply/demand = 2.
SCHEMA_VERSION: int = 2


# -----------------------------------------------------------------------------
# Range settings
# -----------------------------------------------------------------------------
# Each tuple is (floor, ceiling, default_min, default_max).
# The default pair is what the UI renders when the GM first opens the form and
# what `seeder.seed_gm_data` uses for the compatibility shim.
RANGE_SETTINGS: Dict[str, Tuple[int, int, int, int]] = {
    "num_cities":             (1,   40,  3,  8),
    "num_regions":            (1,   10,  2,  4),
    "global_item_pool_size":  (25, 500, 50, 120),
    "city_size_variation":    (1,   20,  3,  8),
    "items_per_shop":         (1,   30,  5, 15),
    # Fused axis: 0 = God Magic, 5 = Medieval, 10 = Post-Apoc Tech.
    "tech_magic_balance":     (0,   10,  4,  6),
}


# -----------------------------------------------------------------------------
# Hard composite caps (swarm-approved)
# -----------------------------------------------------------------------------
# ShopInventory worst-case: cities.max * max(shops_per_size) * items_per_shop.max.
SHOP_INVENTORY_CAP: int = 15_000
# Total entity cap across all generated tables (cities + shops + items + markets
# + inventory + regions + sim_state + config + campaign ...).
TOTAL_ENTITY_CAP: int = 20_000


# -----------------------------------------------------------------------------
# Fused tech_magic_balance axis
# -----------------------------------------------------------------------------
# Inventory selection tolerances (axis distance from city's region axis).
AXIS_TOLERANCE_PRIMARY: int = 1   # |delta| <= 1 -> "native" stock
AXIS_TOLERANCE_IMPORTED: int = 3  # |delta| <= 3 -> "imported" stock (premium)
IMPORTED_PRICE_MULTIPLIER: float = 2.0  # imported items cost 2x base


# 11-position (0..10) axis position -> 8-band naming lookup.
# Used by `naming_logic.py` and `stat_factory.py`.
AXIS_POSITION_TO_BAND: Dict[int, str] = {
    0: "god_magic",
    1: "god_magic",
    2: "high_magic",
    3: "high_magic",
    4: "low_magic",
    5: "medieval",
    6: "renaissance",
    7: "industrial",
    8: "modern",
    9: "post_apoc",
    10: "post_apoc",
}


# Stat-factory gates.
FIREARM_MIN_AXIS: int = 6          # axis >= 6 unlocks firearms
MAGIC_BONUS_MAX_AXIS: int = 4      # axis <= 4 unlocks magic +N bonuses
CURSED_UNIQUE_FREQUENCY_DEFAULT: float = 0.1  # Phase 1: fixed 10% chance


# -----------------------------------------------------------------------------
# Enum whitelists
# -----------------------------------------------------------------------------
GOVERNMENT_TYPES: Tuple[str, ...] = (
    "Feudal", "Corporate", "Anarchy", "Theocratic", "Tribal",
)

SIMULATION_SPEEDS: Tuple[str, ...] = ("pause", "slow", "normal")

# Initial `SimulationState.speed` when a world is generated (GM runs ticks manually).
DEFAULT_SIMULATION_SPEED: str = "pause"

SYSTEM_TYPES: Tuple[str, ...] = ("dnd5e", "pf2e", "generic")

ITEM_CATEGORIES: Tuple[str, ...] = (
    "Melee", "Ranged", "Armor", "General", "Consumable",
)

RARITIES: Tuple[str, ...] = ("Common", "Uncommon", "Rare", "Legendary")
RARITY_WEIGHTS: Dict[str, float] = {
    "Common":     0.60,
    "Uncommon":   0.25,
    "Rare":       0.12,
    "Legendary":  0.03,
}


# -----------------------------------------------------------------------------
# Seed / misc
# -----------------------------------------------------------------------------
SEED_MIN: int = 0
SEED_MAX: int = 2 ** 31 - 1       # fits in a signed int32
# Wall-clock cap for `generator.generate`. None = run until finished (no timeout).
# Set to a positive int (e.g. 120) if you want a safety limit in production.
GENERATION_TIMEOUT_SECONDS: Optional[int] = None
