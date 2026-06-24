"""SRD 5.1 combat profiles and mechanical effect resolution for encounters.

Pure functions plus small profile builders — no Flask or DB imports.
Species keys align with ``dnd5e_species.CORE_SPECIES``.
"""

from __future__ import annotations

import re
from random import Random
from typing import Any

from app.services.combat import dnd5e_rules as rules

DAMAGE_TYPES = frozenset(
    {
        "acid",
        "bludgeoning",
        "cold",
        "fire",
        "force",
        "lightning",
        "necrotic",
        "piercing",
        "poison",
        "psychic",
        "radiant",
        "slashing",
        "thunder",
    }
)

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")

# Mechanical SRD species profiles (machine keys — not rules text).
_SPECIES_PROFILES: dict[str, dict[str, Any]] = {
    "human": {"speed_ft": 30, "size": "medium"},
    "elf": {
        "speed_ft": 30,
        "size": "medium",
        "darkvision_ft": 60,
        "save_advantage_vs_conditions": ["charmed"],
    },
    "dwarf": {
        "speed_ft": 25,
        "size": "medium",
        "darkvision_ft": 60,
        "save_advantage_vs_conditions": ["poisoned"],
        "damage_resistances": ["poison"],
    },
    "halfling": {
        "speed_ft": 25,
        "size": "small",
        "lucky": True,
        "save_advantage_vs_conditions": ["frightened"],
    },
    "dragonborn": {
        "speed_ft": 30,
        "size": "medium",
        "damage_resistances": ["acid"],
    },
    "gnome": {
        "speed_ft": 25,
        "size": "small",
        "darkvision_ft": 60,
        "save_advantage_vs_magic": ["int", "wis", "cha"],
    },
    "half-elf": {
        "speed_ft": 30,
        "size": "medium",
        "darkvision_ft": 60,
        "save_advantage_vs_conditions": ["charmed"],
    },
    "half-orc": {
        "speed_ft": 30,
        "size": "medium",
        "darkvision_ft": 60,
        "savage_attacks": True,
        "relentless_endurance": True,
    },
    "tiefling": {
        "speed_ft": 30,
        "size": "medium",
        "darkvision_ft": 60,
        "damage_resistances": ["fire"],
    },
}

_SAVE_THROW_RE = re.compile(
    r"\b(str|dex|con|int|wis|cha)\s*\+?\s*(-?\d+)\b", re.IGNORECASE
)


def merge_combat_effects(base: dict[str, Any] | None, *layers: dict[str, Any]) -> dict[str, Any]:
    """Merge combat effect layers (traits, species, class, inline overrides)."""
    profile = dict(base or {"speed_ft": 30, "size": "medium"})
    list_keys = (
        "damage_resistances",
        "damage_immunities",
        "damage_vulnerabilities",
        "condition_immunities",
        "save_advantage_vs_conditions",
        "save_advantage_vs_magic",
    )
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        for key, value in layer.items():
            if key in list_keys and isinstance(value, list):
                merged = list(profile.get(key) or [])
                for item in value:
                    if item not in merged:
                        merged.append(item)
                profile[key] = merged
            elif key == "save_bonuses" and isinstance(value, dict):
                bonuses = dict(profile.get("save_bonuses") or {})
                bonuses.update({k: int(v) for k, v in value.items()})
                profile["save_bonuses"] = bonuses
            elif key == "darkvision_ft":
                profile[key] = max(int(profile.get(key) or 0), int(value or 0))
            elif key == "speed_ft":
                profile[key] = int(value)
            elif key == "speed_bonus_ft":
                profile[key] = int(profile.get(key) or 0) + int(value or 0)
            elif key == "unarmored_ac_add_ability" and str(value or "").lower() in ABILITIES:
                profile[key] = str(value).lower()
            elif key == "unarmored_defense":
                profile[key] = bool(value) or bool(profile.get(key))
            elif key == "unarmored_defense_allows_shield":
                profile[key] = bool(profile.get(key, True)) and bool(value)
            elif key == "extra_attacks_per_action":
                try:
                    count = int(value or 0)
                except (TypeError, ValueError):
                    continue
                if count >= 2:
                    profile[key] = max(int(profile.get(key) or 1), count)
            elif key == "action_surge":
                profile[key] = bool(value) or bool(profile.get(key))
            elif key == "action_surge_additional_actions":
                try:
                    count = int(value or 0)
                except (TypeError, ValueError):
                    continue
                if count >= 1:
                    profile[key] = max(int(profile.get(key) or 0), count)
            elif key in ("lucky", "savage_attacks", "relentless_endurance", "relentless_rage"):
                profile[key] = bool(value) or bool(profile.get(key))
            elif key == "reach_cells":
                profile[key] = max(int(profile.get(key) or 1), int(value or 1))
            else:
                profile[key] = value
    return profile


