"""D&D 5e equipment slot definitions aligned with Player_Home body model."""

from __future__ import annotations

from typing import Any, Optional

# Canonical slots used by PlayerEquipment and Player_Home SVG body model.
ALL_EQUIPMENT_SLOTS: tuple[str, ...] = (
    "head",
    "neck",
    "torso",
    "body",
    "cloak",
    "main_hand",
    "off_hand",
    "hands",
    "waist",
    "legs",
    "feet",
    "ring_1",
    "ring_2",
    "wondrous",
    "ammo",
)

# Legacy three-slot names map to canonical slots for backward compatibility.
LEGACY_SLOT_MAP: dict[str, str] = {
    "weapon": "main_hand",
    "armor": "torso",
    "accessory": "wondrous",
}


def normalize_slot(slot: str | None) -> Optional[str]:
    """Return canonical slot name or None if invalid."""
    raw = str(slot or "").strip().lower()
    if not raw:
        return None
    if raw in LEGACY_SLOT_MAP:
        return LEGACY_SLOT_MAP[raw]
    if raw in ALL_EQUIPMENT_SLOTS:
        return raw
    return None


def resolve_equip_slot(item_stats: dict[str, Any] | None, item_type: str = "") -> str:
    """Pick the primary equip slot from item stats or type heuristics."""
    stats = item_stats if isinstance(item_stats, dict) else {}
    explicit = stats.get("equip_slot") or stats.get("primary_slot")
    if explicit:
        normalized = normalize_slot(str(explicit))
        if normalized:
            return normalized
    slots = stats.get("equip_slots")
    if isinstance(slots, list) and slots:
        normalized = normalize_slot(str(slots[0]))
        if normalized:
            return normalized
    category = str(stats.get("category") or stats.get("subcategory") or "").lower()
    t = (item_type or "").strip().lower()
    combined = f"{category} {t}"
    if "shield" in combined:
        return "off_hand"
    if any(k in combined for k in ("ring", "finger")):
        return "ring_1"
    if any(k in combined for k in ("head", "helm", "hat", "circlet")):
        return "head"
    if any(k in combined for k in ("neck", "amulet", "pendant")):
        return "neck"
    if any(k in combined for k in ("cloak", "cape", "mantle")):
        return "cloak"
    if any(k in combined for k in ("boot", "foot", "shoe")):
        return "feet"
    if any(k in combined for k in ("glove", "gauntlet", "hand")):
        return "hands"
    if any(k in combined for k in ("belt", "girdle", "waist")):
        return "waist"
    if any(k in combined for k in ("ranged", "bow", "crossbow", "firearm", "sling")):
        return "main_hand"
    if any(k in combined for k in ("weapon", "sword", "axe", "staff", "dagger", "spear", "martial", "melee")):
        return "main_hand"
    if any(k in combined for k in ("armor", "armour", "plate", "mail", "leather", "shield")):
        return "torso"
    if "ammo" in combined or "arrow" in combined or "bolt" in combined:
        return "ammo"
    return "wondrous"
