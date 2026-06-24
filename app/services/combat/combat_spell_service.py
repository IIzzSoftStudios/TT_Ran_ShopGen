"""Combat spell list resolution, slot snapshots, and SRD area targeting."""

from __future__ import annotations

from typing import Any

from app.models import BattleCombatant, BattleEncounter
from app.services.combat import dnd5e_combat_profile as combat_profile
from app.services.combat import dnd5e_rules as rules
from app.services.character_creation.progression_helpers import resolve_spell_slots_from_row
from app.services.rulesets import get_ruleset
from app.services.spells_compendium_service import combat_spell_snapshots

_KNOWN_CASTERS = frozenset({"known", "pact"})


def spellcasting_ability_key(class_entry: dict[str, Any] | None) -> str:
    ability = "int"
    if isinstance(class_entry, dict):
        ability = str((class_entry.get("spellcasting") or {}).get("ability") or "int").lower()
    if ability not in ("str", "dex", "con", "int", "wis", "cha"):
        return "int"
    return ability


def spell_attack_modifier(
    abilities: dict[str, Any] | None,
    class_entry: dict[str, Any] | None,
    *,
    level: int = 1,
) -> int:
    """Spell attack bonus and save DC use the class spellcasting ability (SRD)."""
    abilities = abilities if isinstance(abilities, dict) else {}
    ruleset = get_ruleset("dnd5e")
    prof = ruleset.proficiency_bonus(max(1, int(level or 1)))
    mod = ruleset.compute_ability_mod(abilities.get(spellcasting_ability_key(class_entry), 10))
    return mod + prof