def parse_stat_modifiers_text(raw: str | None) -> dict[str, Any]:
    """Best-effort parse of GM free-text stat_modifiers into combat effects."""
    if not raw or not str(raw).strip():
        return {}
    text = str(raw).lower()
    effects: dict[str, Any] = {}
    speed = re.search(r"speed\s+(\d+)\s*ft", text)
    if speed:
        effects["speed_ft"] = int(speed.group(1))
    if "small size" in text or re.search(r"\bsmall\b", text):
        effects["size"] = "small"
    elif "large size" in text or re.search(r"\blarge\b", text):
        effects["size"] = "large"
    elif "medium size" in text or re.search(r"\bmedium\b", text):
        effects["size"] = "medium"
    dv = re.search(r"darkvision\s+(\d+)\s*ft", text)
    if dv:
        effects["darkvision_ft"] = int(dv.group(1))
    resist = []
    for dtype in DAMAGE_TYPES:
        if f"resist" in text and dtype in text:
            resist.append(dtype)
        if f"resistance to {dtype}" in text or f"{dtype} resistance" in text:
            resist.append(dtype)
    if resist:
        effects["damage_resistances"] = sorted(set(resist))
    if "advantage" in text and "charm" in text:
        effects["save_advantage_vs_conditions"] = ["charmed"]
    if "advantage" in text and "fright" in text:
        effects["save_advantage_vs_conditions"] = ["frightened"]
    if "advantage" in text and "poison" in text and "save" in text:
        effects["save_advantage_vs_conditions"] = ["poisoned"]
    if "lucky" in text:
        effects["lucky"] = True
    return effects


def species_profile(species_key: str | None) -> dict[str, Any]:
    key = str(species_key or "").strip().lower()
    base = dict(_SPECIES_PROFILES.get(key) or {"speed_ft": 30, "size": "medium"})
    base.setdefault("species_key", key or None)
    return base


def parse_damage_type_tags(raw: str | None) -> set[str]:
    if not raw or not str(raw).strip():
        return set()
    text = str(raw).lower()
    return {tag for tag in DAMAGE_TYPES if tag in text}


def parse_condition_immunities(raw: str | None) -> set[str]:
    if not raw or not str(raw).strip():
        return set()
    text = str(raw).lower()
    return {cond for cond in rules.CONDITIONS if cond in text}


def parse_monster_save_bonuses(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}
    found: dict[str, int] = {}
    for match in _SAVE_THROW_RE.finditer(str(raw)):
        ability = match.group(1).lower()
        found[ability] = int(match.group(2))
    return found


def monster_profile(stats: dict[str, Any]) -> dict[str, Any]:
    stats = stats or {}
    legendary = stats.get("legendary_actions") or []
    legendary_max = 3 if legendary else 0
    return {
        "speed_ft": max(0, int(stats.get("speed_ft") or 30)),
        "size": str(stats.get("size") or "medium").lower()[:20],
        "darkvision_ft": _parse_darkvision(stats.get("senses")),
        "damage_resistances": sorted(parse_damage_type_tags(stats.get("damage_resistances"))),
        "damage_immunities": sorted(parse_damage_type_tags(stats.get("damage_immunities"))),
        "damage_vulnerabilities": sorted(parse_damage_type_tags(stats.get("damage_vulnerabilities"))),
        "condition_immunities": sorted(parse_condition_immunities(stats.get("condition_immunities"))),
        "save_bonuses": parse_monster_save_bonuses(stats.get("saving_throws")),
        "legendary_points_max": legendary_max,
    }


def player_profile(
    sheet: dict[str, Any],
    *,
    species_key: str | None = None,
) -> dict[str, Any]:
    creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
    key = species_key or creation.get("species_key")
    profile = species_profile(str(key or ""))
    profile["save_prof_flags"] = dict(sheet.get("save_prof_flags") or {})
    try:
        profile["character_level"] = max(1, int(sheet.get("level") or 1))
    except (TypeError, ValueError):
        profile["character_level"] = 1
    ancestry = creation.get("dragonborn_ancestry")
    if str(key or "").lower() == "dragonborn" and ancestry:
        profile["damage_resistances"] = [str(ancestry).lower()]
    return profile


