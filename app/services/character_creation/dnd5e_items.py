"""D&D 5e SRD 5.1 item seed catalog (CC-BY-4.0 mechanical shells)."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app.services.character_creation.srd_item_manifest import SRD_ITEMS_BY_CATEGORY

_MAX_SUMMARY = 300
_LORE_DENY = re.compile(
    r"\b(vecna|blackrazor|whelm|wave|kwalish|bigby|melf|mordenkainen|nystul|"
    r"otiluke|leomund|drawmij|otto|tasha|tenser|evard)\b",
    re.I,
)
_RENAME = {"Apparatus of Kwalish": "Apparatus of the Crab"}

_ITEM_OVERRIDES: dict[str, dict[str, Any]] = {
    "longsword": {
        "type": "Melee", "rarity": "Common", "base_price_copper": 1500,
        "damage": "1d8", "range": "5 ft.",
        "type_data": {"category": "martial_weapon", "damage_dice": "1d8", "damage_type": "slashing",
                      "properties": ["versatile"], "versatile_damage": "1d10", "range_ft": 5, "weapon_category": "martial"},
        "equip_slot": "main_hand", "summary": "Martial melee weapon, 1d8 slashing, versatile (1d10).", "automation": "auto",
    },
    "shortsword": {
        "type": "Melee", "rarity": "Common", "base_price_copper": 1000,
        "damage": "1d6", "range": "5 ft.",
        "type_data": {"category": "martial_weapon", "damage_dice": "1d6", "damage_type": "piercing",
                      "properties": ["finesse", "light"], "range_ft": 5, "weapon_category": "martial"},
        "equip_slot": "main_hand", "summary": "Martial finesse/light melee weapon, 1d6 piercing.", "automation": "auto",
    },
    "longbow": {
        "type": "Ranged", "rarity": "Common", "base_price_copper": 5000,
        "damage": "1d8", "range": "150/600",
        "type_data": {"category": "martial_weapon", "damage_dice": "1d8", "damage_type": "piercing",
                      "properties": ["ammunition", "heavy", "two_handed"], "range_ft": 150, "long_range_ft": 600, "weapon_category": "martial"},
        "equip_slot": "main_hand", "summary": "Martial ranged weapon, 1d8 piercing, range 150/600.", "automation": "auto",
    },
    "dagger": {
        "type": "Melee", "rarity": "Common", "base_price_copper": 200,
        "damage": "1d4", "range": "20/60",
        "type_data": {"category": "simple_weapon", "damage_dice": "1d4", "damage_type": "piercing",
                      "properties": ["finesse", "light", "thrown"], "range_ft": 20, "long_range_ft": 60, "weapon_category": "simple"},
        "equip_slot": "main_hand", "summary": "Simple finesse/light/thrown weapon, 1d4 piercing.", "automation": "auto",
    },
    "leather_armor": {
        "type": "Armor", "rarity": "Common", "base_price_copper": 1000,
        "type_data": {"category": "light_armor", "ac_base": 11, "dex_cap": None, "stealth_disadvantage": False, "strength_requirement": 0},
        "equip_slot": "torso", "summary": "Light armor, AC 11 + Dex modifier.", "automation": "auto",
    },
    "chain_mail": {
        "type": "Armor", "rarity": "Common", "base_price_copper": 7500, "min_str": "13",
        "type_data": {"category": "heavy_armor", "ac_base": 16, "dex_cap": 0, "stealth_disadvantage": True, "strength_requirement": 13},
        "equip_slot": "torso", "summary": "Heavy armor, AC 16, Str 13, stealth disadvantage.", "automation": "auto",
    },
    "plate_armor": {
        "type": "Armor", "rarity": "Common", "base_price_copper": 150000, "min_str": "15",
        "type_data": {"category": "heavy_armor", "ac_base": 18, "dex_cap": 0, "stealth_disadvantage": True, "strength_requirement": 15},
        "equip_slot": "torso", "summary": "Heavy armor, AC 18, Str 15, stealth disadvantage.", "automation": "auto",
    },
    "shield": {
        "type": "Armor", "rarity": "Common", "base_price_copper": 1000,
        "type_data": {"category": "shield", "ac_bonus": 2, "is_shield": True},
        "equip_slot": "off_hand", "summary": "Shield grants +2 AC while equipped.", "automation": "auto",
    },
    "bag_of_holding": {
        "type": "General", "rarity": "Uncommon", "base_price_copper": 0,
        "type_data": {"category": "wondrous_magic", "effect_tags": ["extradimensional"]},
        "equip_slot": "wondrous", "summary": "Extradimensional bag holds far more than its size suggests.", "automation": "manual",
    },
    "deck_of_many_things": {
        "type": "General", "rarity": "Legendary", "base_price_copper": 0,
        "type_data": {"category": "wondrous_magic", "effect_tags": ["random_effects", "cards"]},
        "equip_slot": "wondrous", "summary": "Deck of cards that produces powerful random effects when drawn.", "automation": "manual",
    },
    "sun_blade": {
        "type": "Melee", "rarity": "Rare", "base_price_copper": 0, "damage": "1d8", "requires_attunement": True,
        "type_data": {"category": "wondrous_magic", "damage_dice": "1d8", "damage_type": "radiant", "magic_bonus": 2, "properties": ["finesse"], "range_ft": 5},
        "equip_slot": "main_hand", "summary": "Attuned radiant blade with finesse and bonus radiant damage.", "automation": "auto",
    },
    "weapon_1": {
        "type": "Melee", "rarity": "Uncommon", "base_price_copper": 0, "damage": "1d8",
        "type_data": {"category": "wondrous_magic", "magic_bonus": 1, "template": "magic_weapon"},
        "equip_slot": "main_hand", "summary": "Magic weapon grants +1 to attack and damage rolls.", "automation": "auto",
    },
    "ring_of_protection": {
        "type": "General", "rarity": "Rare", "base_price_copper": 0, "requires_attunement": True,
        "type_data": {"category": "wondrous_magic", "ac_bonus": 1, "save_bonus": 1, "effect_tags": ["protection"]},
        "equip_slots": ["ring_1", "ring_2"], "equip_slot": "ring_1",
        "summary": "Attuned ring grants +1 AC and saving throws.", "automation": "auto",
    },
    "potion_of_healing": {
        "type": "Consumable", "rarity": "Common", "base_price_copper": 5000,
        "type_data": {"category": "adventuring_gear", "consumable": True, "healing": "2d4+2"},
        "equip_slot": "wondrous", "summary": "Drinking restores 2d4+2 hit points.", "automation": "auto",
    },
}

_CATEGORY_DEFAULTS: dict[str, dict[str, Any]] = {
    "simple_weapon": {"type": "Melee", "rarity": "Common", "base_price_copper": 100, "equip_slot": "main_hand", "automation": "auto"},
    "martial_weapon": {"type": "Melee", "rarity": "Common", "base_price_copper": 500, "equip_slot": "main_hand", "automation": "auto"},
    "light_armor": {"type": "Armor", "rarity": "Common", "base_price_copper": 500, "equip_slot": "torso", "automation": "auto"},
    "medium_armor": {"type": "Armor", "rarity": "Common", "base_price_copper": 5000, "equip_slot": "torso", "automation": "auto"},
    "heavy_armor": {"type": "Armor", "rarity": "Common", "base_price_copper": 10000, "equip_slot": "torso", "automation": "auto"},
    "shield": {"type": "Armor", "rarity": "Common", "base_price_copper": 1000, "equip_slot": "off_hand", "automation": "auto"},
    "adventuring_gear": {"type": "General", "rarity": "Common", "base_price_copper": 50, "equip_slot": "wondrous", "automation": "manual"},
    "tool": {"type": "General", "rarity": "Common", "base_price_copper": 2500, "equip_slot": "wondrous", "automation": "manual"},
    "mount_vehicle": {"type": "General", "rarity": "Common", "base_price_copper": 7500, "equip_slot": "wondrous", "automation": "manual"},
    "wondrous_magic": {"type": "General", "rarity": "Uncommon", "base_price_copper": 0, "equip_slot": "wondrous", "requires_attunement": False, "automation": "manual"},
}


def item_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")
    return slug[:80] or "item"


def _clean_name(raw: str) -> str:
    name = _RENAME.get(raw, raw)
    if _LORE_DENY.search(name):
        raise ValueError(f"Product Identity item name: {name!r}")
    return name


def _default_shell(name: str, category: str) -> dict[str, Any]:
    defaults = deepcopy(_CATEGORY_DEFAULTS.get(category, _CATEGORY_DEFAULTS["adventuring_gear"]))
    key = item_slug(name)
    type_data: dict[str, Any] = {"category": category}
    if category.endswith("_weapon"):
        type_data.update({"damage_dice": "1d6", "damage_type": "bludgeoning", "properties": [], "range_ft": 5,
                          "weapon_category": "simple" if category == "simple_weapon" else "martial"})
    elif category in {"light_armor", "medium_armor", "heavy_armor"}:
        type_data.update({"ac_base": 11, "dex_cap": None, "stealth_disadvantage": False, "strength_requirement": 0})
    elif category == "shield":
        type_data.update({"ac_bonus": 2, "is_shield": True})
    elif category == "wondrous_magic":
        type_data["effect_tags"] = []
    return {
        "key": key, "origin_srd_key": key, "name": name, "category": category,
        "type": defaults["type"], "rarity": defaults["rarity"], "base_price_copper": defaults["base_price_copper"],
        "damage": type_data.get("damage_dice"), "range": None, "min_str": None,
        "requires_attunement": bool(defaults.get("requires_attunement")),
        "equip_slot": defaults["equip_slot"], "equip_slots": [defaults["equip_slot"]],
        "type_data": type_data, "effect_tags": type_data.get("effect_tags", []),
        "summary": f"SRD {category.replace('_', ' ')} item."[:_MAX_SUMMARY],
        "srd_reference": "SRD 5.1", "content_source": "srd_5_1", "automation": defaults.get("automation", "manual"),
    }


def build_core_item(name: str, category: str) -> dict[str, Any]:
    safe_name = _clean_name(name)
    shell = _default_shell(safe_name, category)
    override = deepcopy(_ITEM_OVERRIDES.get(shell["key"], {}))
    shell.update({k: v for k, v in override.items() if k != "type_data"})
    if override.get("equip_slots"):
        shell["equip_slots"] = list(override["equip_slots"])
    elif override.get("equip_slot"):
        shell["equip_slots"] = [override["equip_slot"]]
    type_data = deepcopy(shell.get("type_data") or {})
    if override.get("type_data"):
        type_data.update(override["type_data"])
    type_data["category"] = category
    shell["type_data"] = type_data
    if shell.get("damage") is None and type_data.get("damage_dice"):
        shell["damage"] = type_data["damage_dice"]
    shell["summary"] = str(shell.get("summary") or "")[:_MAX_SUMMARY]
    return shell


CORE_ITEMS: list[dict[str, Any]] = [
    build_core_item(name, category)
    for category, names in sorted(SRD_ITEMS_BY_CATEGORY.items())
    for name in names
]


def item_to_stats(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": entry.get("category"),
        "subcategory": (entry.get("type_data") or {}).get("category"),
        "equip_slot": entry.get("equip_slot"),
        "equip_slots": entry.get("equip_slots") or [],
        "requires_attunement": bool(entry.get("requires_attunement")),
        "type_data": deepcopy(entry.get("type_data") or {}),
        "effect_tags": list(entry.get("effect_tags") or []),
        "automation": entry.get("automation", "manual"),
        "summary": entry.get("summary", ""),
        "srd_reference": entry.get("srd_reference", "SRD 5.1"),
        "origin_srd_key": entry.get("origin_srd_key") or entry.get("key"),
        "gm_edited": False,
    }


def combat_item_snapshot(item: Any) -> dict[str, Any]:
    stats = getattr(item, "stats", None) or (item.get("stats") if isinstance(item, dict) else {}) or {}
    if not isinstance(stats, dict):
        stats = {}
    type_data = stats.get("type_data") if isinstance(stats.get("type_data"), dict) else {}
    name = getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else "Item")
    damage = getattr(item, "damage", None) or (item.get("damage") if isinstance(item, dict) else None)
    return {
        "key": stats.get("origin_srd_key") or item_slug(str(name)),
        "name": str(name),
        "category": stats.get("category"),
        "equip_slot": stats.get("equip_slot"),
        "automation": stats.get("automation", "manual"),
        "requires_attunement": bool(stats.get("requires_attunement")),
        "damage_dice": type_data.get("damage_dice") or damage,
        "damage_type": type_data.get("damage_type"),
        "magic_bonus": int(type_data.get("magic_bonus") or 0),
        "properties": list(type_data.get("properties") or []),
        "range_ft": type_data.get("range_ft"),
        "long_range_ft": type_data.get("long_range_ft"),
        "ac_base": type_data.get("ac_base"),
        "ac_bonus": type_data.get("ac_bonus"),
        "dex_cap": type_data.get("dex_cap"),
        "is_shield": bool(type_data.get("is_shield")),
        "effect_tags": list(stats.get("effect_tags") or []),
        "summary": str(stats.get("summary") or "")[:300],
    }
