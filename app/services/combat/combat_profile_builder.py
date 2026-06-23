"""Build combat profiles from compendium entries at encounter snapshot time."""

from __future__ import annotations

from typing import Any

from app.services.combat.dnd5e_combat_profile import (
    merge_combat_effects,
    monster_profile,
    parse_stat_modifiers_text,
    species_profile,
)
from app.services.traits_compendium_service import resolve_trait_effects


def _trait_keys_from_species(species_entry: dict[str, Any] | None) -> list[str]:
    if not species_entry:
        return []
    keys = species_entry.get("trait_keys") or []
    if isinstance(keys, str):
        return [part.strip() for part in keys.split(",") if part.strip()]
    if isinstance(keys, list):
        return [str(k).strip() for k in keys if str(k).strip()]
    return []


def class_trait_keys(class_entry: dict[str, Any] | None, level: int) -> list[str]:
    if not class_entry:
        return []
    keys: list[str] = []
    base = class_entry.get("trait_keys") or []
    if isinstance(base, list):
        keys.extend(str(k).strip() for k in base if str(k).strip())
    try:
        level_int = max(1, min(20, int(level or 1)))
    except (TypeError, ValueError):
        level_int = 1
    for row in class_entry.get("level_progression") or []:
        try:
            row_level = int(row.get("level") or 0)
        except (TypeError, ValueError):
            continue
        if row_level > level_int:
            continue
        row_keys = row.get("trait_keys") or []
        if isinstance(row_keys, list):
            keys.extend(str(k).strip() for k in row_keys if str(k).strip())
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def build_player_combat_profile(
    campaign_id: int,
    sheet: dict[str, Any],
    *,
    species_entry: dict[str, Any] | None = None,
    class_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
    species_key = str(
        (species_entry or {}).get("key") or creation.get("species_key") or ""
    ).strip().lower()
    class_key = str(
        (class_entry or {}).get("key") or creation.get("class_key") or ""
    ).strip().lower()
    try:
        level = max(1, int(sheet.get("level") or 1))
    except (TypeError, ValueError):
        level = 1
    abilities = sheet.get("abilities") if isinstance(sheet.get("abilities"), dict) else {}

    layers: list[dict[str, Any]] = [species_profile(species_key)]
    trait_keys: list[str] = []
    trait_keys.extend(_trait_keys_from_species(species_entry))
    trait_keys.extend(class_trait_keys(class_entry, level))
    if trait_keys:
        layers.append(
            resolve_trait_effects(
                campaign_id,
                trait_keys,
                context={
                    "level": level,
                    "species_key": species_key or None,
                    "class_key": class_key or None,
                    "abilities": dict(abilities),
                },
            )
        )
    inline = (species_entry or {}).get("combat_effects")
    if isinstance(inline, dict) and inline:
        layers.append(dict(inline))
    layers.append(parse_stat_modifiers_text((species_entry or {}).get("stat_modifiers")))

    profile = merge_combat_effects({}, *layers)
    profile["save_prof_flags"] = dict(sheet.get("save_prof_flags") or {})
    profile["character_level"] = level
    profile["species_key"] = species_key or None
    ancestry = creation.get("dragonborn_ancestry")
    if species_key == "dragonborn" and ancestry:
        profile["damage_resistances"] = [str(ancestry).lower()]
    return profile


def build_monster_combat_profile(stats: dict[str, Any], campaign_id: int) -> dict[str, Any]:
    profile = monster_profile(stats)
    trait_keys = stats.get("trait_keys") or []
    if trait_keys:
        profile = merge_combat_effects(profile, resolve_trait_effects(campaign_id, trait_keys))
    inline = stats.get("combat_effects")
    if isinstance(inline, dict) and inline:
        profile = merge_combat_effects(profile, inline)
    return profile