def _parse_darkvision(senses: str | None) -> int:
    if not senses:
        return 0
    match = re.search(r"darkvision\s+(\d+)\s*ft", str(senses), re.IGNORECASE)
    return int(match.group(1)) if match else 0


def profile_from_action_data(action_data: dict[str, Any] | None) -> dict[str, Any]:
    data = action_data or {}
    profile = dict(data.get("combat_profile") or {})
    if "save_prof_flags" not in profile and data.get("save_prof_flags"):
        profile["save_prof_flags"] = dict(data.get("save_prof_flags") or {})
    if "character_level" not in profile and data.get("character_level"):
        profile["character_level"] = int(data.get("character_level") or 1)
    return profile


def combine_roll_modes(*modes: str) -> str:
    active = [m for m in modes if m in ("advantage", "disadvantage")]
    if not active:
        return "normal"
    if "advantage" in active and "disadvantage" in active:
        return "normal"
    if "advantage" in active:
        return "advantage"
    return "disadvantage"


def _conditions(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(c).strip().lower() for c in raw if str(c).strip()]


def condition_attack_modifiers(
    attacker_conditions: list[str],
    target_conditions: list[str],
    *,
    attack_kind: str = "melee",
) -> tuple[str, str]:
    """Return (attacker_roll_mode_component, defender_roll_mode_component)."""
    atk = _conditions(attacker_conditions)
    tgt = _conditions(target_conditions)
    attacker_modes: list[str] = []
    defender_modes: list[str] = []
    ranged = str(attack_kind or "melee").lower() != "melee"

    if "blinded" in atk:
        attacker_modes.append("disadvantage")
    if "poisoned" in atk:
        attacker_modes.append("disadvantage")
    if "frightened" in atk:
        attacker_modes.append("disadvantage")
    if "restrained" in atk:
        attacker_modes.append("disadvantage")
    if "prone" in atk:
        attacker_modes.append("disadvantage")
    if "invisible" in atk:
        attacker_modes.append("advantage")

    if "blinded" in tgt:
        defender_modes.append("advantage")
    if "paralyzed" in tgt or "unconscious" in tgt:
        defender_modes.append("advantage")
    if "restrained" in tgt:
        defender_modes.append("advantage")
    if "stunned" in tgt:
        defender_modes.append("advantage")
    if "prone" in tgt:
        if ranged:
            defender_modes.append("disadvantage")
        else:
            defender_modes.append("advantage")
    if "invisible" in tgt:
        defender_modes.append("disadvantage")

    return (
        combine_roll_modes(*attacker_modes) if attacker_modes else "normal",
        combine_roll_modes(*defender_modes) if defender_modes else "normal",
    )


def condition_save_modifiers(
    defender_conditions: list[str],
    ability: str,
) -> str:
    conds = _conditions(defender_conditions)
    ability = str(ability or "dex").lower()
    modes: list[str] = []
    if "poisoned" in conds:
        modes.append("disadvantage")
    if "frightened" in conds:
        modes.append("disadvantage")
    if "restrained" in conds and ability == "dex":
        modes.append("disadvantage")
    if ability in ("str", "dex"):
        if "paralyzed" in conds or "stunned" in conds or "unconscious" in conds:
            return "auto_fail"
    return combine_roll_modes(*modes) if modes else "normal"


def save_advantage_for_profile(
    profile: dict[str, Any],
    *,
    ability: str,
    vs_condition: str | None = None,
    is_magic: bool = False,
) -> bool:
    ability = str(ability or "dex").lower()
    cond = str(vs_condition or "").strip().lower()
    if cond and cond in set(profile.get("save_advantage_vs_conditions") or []):
        return True
    if is_magic and ability in set(profile.get("save_advantage_vs_magic") or []):
        return True
    return False


def compute_save_modifier(
    ability_score: int,
    ability: str,
    profile: dict[str, Any],
    *,
    level: int = 1,
    save_prof_flags: dict[str, bool] | None = None,
) -> int:
    ability = str(ability or "dex").lower()
    monster_bonus = (profile.get("save_bonuses") or {}).get(ability)
    if monster_bonus is not None:
        return int(monster_bonus)
    mod = rules.ability_modifier(ability_score)
    flags = save_prof_flags if save_prof_flags is not None else profile.get("save_prof_flags") or {}
    if flags.get(ability):
        mod += rules.proficiency_bonus(level)
    return mod


