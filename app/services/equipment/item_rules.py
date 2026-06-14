"""Derive AC, attacks, and attunement from equipped SRD items."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.models import Item, PlayerEquipment
from app.services.character_creation.dnd5e_items import combat_item_snapshot
from app.services.equipment.slots import ALL_EQUIPMENT_SLOTS, normalize_slot, resolve_equip_slot

MAX_ATTUNED_ITEMS = 3


def get_equipped_items(player) -> list[tuple[str, Item]]:
    """Return (slot, Item) pairs for equipped gear."""
    rows = (
        PlayerEquipment.query.filter_by(player_id=player.id)
        .filter(PlayerEquipment.item_id.isnot(None))
        .all()
    )
    out: list[tuple[str, Item]] = []
    for row in rows:
        slot = normalize_slot(row.slot) or row.slot
        if row.item is None:
            continue
        out.append((slot, row.item))
    return out


def count_attuned_items(equipped: Iterable[tuple[str, Item]]) -> int:
    total = 0
    for _slot, item in equipped:
        stats = item.stats if isinstance(item.stats, dict) else {}
        if stats.get("requires_attunement"):
            total += 1
    return total


def pick_equip_slot(player, item: Item, *, requested_slot: str | None = None) -> Optional[str]:
    """Resolve canonical slot for equipping, including ring fallback."""
    stats = item.stats if isinstance(item.stats, dict) else {}
    if requested_slot:
        slot = normalize_slot(requested_slot)
        if slot and slot in ALL_EQUIPMENT_SLOTS:
            return slot
    primary = resolve_equip_slot(stats, item.type or "")
    allowed = stats.get("equip_slots")
    if isinstance(allowed, list) and allowed:
        candidates = [normalize_slot(str(s)) for s in allowed]
        candidates = [c for c in candidates if c]
    else:
        candidates = [primary] if primary else []
    if not candidates:
        return None
    occupied = {
        normalize_slot(row.slot) or row.slot
        for row in PlayerEquipment.query.filter_by(player_id=player.id).all()
        if row.item_id is not None
    }
    for slot in candidates:
        if slot not in occupied:
            return slot
    if primary in {"ring_1", "ring_2"}:
        for ring_slot in ("ring_1", "ring_2"):
            if ring_slot not in occupied:
                return ring_slot
    return candidates[0]


def validate_attunement(player, item: Item, *, replacing_item_id: int | None = None) -> str | None:
    """Return error message when attunement limit would be exceeded."""
    stats = item.stats if isinstance(item.stats, dict) else {}
    if not stats.get("requires_attunement"):
        return None
    equipped = get_equipped_items(player)
    attuned = count_attuned_items(equipped)
    already_attuned = any(
        it.item_id == item.item_id and (it.stats or {}).get("requires_attunement")
        for _slot, it in equipped
    )
    if already_attuned or replacing_item_id == item.item_id:
        return None
    if attuned >= MAX_ATTUNED_ITEMS:
        return f"Attunement limit reached ({MAX_ATTUNED_ITEMS} items)."
    return None


def compute_equipment_ac(
    equipped: Iterable[tuple[str, Item]],
    *,
    dex_mod: int,
    base_ac: int = 10,
) -> int:
    """Compute AC from armor/shield/ring bonuses on top of Dex-only base."""
    armor_ac: int | None = None
    dex_cap: int | None = None
    shield_bonus = 0
    misc_bonus = 0

    for slot, item in equipped:
        snap = combat_item_snapshot(item)
        if snap.get("ac_base") is not None and slot in {"torso", "body"}:
            armor_ac = int(snap["ac_base"])
            cap = snap.get("dex_cap")
            dex_cap = int(cap) if cap is not None else None
        if snap.get("is_shield") or slot == "off_hand" and snap.get("ac_bonus"):
            shield_bonus += int(snap.get("ac_bonus") or 0)
        misc_bonus += int(snap.get("ac_bonus") or 0) if slot in {"ring_1", "ring_2", "cloak", "wondrous"} else 0

    if armor_ac is not None:
        dex_add = dex_mod
        if dex_cap is not None:
            dex_add = min(dex_mod, dex_cap)
        return max(1, armor_ac + max(0, dex_add) + shield_bonus + misc_bonus)

    return max(1, base_ac + dex_mod + shield_bonus + misc_bonus)


def build_weapon_attacks(
    equipped: Iterable[tuple[str, Item]],
    *,
    str_mod: int,
    dex_mod: int,
    prof_bonus: int,
) -> list[dict[str, Any]]:
    attacks: list[dict[str, Any]] = []
    for slot, item in equipped:
        if slot not in {"main_hand", "off_hand", "weapon"}:
            continue
        snap = combat_item_snapshot(item)
        if not snap.get("damage_dice"):
            continue
        props = {str(p).lower() for p in (snap.get("properties") or [])}
        use_dex = "finesse" in props or item.type == "Ranged"
        ability_mod = dex_mod if use_dex else str_mod
        magic = int(snap.get("magic_bonus") or 0)
        range_ft = int(snap.get("range_ft") or 5)
        kind = "ranged" if item.type == "Ranged" or range_ft > 10 else "melee"
        attacks.append(
            {
                "key": snap.get("key") or f"item_{item.item_id}",
                "name": snap.get("name") or item.name,
                "kind": kind,
                "attack_mod": ability_mod + prof_bonus + magic,
                "damage": f"{snap['damage_dice']}+{max(0, ability_mod + magic)}",
                "damage_type": snap.get("damage_type") or "bludgeoning",
                "range_ft": range_ft,
                "source_item_id": item.item_id,
                "automation": snap.get("automation", "manual"),
            }
        )
    return attacks


def combat_equipment_snapshots(player) -> dict[str, Any]:
    equipped = get_equipped_items(player)
    items = [combat_item_snapshot(item) for _slot, item in equipped]
    return {
        "items": items,
        "attuned_count": count_attuned_items(equipped),
        "slots": {slot: combat_item_snapshot(item) for slot, item in equipped},
    }


def equipment_slots_payload(player) -> list[dict[str, Any]]:
    """Build player-safe equipment slot list for character views."""
    by_slot = {slot: None for slot in ALL_EQUIPMENT_SLOTS}
    for slot, item in get_equipped_items(player):
        canonical = normalize_slot(slot) or slot
        by_slot[canonical] = {
            "id": item.item_id,
            "name": item.name,
            "rarity": item.rarity,
            "description_short": (item.description or "")[:120],
            "type": item.type,
        }
    return [
        {"slot_name": slot, "item": by_slot[slot]}
        for slot in ALL_EQUIPMENT_SLOTS
        if by_slot[slot] is not None
    ]
