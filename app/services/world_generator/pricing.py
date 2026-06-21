"""SHARED pricing module used by both the world generator (at generation
time, to precompute `Item.base_price`) and the simulation engine (at
runtime, to update `ShopInventory.dynamic_price`).

Keeping this in one file means there is no risk of the generator baking
prices with one formula and the simulation drifting to another.

Public API:

- `compute_base_price(category, rarity, stats, wealth_multiplier=1.0)` ->
  int, the canonical base price stamped onto `Item.base_price`.
- `dynamic_price_arithmetic(base_price, region_mult, axis_distance_mult)`
  -> float, the cheap arithmetic used by the generator while filling
  `ShopInventory` rows. No DB lookups, no RNG.

The "general_goods" path (rope, rations, torches) bypasses the
utility-score formula: their price is driven by volatility +
connectivity rather than equipment math.
"""

from __future__ import annotations

from typing import Any, Dict

# Rarity multiplier -- this is the "scarcity scalar" described in the plan.
RARITY_MULTIPLIER: Dict[str, float] = {
    "Common":    1.0,
    "Uncommon":  2.0,
    "Rare":      5.0,
    "Legendary": 50.0,
}

# Simulation ``calculate_dynamic_price`` expects a small integer scalar (not
# the string label and not the price multiplier above).
RARITY_SIMULATION_SCALAR: Dict[str, int] = {
    "common": 1,
    "uncommon": 2,
    "rare": 3,
    "legendary": 4,
}


def rarity_for_simulation(rarity_label: Any) -> int:
    """Map item rarity labels to the integer scalar used in tick pricing."""
    if rarity_label is None:
        return 3
    text = str(rarity_label).strip()
    if text.isdigit():
        return max(1, min(10, int(text)))
    key = text.lower()
    if key in RARITY_SIMULATION_SCALAR:
        return RARITY_SIMULATION_SCALAR[key]
    for label, scalar in RARITY_SIMULATION_SCALAR.items():
        if label in key:
            return scalar
    title = text.title()
    if title in RARITY_MULTIPLIER:
        return max(1, min(10, int(RARITY_MULTIPLIER[title])))
    return 3

# Base "utility floor" by category when stats are missing/minimal.
CATEGORY_BASELINE: Dict[str, float] = {
    "Melee":      5.0,
    "Ranged":     7.0,
    "Armor":      6.0,
    "Consumable": 2.0,
    "General":    1.0,
}

# Categories routed through the general-goods path (no utility scaling).
GENERAL_GOODS_CATEGORIES = {"General", "Consumable"}


def compute_utility_score(category: str, stats: Dict[str, Any]) -> float:
    """Return a numeric "power" score for an item.

    The exact numbers are less important than the *ordering*: higher-AC
    armor should always out-price lower-AC armor of the same rarity.
    """
    baseline = CATEGORY_BASELINE.get(category, 1.0)

    if category == "Armor":
        # D&D 5e: stats['ac']. PF2E: stats['ac_bonus'].
        ac = stats.get("ac")
        if ac is not None:
            return baseline + max(0.0, float(ac) - 10.0) ** 1.5
        ac_bonus = stats.get("ac_bonus")
        if ac_bonus is not None:
            return baseline + float(ac_bonus) * 3.0
        return baseline

    if category == "Melee":
        avg_dmg = float(stats.get("avg_dmg", 3.0))
        magic_bonus = float(stats.get("magic_bonus", 0))
        return baseline + avg_dmg + magic_bonus * 8.0

    if category == "Ranged":
        avg_dmg = float(stats.get("avg_dmg", 4.0))
        magic_bonus = float(stats.get("magic_bonus", 0))
        return baseline + avg_dmg + magic_bonus * 8.0

    return baseline


def compute_base_price(
    category: str,
    rarity: str,
    stats: Dict[str, Any],
    wealth_multiplier: float = 1.0,
) -> int:
    """Precomputed once per item at generation time.

    Formula: `utility * rarity * wealth`, rounded up to the nearest int.
    """
    if category in GENERAL_GOODS_CATEGORIES:
        base = CATEGORY_BASELINE[category]
    else:
        base = compute_utility_score(category, stats)

    rarity_mult = RARITY_MULTIPLIER.get(rarity, 1.0)
    price = base * rarity_mult * max(wealth_multiplier, 0.1)
    return max(1, int(round(price)))


def dynamic_price_arithmetic(
    base_price: int,
    region_mult: float = 1.0,
    axis_distance_mult: float = 1.0,
) -> float:
    """Cheap arithmetic used by the generator when creating ShopInventory.

    Both multipliers default to 1.0 so callers can omit either one.
    Never returns a non-positive price.
    """
    price = float(base_price) * float(region_mult) * float(axis_distance_mult)
    return max(0.01, price)


def gravity_well_blend(local_price: float, regional_avg: float, connectivity: int) -> float:
    """`lerp(local, regional_avg, connectivity / 10)`.

    Phase 2 helper — the intensity dials aren't exposed yet, but the
    simulation engine can call this unchanged when they are.
    """
    t = max(0.0, min(1.0, float(connectivity) / 10.0))
    return local_price * (1.0 - t) + regional_avg * t