def roll_d20_with_lucky(
    modifier: int,
    rng: Random,
    mode: str,
    profile: dict[str, Any],
    *,
    allow_lucky: bool = True,
) -> dict[str, Any]:
    result = rules.d20_roll(modifier, rng, mode)
    if (
        allow_lucky
        and profile.get("lucky")
        and result["natural"] == 1
        and mode == "normal"
    ):
        reroll = rules.d20_roll(modifier, rng, "normal")
        result = dict(reroll)
        result["lucky_reroll"] = True
        result["discarded_natural"] = 1
    return result


def apply_damage_modifiers(
    amount: int,
    damage_type: str | None,
    profile: dict[str, Any],
) -> dict[str, Any]:
    amount = max(0, int(amount))
    dtype = str(damage_type or "").strip().lower()
    resist = set(profile.get("damage_resistances") or [])
    immune = set(profile.get("damage_immunities") or [])
    vuln = set(profile.get("damage_vulnerabilities") or [])
    applied: list[str] = []
    total = amount
    if dtype and dtype in immune:
        applied.append("immune")
        total = 0
    elif dtype and dtype in resist:
        applied.append("resistance")
        total = amount // 2
    elif dtype and dtype in vuln:
        applied.append("vulnerability")
        total = amount * 2
    return {"total": total, "original": amount, "damage_type": dtype or None, "applied": applied}


def savage_attacks_extra_damage(
    damage_notation: str,
    rng: Random,
    *,
    enabled: bool,
    crit: bool,
    melee: bool,
) -> dict[str, Any] | None:
    if not enabled or not crit or not melee:
        return None
    try:
        return rules.roll_damage(damage_notation, rng, crit=False)
    except ValueError:
        return None


def _chebyshev_cells(ax: int, ay: int, bx: int, by: int) -> int:
    return max(abs(int(bx) - int(ax)), abs(int(by) - int(ay)))


def _line_cells(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        cells.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
    return cells


def cover_ac_bonus(
    ax: int,
    ay: int,
    tx: int,
    ty: int,
    blockers: list[tuple[int, int]],
) -> int:
    if not blockers:
        return 0
    line = _line_cells(ax, ay, tx, ty)
    if len(line) <= 2:
        return 0
    interior = set(line[1:-1])
    count = sum(1 for pos in blockers if pos in interior)
    if count >= 2:
        return 5
    if count == 1:
        return 2
    return 0


def is_flanking(
    attacker_x: int,
    attacker_y: int,
    target_x: int,
    target_y: int,
    ally_positions: list[tuple[int, int]],
    *,
    attack_kind: str = "melee",
) -> bool:
    if str(attack_kind or "melee").lower() != "melee":
        return False
    if _chebyshev_cells(attacker_x, attacker_y, target_x, target_y) > 1:
        return False
    ax, ay = attacker_x - target_x, attacker_y - target_y
    for lx, ly in ally_positions:
        if _chebyshev_cells(lx, ly, target_x, target_y) > 1:
            continue
        bx, by = lx - target_x, ly - target_y
        if ax == -bx and ay == -by and (ax != 0 or ay != 0):
            return True
        if ax != 0 and bx != 0 and (ax > 0) != (bx > 0) and ay == by == 0:
            return True
        if ay != 0 and by != 0 and (ay > 0) != (by > 0) and ax == bx == 0:
            return True
    return False


def leaving_melee_reach(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    hostile_positions: list[tuple[int, int, int]],
    *,
    reach_cells: int = 1,
) -> list[int]:
    """Return hostile combatant ids whose reach the mover leaves."""
    triggered: list[int] = []
    for cid, hx, hy in hostile_positions:
        was_in = _chebyshev_cells(from_x, from_y, hx, hy) <= reach_cells
        now_in = _chebyshev_cells(to_x, to_y, hx, hy) <= reach_cells
        if was_in and not now_in:
            triggered.append(cid)
    return triggered


def has_condition(combatant_conditions: list[str], condition: str) -> bool:
    return str(condition or "").lower() in _conditions(combatant_conditions)


def incapacitated(conditions: list[str]) -> bool:
    conds = set(_conditions(conditions))
    return bool(
        conds
        & {
            "incapacitated",
            "paralyzed",
            "petrified",
            "stunned",
            "unconscious",
        }
    )
