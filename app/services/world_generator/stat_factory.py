"""Build system-specific stat blocks stored on `Item.stats` (JSONB).

Gates:
- Firearms (Ranged + modern nouns) unlock at axis >= FIREARM_MIN_AXIS (6).
- Magic +N bonuses unlock at axis <= MAGIC_BONUS_MAX_AXIS (4).

Phase 1 keeps cursed_unique_frequency fixed (see `defaults`).
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.world_generator.defaults import (
    FIREARM_MIN_AXIS,
    MAGIC_BONUS_MAX_AXIS,
)


def _magic_bonus(rng, axis_position: int, rarity: str) -> int:
    """Return a +N magic bonus for weapons/armor. 0 if not magic-era."""
    if axis_position > MAGIC_BONUS_MAX_AXIS:
        return 0
    ceiling = {"Common": 0, "Uncommon": 1, "Rare": 2, "Legendary": 3}.get(rarity, 0)
    if axis_position <= 1:  # God Magic
        ceiling = min(4, ceiling + 1)
    return rng.randint(0, ceiling)


def _avg_damage(rng, category: str, rarity: str) -> float:
    base = {"Melee": 4.0, "Ranged": 5.0}.get(category, 0.0)
    bonus = {"Common": 0, "Uncommon": 1, "Rare": 2, "Legendary": 3}.get(rarity, 0)
    return base + rng.uniform(0, 1.5) + bonus


def _dnd5e_stats(rng, category, rarity, axis_position, is_cursed) -> Dict[str, Any]:
    if category == "Armor":
        ac = rng.randint(11, 18)
        magic = _magic_bonus(rng, axis_position, rarity)
        return {
            "ac": ac + magic,
            "type": "Medium",
            "weight": rng.randint(10, 50),
            "stealth_disadvantage": ac >= 16,
            "magic_bonus": magic,
            "cursed": is_cursed,
        }
    if category in {"Melee", "Ranged"}:
        magic = _magic_bonus(rng, axis_position, rarity)
        avg_dmg = _avg_damage(rng, category, rarity)
        stats: Dict[str, Any] = {
            "avg_dmg": round(avg_dmg, 2),
            "damage": f"1d{rng.choice([6, 8, 10])}",
            "to_hit_bonus": magic,
            "magic_bonus": magic,
            "cursed": is_cursed,
        }
        if category == "Ranged":
            stats["is_firearm"] = axis_position >= FIREARM_MIN_AXIS
            stats["range"] = "30/120" if stats["is_firearm"] else "80/320"
        return stats
    # General / Consumable
    return {"weight": rng.uniform(0.1, 5.0), "cursed": is_cursed}


def _pf2e_stats(rng, category, rarity, axis_position, is_cursed) -> Dict[str, Any]:
    if category == "Armor":
        magic = _magic_bonus(rng, axis_position, rarity)
        return {
            "ac_bonus": rng.randint(1, 5) + magic,
            "dex_cap": rng.choice([0, 1, 2, 3]),
            "check_penalty": -rng.randint(0, 3),
            "bulk": rng.randint(1, 4),
            "magic_bonus": magic,
            "cursed": is_cursed,
        }
    if category in {"Melee", "Ranged"}:
        magic = _magic_bonus(rng, axis_position, rarity)
        avg_dmg = _avg_damage(rng, category, rarity)
        stats: Dict[str, Any] = {
            "avg_dmg": round(avg_dmg, 2),
            "attack_mod": magic,
            "bulk": rng.choice([0.1, 1, 2]),
            "magic_bonus": magic,
            "cursed": is_cursed,
        }
        if category == "Ranged":
            stats["is_firearm"] = axis_position >= FIREARM_MIN_AXIS
        return stats
    return {"bulk": rng.choice([0.1, 1]), "cursed": is_cursed}


def _generic_stats(rng, category, rarity, axis_position, is_cursed) -> Dict[str, Any]:
    magic = _magic_bonus(rng, axis_position, rarity)
    return {
        "power": rng.randint(1, 10) + magic,
        "magic_bonus": magic,
        "cursed": is_cursed,
    }


_SYSTEM_DISPATCH = {
    "dnd5e":   _dnd5e_stats,
    "pf2e":    _pf2e_stats,
    "generic": _generic_stats,
}


def build_item_stats(
    rng,
    system_type: str,
    category: str,
    rarity: str,
    axis_position: int,
    is_cursed: bool,
) -> Dict[str, Any]:
    """Return a stats_json dict shaped for the GM's chosen rule system."""
    fn = _SYSTEM_DISPATCH.get(system_type, _generic_stats)
    stats = fn(rng, category, rarity, axis_position, is_cursed)
    stats["axis_position"] = int(axis_position)
    stats["rarity"] = rarity
    stats["category"] = category
    return stats