def combat_spell_keys_with_buckets(
    sheet: dict[str, Any],
    class_entry: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """Return (spell_key, bucket) pairs available in combat — cantrips + prepared or known."""
    spells_state = sheet.get("spells") if isinstance(sheet.get("spells"), dict) else {}
    spellcasting = (class_entry or {}).get("spellcasting") if isinstance(class_entry, dict) else {}
    if not isinstance(spellcasting, dict):
        spellcasting = {}
    sc_type = str(spellcasting.get("type") or "none")
    cantrips = [
        str(raw).strip().lower()
        for raw in (spells_state.get("cantrips") or [])
        if str(raw or "").strip()
    ]
    if sc_type in _KNOWN_CASTERS:
        leveled = [
            str(raw).strip().lower()
            for raw in (spells_state.get("known") or [])
            if str(raw or "").strip()
        ]
        bucket = "known"
    else:
        leveled = [
            str(raw).strip().lower()
            for raw in (spells_state.get("prepared") or [])
            if str(raw or "").strip()
        ]
        bucket = "prepared"
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for key in cantrips:
        if key not in seen:
            seen.add(key)
            out.append((key, "cantrip"))
    for key in leveled:
        if key not in seen:
            seen.add(key)
            out.append((key, bucket))
    return out


def build_player_spell_snapshots(
    campaign_id: int,
    sheet: dict[str, Any],
    class_entry: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    keyed = combat_spell_keys_with_buckets(sheet, class_entry)
    if not keyed:
        return []
    bucket_by_key = {key: bucket for key, bucket in keyed}
    snapshots = combat_spell_snapshots(campaign_id, [key for key, _ in keyed])
    for snap in snapshots:
        snap["spell_bucket"] = bucket_by_key.get(str(snap.get("key") or "").lower(), "prepared")
    snapshots.sort(key=lambda row: (int(row.get("level") or 0), str(row.get("name") or "")))
    return snapshots


def build_spell_slots_snapshot(
    sheet: dict[str, Any],
    class_row: dict[str, Any] | None,
) -> dict[str, dict[str, int]]:
    """Remaining spell slots from sheet progression minus slots_used."""
    stored = sheet.get("spell_slots") if isinstance(sheet.get("spell_slots"), dict) else None
    slot_map = stored if stored else resolve_spell_slots_from_row(class_row or {})
    spells_state = sheet.get("spells") if isinstance(sheet.get("spells"), dict) else {}
    used = spells_state.get("slots_used") if isinstance(spells_state.get("slots_used"), dict) else {}
    snapshot: dict[str, dict[str, int]] = {}
    for key, total in (slot_map or {}).items():
        try:
            slot_total = int(total)
        except (TypeError, ValueError):
            continue
        if slot_total <= 0:
            continue
        try:
            consumed = int(used.get(str(key)) or 0)
        except (TypeError, ValueError):
            consumed = 0
        remaining = max(0, slot_total - consumed)
        snapshot[str(key)] = {"total": slot_total, "remaining": remaining}
    return snapshot


def is_area_damage_spell(spell: dict[str, Any]) -> bool:
    area = spell.get("area") if isinstance(spell.get("area"), dict) else {}
    if not area.get("shape"):
        return False
    if spell.get("conditions"):
        return False
    if str(spell.get("attack_type") or "") != "save":
        return False
    return bool(spell.get("damage"))


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _line_cells_limited(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    max_cells: int,
) -> set[tuple[int, int]]:
    cells = combat_profile._line_cells(x0, y0, x1, y1)
    if len(cells) > max_cells:
        cells = cells[:max_cells]
    return set(cells)


def combatants_in_spell_area(
    encounter: BattleEncounter,
    caster: BattleCombatant,
    anchor: BattleCombatant,
    spell: dict[str, Any],
    *,
    diagonal_mode: str,
) -> list[BattleCombatant]:
    """Return active combatants affected by an area spell (SRD 5ft grid approximation)."""
    area = spell.get("area") if isinstance(spell.get("area"), dict) else {}
    shape = str(area.get("shape") or "").strip().lower()
    try:
        size_ft = int(area.get("size_ft") or 0)
    except (TypeError, ValueError):
        size_ft = 0
    if not shape or size_ft <= 0:
        return [anchor] if anchor.status == "active" else []

    from app.models import BattleCombatant as BC

    candidates = [
        c
        for c in BC.query.filter_by(encounter_id=encounter.id).all()
        if c.status == "active"
    ]

    cx, cy = int(caster.x), int(caster.y)
    ax, ay = int(anchor.x), int(anchor.y)
    affected: list[BattleCombatant] = []

    if shape == "sphere":
        for combatant in candidates:
            if rules.grid_distance_ft(ax, ay, combatant.x, combatant.y, diagonal_mode) <= size_ft:
                affected.append(combatant)
        return affected

    if shape == "cube":
        range_text = str(spell.get("range_text") or "").lower()
        origin_x, origin_y = (cx, cy) if "self" in range_text else (ax, ay)
        radius_cells = max(1, (size_ft + rules.GRID_CELL_FT - 1) // rules.GRID_CELL_FT)
        for combatant in candidates:
            if max(abs(combatant.x - origin_x), abs(combatant.y - origin_y)) <= radius_cells:
                affected.append(combatant)
        return affected

    if shape == "line":
        max_cells = max(1, (size_ft + rules.GRID_CELL_FT - 1) // rules.GRID_CELL_FT)
        line_cells = _line_cells_limited(cx, cy, ax, ay, max_cells=max_cells)
        for combatant in candidates:
            if (combatant.x, combatant.y) in line_cells:
                affected.append(combatant)
        return affected

    if shape == "cone":
        dx, dy = _sign(ax - cx), _sign(ay - cy)
        if dx == 0 and dy == 0:
            dx = 1
        for combatant in candidates:
            tx, ty = int(combatant.x), int(combatant.y)
            dist = rules.grid_distance_ft(cx, cy, tx, ty, diagonal_mode)
            if dist <= 0 or dist > size_ft:
                continue
            vx, vy = tx - cx, ty - cy
            if (vx * dx + vy * dy) > 0:
                affected.append(combatant)
        return affected

    return [anchor] if anchor.status == "active" else []
