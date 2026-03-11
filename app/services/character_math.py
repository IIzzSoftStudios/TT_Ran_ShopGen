from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Tuple

from app.config.system_config import SYSTEM_DND5E, SYSTEM_PF2E
from app.models.users import CharacterStat, PlayerCharacter


@dataclass(frozen=True)
class ComputedStats:
    """Container for system-derived values."""

    skills: Dict[str, int]
    saves: Dict[str, int]


def ability_modifier(score: Optional[float]) -> int:
    """
    Compute the D20-style ability modifier from a raw score.

    Uses floor((score - 10) / 2). None is treated as 0 for now.
    """
    if score is None:
        return 0
    return int((int(score) - 10) // 2)


def dnd5e_proficiency_bonus(level: Optional[int]) -> int:
    """5e bounded accuracy proficiency progression."""
    if not level or level < 1:
        level = 1
    if level <= 4:
        return 2
    if level <= 8:
        return 3
    if level <= 12:
        return 4
    if level <= 16:
        return 5
    return 6


def _index_stats(
    stats: Iterable[CharacterStat],
) -> Dict[Tuple[Optional[str], str], CharacterStat]:
    """
    Index CharacterStat rows by (category, stat_key) for fast lookup.
    """
    indexed: Dict[Tuple[Optional[str], str], CharacterStat] = {}
    for stat in stats:
        key = (stat.category, stat.stat_key)
        if key not in indexed:
            indexed[key] = stat
    return indexed


def _get_value(
    index: Mapping[Tuple[Optional[str], str], CharacterStat],
    category: Optional[str],
    key: str,
    default: Optional[float] = None,
) -> Optional[float]:
    stat = index.get((category, key))
    return stat.value if stat is not None else default


# --- D&D 5e --------------------------------------------------------------------

_DND5E_SKILL_ABILITY: Dict[str, str] = {
    "Acrobatics": "DEX",
    "Animal_Handling": "WIS",
    "Arcana": "INT",
    "Athletics": "STR",
    "Deception": "CHA",
    "History": "INT",
    "Insight": "WIS",
    "Intimidation": "CHA",
    "Investigation": "INT",
    "Medicine": "WIS",
    "Nature": "INT",
    "Perception": "WIS",
    "Performance": "CHA",
    "Persuasion": "CHA",
    "Religion": "INT",
    "Sleight_of_Hand": "DEX",
    "Stealth": "DEX",
    "Survival": "WIS",
}

_DND5E_SAVE_ABILITY: Dict[str, str] = {
    "STR_SAVE": "STR",
    "DEX_SAVE": "DEX",
    "CON_SAVE": "CON",
    "INT_SAVE": "INT",
    "WIS_SAVE": "WIS",
    "CHA_SAVE": "CHA",
}


def _tier_to_multiplier(raw_tier: Optional[float]) -> float:
    """
    Map stored 5e proficiency tier code to a numeric multiplier.

    Tiers are encoded as:
      0 = Untrained  -> 0.0
      1 = Half       -> 0.5
      2 = Proficient -> 1.0
      3 = Expertise  -> 2.0
    """
    if raw_tier is None:
        return 0.0
    try:
        code = int(raw_tier)
    except (TypeError, ValueError):
        return 0.0
    if code == 1:
        return 0.5
    if code == 2:
        return 1.0
    if code == 3:
        return 2.0
    return 0.0


def _compute_dnd5e(
    character: PlayerCharacter, stats: Iterable[CharacterStat]
) -> ComputedStats:
    """
    Compute D&D 5e-style skill and save modifiers.

    Skill/Save proficiency information is read from:
      - category \"skill_prof_tier\", key = skill name
      - category \"save_prof_flag\",  key = save key (e.g. STR_SAVE)

    Expected multiplier values:
      - 0.0   = untrained
      - 0.5   = half proficient (Jack of All Trades)
      - 1.0   = proficient
      - 2.0   = expertise
    """
    index = _index_stats(stats)

    # Raw ability scores
    abilities: Dict[str, float] = {}
    for ability_key in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
        abilities[ability_key] = _get_value(index, "ability", ability_key, 10) or 10

    ability_mods: Dict[str, int] = {
        key: ability_modifier(score) for key, score in abilities.items()
    }

    pb = dnd5e_proficiency_bonus(character.level or 1)

    # Skills
    skill_mods: Dict[str, int] = {}
    for skill_key, ability_key in _DND5E_SKILL_ABILITY.items():
        base_mod = ability_mods.get(ability_key, 0)
        tier_raw = _get_value(index, "skill_prof_tier", skill_key, 0.0)
        prof_mult = _tier_to_multiplier(tier_raw)

        # Misc/item bonuses can be introduced later via additional categories;
        # for now, treat them as 0.
        misc_bonus = 0

        total = base_mod + int(pb * prof_mult) + misc_bonus
        skill_mods[skill_key] = total

    # Saving throws
    save_mods: Dict[str, int] = {}
    for save_key, ability_key in _DND5E_SAVE_ABILITY.items():
        base_mod = ability_mods.get(ability_key, 0)
        flag_raw = _get_value(index, "save_prof_flag", save_key, 0.0) or 0.0
        # Treat any non-zero flag as full proficiency
        prof_mult = 1.0 if flag_raw >= 0.5 else 0.0
        misc_bonus = 0

        total = base_mod + int(pb * prof_mult) + misc_bonus
        save_mods[save_key] = total

    return ComputedStats(skills=skill_mods, saves=save_mods)


# --- Pathfinder 2e -------------------------------------------------------------

_PF2E_SKILL_ABILITY: Dict[str, str] = {
    # Perception is treated like a skill in this schema
    "Perception": "WIS",
    "Acrobatics": "DEX",
    "Arcana": "INT",
    "Athletics": "STR",
    "Crafting": "INT",
    "Deception": "CHA",
    "Diplomacy": "CHA",
    "Intimidation": "CHA",
    "Lore": "INT",
    "Medicine": "WIS",
    "Nature": "WIS",
    "Occultism": "INT",
    "Performance": "CHA",
    "Religion": "WIS",
    "Society": "INT",
    "Stealth": "DEX",
    "Survival": "WIS",
    "Thievery": "DEX",
}

_PF2E_SAVE_ABILITY: Dict[str, str] = {
    "Fortitude": "CON",
    "Reflex": "DEX",
    "Will": "WIS",
}


def _pf2e_rank_bonus(raw_value: Optional[float]) -> int:
    """
    Interpret a stored rank as the PF2e proficiency bonus component.

    We expect values in {0, 2, 4, 6, 8} corresponding to
    Untrained/Trained/Expert/Master/Legendary, but clamp to int safely.
    """
    if raw_value is None:
        return 0
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return 0


def _compute_pf2e(
    character: PlayerCharacter, stats: Iterable[CharacterStat]
) -> ComputedStats:
    """
    Compute PF2e-style skill and save modifiers.

    Proficiency bonuses are: Level + RankValue for trained-or-better, where
    RankValue is typically 2/4/6/8. Untrained uses 0.
    """
    index = _index_stats(stats)

    # Raw ability scores
    abilities: Dict[str, float] = {}
    for ability_key in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
        abilities[ability_key] = _get_value(index, "ability", ability_key, 10) or 10

    ability_mods: Dict[str, int] = {
        key: ability_modifier(score) for key, score in abilities.items()
    }

    level = character.level or 1

    # Skills (including Perception)
    skill_mods: Dict[str, int] = {}
    for skill_key, ability_key in _PF2E_SKILL_ABILITY.items():
        base_mod = ability_mods.get(ability_key, 0)
        rank_bonus = _pf2e_rank_bonus(
            _get_value(index, "skill_rank", skill_key, 0.0)
        )
        # Item and misc bonuses can be modeled later; default to 0.
        item_bonus = 0
        misc_bonus = 0

        # If untrained (rank_bonus == 0), no level is added.
        prof_component = 0
        if rank_bonus > 0:
            prof_component = level + rank_bonus

        total = base_mod + prof_component + item_bonus + misc_bonus
        skill_mods[skill_key] = total

    # Saves
    save_mods: Dict[str, int] = {}
    for save_key, ability_key in _PF2E_SAVE_ABILITY.items():
        base_mod = ability_mods.get(ability_key, 0)
        rank_bonus = _pf2e_rank_bonus(
            _get_value(index, "save_rank", save_key, 0.0)
        )
        item_bonus = 0
        misc_bonus = 0

        prof_component = 0
        if rank_bonus > 0:
            prof_component = level + rank_bonus

        total = base_mod + prof_component + item_bonus + misc_bonus
        save_mods[save_key] = total

    return ComputedStats(skills=skill_mods, saves=save_mods)


# --- Public facade -------------------------------------------------------------

def compute_character_derived_stats(
    character: PlayerCharacter, stats: Iterable[CharacterStat]
) -> ComputedStats:
    """
    Compute derived skills and saves for a character based on system_type.

    For now, supports:
      - D&D 5e (SYSTEM_DND5E)
      - Pathfinder 2e (SYSTEM_PF2E)

    Other systems return empty dicts.
    """
    system_type = (character.system_type or "").lower()

    if system_type in {"dnd", "dnd5e", "5e", SYSTEM_DND5E}:
        return _compute_dnd5e(character, stats)
    if system_type in {"pf2", "pf2e", "pathfinder2e", SYSTEM_PF2E}:
        return _compute_pf2e(character, stats)

    return ComputedStats(skills={}, saves={})

