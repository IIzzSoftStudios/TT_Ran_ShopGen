"""Character sheet persistence + view builder.

One service boundary between (route, template) and (PlayerCharacterSheet,
ruleset registry). Routes never touch sheet_json directly; they call:

- ``get_or_default_sheet(player, campaign)`` on GET
- ``build_character_view(player, campaign, equipment_slots=..., name=...)``
  on GET to produce the exact SimpleNamespace the Jinja templates consume
- ``apply_sheet_update(player, campaign, form)`` on POST

Security invariants (from the Cyber-Architect review passes):
- Stat / skill / save / defense keys are whitelisted against the rule set
  (never client-supplied).
- Proficiency tier values must be in the rule set's declared tier set.
- Ability scores are clamped to the rule set's ability_min / ability_max.
- The caller is responsible for loading the right Player + Campaign (scope
  enforcement: player self-access via current_user, GM access via the
  campaign's owning GM). This service trusts the objects it is handed.
"""
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from app.extensions import db
from app.models import Campaign, Player, PlayerCharacterSheet
from app.services.rulesets import Ruleset, get_ruleset


SHEET_SCHEMA_VERSION = 1


def _empty_sheet(system_type):
    return {
        "schema_version": SHEET_SCHEMA_VERSION,
        "system_type": system_type,
        "name": None,
        "class_name": None,
        "species": None,
        "level": None,
        "notes": None,
        "abilities": {},
        "defenses": {},
        "save_prof_flags": {},
        "skill_prof_tiers": {},
    }


def _system_type_of(campaign):
    if campaign is None:
        return "generic"
    return getattr(campaign, "system_type", None) or "generic"


def _ruleset_for_sheet(campaign, sheet: dict) -> Ruleset:
    st = (sheet.get("system_type") or "").strip().lower()
    if not st or st == "generic":
        st = _system_type_of(campaign)
    return get_ruleset(st)


def create_initial_vault_sheet(player_id, *, system_type, name=None):
    """Insert a fresh vault (campaign_id NULL) sheet for ``player_id``.

    Used by the character-creation form so a brand new ``Player`` row lands
    with the system the user picked baked into ``sheet_json``. Caller owns
    the surrounding transaction (no commit here).
    """
    st = (system_type or "").strip().lower() or "generic"
    sheet = _empty_sheet(st)
    if name:
        clean = str(name).strip()
        if clean:
            sheet["name"] = clean[:100]
    row = PlayerCharacterSheet(
        player_id=player_id,
        campaign_id=None,
        sheet_json=sheet,
    )
    db.session.add(row)
    return row


def ensure_initial_campaign_sheet(player, campaign, *, name=None):
    """Create the starter campaign sheet for a campaign-bound character.

    CAMP-code registration creates the campaign ``Player`` row before the
    full character-builder flow runs. This gives that character a scoped sheet
    immediately so the later walkthrough can edit the existing character
    instead of creating a second solo vault character.
    """
    if player is None or campaign is None:
        return None
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id,
        campaign_id=campaign.id,
    ).first()
    if row is not None:
        return row
    sheet = _empty_sheet(_system_type_of(campaign))
    if name:
        clean = str(name).strip()
        if clean:
            sheet["name"] = clean[:100]
    row = PlayerCharacterSheet(
        player_id=player.id,
        campaign_id=campaign.id,
        sheet_json=sheet,
    )
    db.session.add(row)
    return row


def get_or_default_sheet(player, campaign):
    """Return the stored sheet dict (or a defaulted one). Never auto-inserts."""
    if player is None:
        return _empty_sheet(_system_type_of(campaign))

    row = None
    if campaign is not None:
        row = (
            PlayerCharacterSheet.query.filter_by(
                player_id=player.id, campaign_id=campaign.id
            ).first()
        )
    else:
        row = (
            PlayerCharacterSheet.query.filter(
                PlayerCharacterSheet.player_id == player.id,
                PlayerCharacterSheet.campaign_id.is_(None),
            ).first()
        )

    if row is None or not isinstance(row.sheet_json, dict):
        return _empty_sheet(_system_type_of(campaign))

    # Merge with defaults so newly-added top-level keys (future schema
    # versions) do not KeyError older stored blobs.
    merged = _empty_sheet(_system_type_of(campaign))
    for k, v in row.sheet_json.items():
        merged[k] = v
    if campaign is not None:
        # Campaign is source of truth for in-campaign sheets.
        merged["system_type"] = _system_type_of(campaign)
    # Vault (campaign is None): keep ``system_type`` from stored JSON.
    for sub in ("abilities", "defenses", "save_prof_flags", "skill_prof_tiers"):
        if not isinstance(merged.get(sub), dict):
            merged[sub] = {}
    return merged


def _build_abilities_display(ruleset, sheet):
    out = []
    abilities_map = sheet.get("abilities") or {}
    for ab in ruleset.abilities:
        raw = abilities_map.get(ab.key)
        try:
            value = int(raw) if raw is not None and raw != "" else None
        except (TypeError, ValueError):
            value = None
        modifier = (
            ruleset.compute_ability_mod(value) if value is not None else None
        )
        out.append(
            {
                "id": f"ability_{ab.key}",
                "key": ab.key,
                "label": ab.label,
                "category": "ability",
                "value": value,
                "modifier": modifier,
                "computed_value": None,
            }
        )
    return out


def _build_defenses_display(ruleset, sheet):
    out = []
    defenses_map = sheet.get("defenses") or {}
    for d in ruleset.derived:
        raw = defenses_map.get(d.key)
        try:
            value = int(raw) if raw is not None and raw != "" else None
        except (TypeError, ValueError):
            value = None
        out.append(
            {
                "id": f"defense_{d.key}",
                "key": d.key,
                "label": d.label,
                "category": "derived",
                "value": value,
                "modifier": None,
                "computed_value": None,
            }
        )

    # Saves rendered in the same grid with category='save' so the template's
    # per-save proficiency checkbox block fires.
    prof_flags = sheet.get("save_prof_flags") or {}
    level = sheet.get("level") or 0
    prof_bonus = ruleset.proficiency_bonus(level)
    abilities_map = sheet.get("abilities") or {}
    for s in ruleset.saves:
        ability_mod = 0
        if s.ability_key:
            score = abilities_map.get(s.ability_key)
            ability_mod = ruleset.compute_ability_mod(score)
        flag = prof_flags.get(s.key)
        try:
            flag_f = float(flag) if flag is not None else 0.0
        except (TypeError, ValueError):
            flag_f = 0.0
        computed = ability_mod + (prof_bonus * (1 if flag_f >= 0.5 else 0))
        out.append(
            {
                "id": f"save_{s.key}",
                "key": s.key,
                "label": s.label,
                "category": "save",
                "value": None,
                "modifier": None,
                "computed_value": computed,
            }
        )
    return out


def _build_skills_display(ruleset, sheet):
    out = []
    if not ruleset.skills:
        return out
    prof_tiers = sheet.get("skill_prof_tiers") or {}
    level = sheet.get("level") or 0
    prof_bonus = ruleset.proficiency_bonus(level)
    abilities_map = sheet.get("abilities") or {}
    for sk in ruleset.skills:
        ability_mod = ruleset.compute_ability_mod(
            abilities_map.get(sk.ability_key)
        )
        tier_val = prof_tiers.get(sk.key)
        tier = ruleset.tier_by_value(tier_val)
        multiplier = tier.multiplier if tier is not None else 0.0
        # Round half to nearest lower int (D&D 5e half-proficiency rounds down).
        prof_component = int(prof_bonus * multiplier)
        computed = ability_mod + prof_component
        out.append(
            {
                "id": f"skill_{sk.key}",
                "key": sk.key,
                "label": sk.label,
                "category": "skill",
                "value": None,
                "modifier": ability_mod,
                "computed_value": computed,
            }
        )
    return out


def _assemble_display_sections(ruleset, sheet):
    """Build each display section once and return (abilities, derived, saves, skills).

    Centralised so ``build_character_view`` and ``character_data_payload``
    stay in lock-step and do not each rebuild overlapping slices of the
    sheet (which previously made ``stat_display`` diverge between the HTML
    view and the JSON payload).
    """
    abilities = _build_abilities_display(ruleset, sheet)
    defenses_and_saves = _build_defenses_display(ruleset, sheet)
    derived = [row for row in defenses_and_saves if row["category"] == "derived"]
    saves = [row for row in defenses_and_saves if row["category"] == "save"]
    skills = _build_skills_display(ruleset, sheet)
    return abilities, derived, saves, skills


def _sheet_system_type(campaign, sheet: dict) -> str:
    st = (sheet.get("system_type") or "").strip().lower()
    if st and st != "generic":
        return st
    return _system_type_of(campaign)


def _creation_block(sheet: dict) -> dict:
    raw = sheet.get("creation")
    return raw if isinstance(raw, dict) else {}


def _resolve_class_details(player, campaign, sheet):
    from app.services.classes_compendium_service import (
        _level_row,
        resolve_character_class_details,
    )
    from app.services.character_creation.level_progression_service import (
        _class_entry_for_sheet,
    )

    creation = _creation_block(sheet)
    class_key = creation.get("class_key")
    subclass_key = creation.get("subclass_key")
    level = sheet.get("level")
    class_name = sheet.get("class_name")
    if _sheet_system_type(campaign, sheet) != "dnd5e":
        return {
            "available": False,
            "hidden_message": None,
            "name": class_name,
            "level": level,
        }

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    if campaign_id is not None:
        return resolve_character_class_details(
            campaign_id,
            class_key=class_key,
            level=level,
            class_name_fallback=class_name,
            owner_class_key=class_key,
            subclass_key=subclass_key,
        )

    entry = _class_entry_for_sheet(None, sheet)
    if entry is None:
        return {
            "available": False,
            "hidden_message": "Class details are not available for this character.",
            "name": class_name,
            "level": level,
        }
    try:
        level_int = max(1, min(20, int(level or 1)))
    except (TypeError, ValueError):
        level_int = 1
    current_row = _level_row(entry, level_int)
    next_row = _level_row(entry, level_int + 1) if level_int < 20 else None
    return {
        "available": True,
        "hidden_message": None,
        "key": entry.get("key"),
        "name": entry.get("name") or class_name,
        "summary": entry.get("summary") or "",
        "hit_die": entry.get("hit_die"),
        "save_proficiencies": list(entry.get("save_proficiencies") or []),
        "source": entry.get("source"),
        "level": level_int,
        "current_level_row": current_row,
        "next_level_row": next_row,
    }


def _resolve_species_details(campaign, sheet):
    from app.services.character_creation.dnd5e_catalog import (
        catalog_entry_by_key,
        merged_creation_catalog,
    )
    from app.services.species_compendium_service import resolve_character_species_details

    species_name = sheet.get("species")
    creation = _creation_block(sheet)
    species_key = creation.get("species_key")
    if (
        campaign is not None
        and getattr(campaign, "id", None) is not None
        and (_system_type_of(campaign) or "").lower() == "dnd5e"
    ):
        return resolve_character_species_details(
            campaign.id,
            species_key=species_key,
            species_name_fallback=species_name,
        )

    if _sheet_system_type(campaign, sheet) != "dnd5e":
        return {
            "available": False,
            "name": species_name,
            "entry": None,
        }

    catalog = merged_creation_catalog()
    entry = None
    key_hint = str(species_key or "").strip().lower()
    if key_hint:
        entry = catalog_entry_by_key(catalog, "species", key_hint)
    if entry is None and species_name:
        name_hint = str(species_name).strip().lower()
        for row in catalog.get("species") or []:
            if not isinstance(row, dict):
                continue
            row_key = str(row.get("key") or "").strip().lower()
            row_name = str(row.get("name") or "").strip().lower()
            if row_name == name_hint or row_key == name_hint.replace(" ", "-"):
                entry = row
                break
    display_name = (
        str((entry or {}).get("name") or species_name or species_key or "").strip()
        or None
    )
    if entry is None:
        return {
            "available": bool(display_name),
            "name": display_name,
            "entry": None,
        }
    return {
        "available": True,
        "name": display_name,
        "entry": entry,
    }


def _mechanical_trait_rows(trait_keys: list[str], *, campaign_id: int | None) -> list[dict[str, str]]:
    mechanical: list[dict[str, str]] = []
    if not trait_keys:
        return mechanical
    by_key: dict[str, dict[str, Any]] = {}
    if campaign_id is not None:
        from app.services.traits_compendium_service import ensure_traits_compendium

        by_key = {
            str(row.get("key") or "").strip().lower(): row
            for row in ensure_traits_compendium(campaign_id)
        }
    else:
        from app.services.character_creation.dnd5e_traits import CORE_TRAITS_BY_KEY

        by_key = CORE_TRAITS_BY_KEY
    for key in trait_keys:
        needle = str(key or "").strip().lower()
        if not needle:
            continue
        row = by_key.get(needle) or {}
        summary = str(row.get("summary") or row.get("notes") or "")[:300]
        rules_text = str(row.get("rules_text") or "")[:2000]
        mechanical.append(
            {
                "key": needle,
                "name": str(row.get("name") or needle),
                "summary": summary,
                "description": summary,
                "rules_text": rules_text,
            }
        )
    return mechanical


def _trait_tooltip_text(
    trait_key: str,
    *,
    campaign_id: int | None = None,
    fallback: str = "",
) -> str:
    """Player-facing tooltip body for a compendium trait key."""
    clean = str(trait_key or "").strip().lower()
    if not clean:
        return fallback
    if campaign_id is not None:
        rows = _mechanical_trait_rows([clean], campaign_id=campaign_id)
        if rows:
            row = rows[0]
            return str(row.get("rules_text") or row.get("summary") or fallback)
    from app.services.character_creation.dnd5e_srd_class_traits import _TRAIT_SUMMARIES

    return str(_TRAIT_SUMMARIES.get(clean) or fallback)


def _resolve_traits_details(campaign, sheet, species_details=None):
    """Player-safe racial traits from the sheet and compendium."""
    creation = _creation_block(sheet)
    flavor = list(sheet.get("traits") or [])
    entry = (species_details or {}).get("entry") if isinstance(species_details, dict) else None
    if not flavor and isinstance(entry, dict):
        flavor = list(entry.get("traits") or [])
    trait_keys = list(creation.get("trait_keys") or [])
    if not trait_keys and isinstance(entry, dict):
        trait_keys = list(entry.get("trait_keys") or [])
    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    mechanical = _mechanical_trait_rows(
        trait_keys,
        campaign_id=campaign_id
        if campaign_id is not None and _sheet_system_type(campaign, sheet) == "dnd5e"
        else None,
    )
    ancestry = creation.get("dragonborn_ancestry")
    stat_modifiers = str(creation.get("stat_modifiers") or "").strip()
    if not stat_modifiers and isinstance(entry, dict):
        stat_modifiers = str(entry.get("stat_modifiers") or "").strip()
    return {
        "available": bool(flavor or mechanical or ancestry or stat_modifiers),
        "name": (species_details or {}).get("name") if isinstance(species_details, dict) else sheet.get("species"),
        "traits": flavor,
        "mechanical_traits": mechanical,
        "dragonborn_ancestry": ancestry,
        "dragonborn_breath_summary": creation.get("dragonborn_breath_summary"),
        "dragonborn_breath_shape": creation.get("dragonborn_breath_shape"),
        "stat_modifiers": stat_modifiers,
        "hidden_message": None,
    }


def _resolve_background_details(campaign, sheet):
    from app.services.character_creation.dnd5e_catalog import (
        catalog_entry_by_key,
        merged_creation_catalog,
    )

    creation = _creation_block(sheet)
    background_key = str(creation.get("background_key") or "").strip().lower()
    if not background_key or _sheet_system_type(campaign, sheet) != "dnd5e":
        return {"available": False, "name": None, "summary": "", "skill_proficiencies": []}

    if campaign is not None and getattr(campaign, "id", None) is not None:
        from app.services.character_creation.campaign_settings import get_character_options

        catalog = merged_creation_catalog(
            campaign_id=campaign.id,
            character_options=get_character_options(campaign.id),
        )
    else:
        catalog = merged_creation_catalog()
    entry = catalog_entry_by_key(catalog, "backgrounds", background_key)
    if entry is None:
        return {
            "available": False,
            "name": background_key.replace("-", " ").title(),
            "summary": "",
            "skill_proficiencies": [],
        }
    return {
        "available": True,
        "name": entry.get("name") or background_key,
        "summary": str(entry.get("summary") or ""),
        "skill_proficiencies": list(entry.get("skill_proficiencies") or []),
    }


def _combat_abilities_from_profile(
    profile: dict[str, Any] | None,
    *,
    campaign_id: int | None = None,
) -> list[dict[str, str]]:
    """Player-facing mechanical class abilities from merged combat profile."""
    if not isinstance(profile, dict):
        return []
    abilities: list[dict[str, str]] = []
    try:
        extra = int(profile.get("extra_attacks_per_action") or 0)
    except (TypeError, ValueError):
        extra = 0
    if extra >= 2:
        trait_key = "cf-extra-attack"
        if extra >= 4:
            trait_key = "cf-extra-attack-3"
        elif extra >= 3:
            trait_key = "cf-extra-attack-2"
        abilities.append(
            {
                "key": "extra_attack",
                "label": f"Extra Attack ({extra} attacks per Attack action)",
                "description": _trait_tooltip_text(
                    trait_key,
                    campaign_id=campaign_id,
                    fallback="Attack multiple times when you take the Attack action.",
                ),
            }
        )
    add_ab = str(profile.get("unarmored_ac_add_ability") or "").strip().lower()
    if profile.get("unarmored_defense") or add_ab:
        shield_ok = bool(profile.get("unarmored_defense_allows_shield", True))
        shield_text = "shield allowed" if shield_ok else "no shield"
        ability_label = add_ab.upper() if add_ab else "?"
        ud_trait = (
            "cf-monk-unarmored-defense"
            if add_ab == "wis" and not shield_ok
            else "cf-barbarian-unarmored-defense"
        )
        abilities.append(
            {
                "key": "unarmored_defense",
                "label": f"Unarmored Defense (AC 10 + DEX + {ability_label}, {shield_text})",
                "description": _trait_tooltip_text(
                    ud_trait,
                    campaign_id=campaign_id,
                    fallback=f"AC 10 + DEX + {ability_label} when not wearing armor ({shield_text}).",
                ),
            }
        )
    if profile.get("action_surge"):
        try:
            add_actions = max(1, int(profile.get("action_surge_additional_actions") or 1))
        except (TypeError, ValueError):
            add_actions = 1
        word = "action" if add_actions == 1 else "actions"
        abilities.append(
            {
                "key": "action_surge",
                "label": f"Action Surge (+{add_actions} {word} on your turn)",
                "description": _trait_tooltip_text(
                    "cf-fighter-action-surge",
                    campaign_id=campaign_id,
                    fallback="Take one additional action on your turn (short rest recharge).",
                ),
            }
        )
    return abilities


def _enrich_class_features_from_traits(
    features: list[Any],
    trait_keys: list[str],
    *,
    campaign_id: int | None,
    class_key: str | None = None,
) -> list[dict[str, Any]]:
    """Merge compendium trait summaries into progression feature labels."""
    from app.services.character_creation.dnd5e_srd_class_traits import trait_key_for_feature

    trait_by_key = {
        str(row.get("key") or "").strip().lower(): row
        for row in _mechanical_trait_rows(trait_keys, campaign_id=campaign_id)
    }
    enriched: list[dict[str, Any]] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        name = str(feat.get("name") or "").strip()
        if not name:
            continue
        description = str(feat.get("description") or feat.get("summary") or "").strip()
        summary = str(feat.get("summary") or description).strip()
        rules_text = str(feat.get("rules_text") or "").strip()
        trait_key = str(feat.get("trait_key") or "").strip().lower()
        if not trait_key and class_key:
            trait_key = trait_key_for_feature(class_key, name)
        if not description and trait_key:
            trait_row = trait_by_key.get(trait_key)
            if trait_row is None:
                lookup = _mechanical_trait_rows([trait_key], campaign_id=campaign_id)
                trait_row = lookup[0] if lookup else None
            if trait_row:
                description = str(
                    trait_row.get("description") or trait_row.get("summary") or ""
                ).strip()
                if not summary:
                    summary = description
                if not rules_text:
                    rules_text = str(trait_row.get("rules_text") or "").strip()
        enriched.append(
            {
                "name": name,
                "description": description,
                "summary": summary or description,
                "rules_text": rules_text,
                "trait_key": trait_key,
            }
        )
    return enriched


def _accumulated_class_features(campaign, sheet) -> list[dict[str, Any]]:
    from app.services.classes_compendium_service import _level_row
    from app.services.character_creation.level_progression_service import (
        _class_entry_for_sheet,
    )

    if _sheet_system_type(campaign, sheet) != "dnd5e":
        return []
    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    entry = _class_entry_for_sheet(campaign_id, sheet)
    if entry is None:
        return []
    class_key = str(entry.get("key") or "").strip().lower()
    try:
        level_int = max(1, min(20, int(sheet.get("level") or 1)))
    except (TypeError, ValueError):
        level_int = 1
    history: list[dict[str, Any]] = []
    for lvl in range(1, level_int + 1):
        row = _level_row(entry, lvl) or {}
        trait_keys = list(row.get("trait_keys") or [])
        features = _enrich_class_features_from_traits(
            list(row.get("features") or []),
            trait_keys,
            campaign_id=campaign_id,
            class_key=class_key or None,
        )
        if not features and trait_keys:
            features = [
                {
                    "name": item["name"],
                    "description": item.get("description") or item.get("summary") or "",
                    "summary": item.get("summary") or "",
                    "rules_text": item.get("rules_text") or "",
                    "trait_key": item.get("key") or "",
                }
                for item in _mechanical_trait_rows(trait_keys, campaign_id=campaign_id)
            ]
        if not features:
            continue
        history.append({"level": lvl, "features": features})
    return history


from app.services.character_creation.progression_helpers import resolve_spell_slots_from_row


def _resolve_spell_slots_display(campaign, sheet, class_details) -> dict[str, int]:
    stored = sheet.get("spell_slots")
    if isinstance(stored, dict) and stored:
        out: dict[str, int] = {}
        for key, value in stored.items():
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count > 0:
                out[str(key)] = count
        if out:
            return out
    if not isinstance(class_details, dict) or not class_details.get("available"):
        return {}
    current_row = class_details.get("current_level_row") or {}
    return resolve_spell_slots_from_row(current_row)


def build_character_view(player, campaign, *, name=None, equipment_slots=None):
    """Produce the SimpleNamespace the character-sheet templates consume."""
    sheet = get_or_default_sheet(player, campaign)
    ruleset = _ruleset_for_sheet(campaign, sheet)

    stored_raw = sheet.get("name") if isinstance(sheet, dict) else None
    stored_name = (stored_raw or "").strip() or None
    if name:
        display_name = name
    elif stored_name:
        display_name = stored_name
    elif player is not None and getattr(player, "is_npc", False):
        display_name = "NPC"
    elif player is not None and getattr(player, "id", None) is not None:
        # Stay consistent with list views (`list_characters`,
        # `_player_character_rows_for_campaign`, and
        # `_build_solo_characters_for_user`) which all fall back to
        # ``Character #N``. Surfacing the account username here was a
        # cross-character PII leak: another player viewing a sheet would
        # learn the owner's login name even though the character was
        # left intentionally unnamed.
        display_name = f"Character #{player.id}"
    else:
        display_name = "Character"

    abilities, derived, saves, skills = _assemble_display_sections(ruleset, sheet)
    defenses_display = derived + saves
    # Flat list in the same shape the JSON payload produces so any consumer
    # (template or frontend) that reads ``character.stat_display`` sees the
    # full ability + derived + save + skill set, not just abilities.
    stat_display = abilities + derived + saves + skills
    class_details = _resolve_class_details(player, campaign, sheet)
    spell_details = _resolve_spell_details(campaign, sheet, class_details=class_details)
    species_details = _resolve_species_details(campaign, sheet)
    traits_details = _resolve_traits_details(campaign, sheet, species_details)
    background_details = _resolve_background_details(campaign, sheet)
    class_feature_history = _accumulated_class_features(campaign, sheet)
    spell_slots_display = _resolve_spell_slots_display(campaign, sheet, class_details)

    class_features: list[dict[str, Any]] = []
    for level_row in class_feature_history:
        for feat in level_row.get("features") or []:
            if isinstance(feat, dict) and feat.get("name"):
                description = (
                    feat.get("description")
                    or feat.get("summary")
                    or ""
                )
                class_features.append(
                    {
                        "name": feat.get("name"),
                        "description": description,
                        "summary": feat.get("summary") or description,
                        "rules_text": feat.get("rules_text") or "",
                        "level": level_row.get("level"),
                    }
                )
    pending_trait_choices: list[dict[str, Any]] = []

    from app.services.character_creation.level_progression_service import preview_level_up
    from app.services.character_creation.campaign_settings import get_max_player_level

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    max_player_level = get_max_player_level(campaign_id)
    level_up_preview = preview_level_up(player, campaign)

    class_progression = (
        sheet.get("class_progression") if isinstance(sheet.get("class_progression"), dict) else {}
    )
    pending_level_choices = [
        choice
        for choice in (sheet.get("pending_level_choices") or [])
        if isinstance(choice, dict) and not choice.get("skipped")
    ]
    if pending_level_choices and class_details.get("available_subclasses"):
        enriched: list[dict[str, Any]] = []
        for choice in pending_level_choices:
            row = dict(choice)
            if str(row.get("type") or "").strip().lower() == "subclass":
                row["options"] = list(class_details.get("available_subclasses") or [])
            enriched.append(row)
        pending_level_choices = enriched
    class_resources = (
        sheet.get("class_resources") if isinstance(sheet.get("class_resources"), dict) else {}
    )
    combat_abilities: list[dict[str, str]] = []
    if _sheet_system_type(campaign, sheet) == "dnd5e" and campaign is not None:
        from app.services.classes_compendium_service import get_class_entry
        from app.services.combat.combat_profile_builder import build_player_combat_profile
        from app.services.species_compendium_service import get_species_entry

        creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
        combat_profile = build_player_combat_profile(
            campaign.id,
            sheet,
            species_entry=get_species_entry(campaign.id, creation.get("species_key")),
            class_entry=get_class_entry(campaign.id, creation.get("class_key")),
        )
        combat_abilities = _combat_abilities_from_profile(
            combat_profile,
            campaign_id=campaign.id,
        )

    return SimpleNamespace(
        id=getattr(player, "id", None),
        name=display_name,
        # Resolved ruleset (unknown campaign.system_type falls back to generic).
        system_type=ruleset.system_type,
        class_name=sheet.get("class_name"),
        species=sheet.get("species"),
        level=sheet.get("level"),
        notes=sheet.get("notes"),
        abilities_display=abilities,
        defenses_display=defenses_display,
        skills_display=skills,
        save_prof_flags=dict(sheet.get("save_prof_flags") or {}),
        skill_prof_tiers=dict(sheet.get("skill_prof_tiers") or {}),
        equipment_slots=equipment_slots or [],
        ruleset_meta=ruleset.to_meta(),
        stat_display=stat_display,
        class_details=class_details,
        spell_details=spell_details,
        species_details=species_details,
        traits_details=traits_details,
        background_details=background_details,
        class_feature_history=class_feature_history,
        spell_slots_display=spell_slots_display,
        level_up_preview=level_up_preview,
        class_progression=class_progression,
        class_resources=class_resources,
        pending_level_choices=pending_level_choices,
        class_features=class_features,
        pending_trait_choices=pending_trait_choices,
        combat_abilities=combat_abilities,
        max_player_level=max_player_level,
    )


def _spell_display_stub(key: str) -> dict[str, Any]:
    clean = str(key or "").strip().lower()
    return {
        "key": clean,
        "name": clean.replace("-", " ").title() if clean else "Unknown spell",
    }


def _spell_caps_for_sheet(sheet: dict[str, Any], class_details: dict[str, Any] | None = None) -> dict[str, int]:
    """Return cantrips_known / spells_known / spells_prepared caps for the character."""
    from app.services.character_creation.progression_helpers import class_progression_caps_from_row

    caps: dict[str, int] = {}
    stored = sheet.get("class_progression") if isinstance(sheet.get("class_progression"), dict) else {}
    for field in ("cantrips_known", "spells_known", "spells_prepared"):
        raw = stored.get(field)
        if raw is not None and raw != "":
            try:
                caps[field] = int(raw)
            except (TypeError, ValueError):
                pass
    if isinstance(class_details, dict):
        row_caps = class_progression_caps_from_row(class_details.get("current_level_row") or {})
        for field in ("cantrips_known", "spells_known", "spells_prepared"):
            if field not in caps and field in row_caps:
                caps[field] = int(row_caps[field])
    return caps


def _max_castable_spell_level(
    campaign,
    sheet: dict[str, Any],
    class_details: dict[str, Any] | None = None,
) -> int:
    """Highest leveled spell slot the character can cast (0 if none)."""
    slots = _resolve_spell_slots_display(campaign, sheet, class_details or {})
    if slots:
        return max(int(level) for level in slots)
    try:
        char_level = max(1, int(sheet.get("level") or 1))
    except (TypeError, ValueError):
        char_level = 1
    return min(9, ((char_level - 1) // 2) + 1)


def _spell_is_available_at_level(
    spell: dict[str, Any],
    *,
    max_spell_level: int,
    selected_keys: set[str],
) -> bool:
    key = str(spell.get("key") or "").strip().lower()
    if key and key in selected_keys:
        return True
    try:
        spell_level = int(spell.get("level") or 0)
    except (TypeError, ValueError):
        spell_level = 0
    if spell_level == 0:
        return True
    return spell_level <= max_spell_level


def _merge_spell_keys_to_entries(keys: list[str], resolved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {
        str(entry.get("key") or "").strip().lower(): entry
        for entry in resolved
        if str(entry.get("key") or "").strip()
    }
    out: list[dict[str, Any]] = []
    for raw in keys:
        key = str(raw or "").strip().lower()
        if not key:
            continue
        out.append(by_key.get(key) or _spell_display_stub(key))
    return out


def _resolve_spell_details(campaign, sheet, *, class_details=None):
    from app.services.spells_compendium_service import (
        list_visible_spells,
        resolve_character_spells,
    )

    if _sheet_system_type(campaign, sheet) != "dnd5e":
        return {
            "available": False,
            "spells": {},
            "catalog": [],
            "has_selections": False,
        }

    spells_state = sheet.get("spells") if isinstance(sheet.get("spells"), dict) else {}
    known_keys = [str(k) for k in (spells_state.get("known") or []) if str(k).strip()]
    prepared_keys = [str(k) for k in (spells_state.get("prepared") or []) if str(k).strip()]
    cantrip_keys = [str(k) for k in (spells_state.get("cantrips") or []) if str(k).strip()]
    selected_keys = {
        str(k).strip().lower()
        for k in (*known_keys, *prepared_keys, *cantrip_keys)
        if str(k).strip()
    }

    creation = _creation_block(sheet)
    class_key = str(creation.get("class_key") or "").strip().lower()
    if not class_key:
        class_key = str(sheet.get("class_name") or "").strip().lower().replace(" ", "_")

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    if campaign_id is not None:
        catalog = list_visible_spells(campaign_id)
        raw_spells = resolve_character_spells(campaign_id, sheet)
    else:
        from app.services.character_creation.dnd5e_spells import CORE_SPELLS

        catalog = list(CORE_SPELLS)
        core_by_key = {
            str(row.get("key") or "").strip().lower(): row for row in CORE_SPELLS
        }

        def _from_core(keys: list[str]) -> list[dict[str, Any]]:
            return [
                core_by_key.get(str(k).strip().lower()) or _spell_display_stub(k)
                for k in keys
                if str(k).strip()
            ]

        raw_spells = {
            "known": _from_core(known_keys),
            "prepared": _from_core(prepared_keys),
            "cantrips": _from_core(cantrip_keys),
            "slots_used": dict(spells_state.get("slots_used") or {}),
        }

    spells = {
        "known": _merge_spell_keys_to_entries(known_keys, raw_spells.get("known") or []),
        "prepared": _merge_spell_keys_to_entries(prepared_keys, raw_spells.get("prepared") or []),
        "cantrips": _merge_spell_keys_to_entries(cantrip_keys, raw_spells.get("cantrips") or []),
        "slots_used": dict(raw_spells.get("slots_used") or {}),
    }
    max_spell_level = _max_castable_spell_level(campaign, sheet, class_details)
    spell_caps = _spell_caps_for_sheet(sheet, class_details)
    from app.services.character_creation.progression_helpers import resolve_spell_list_limits

    class_available = []
    if class_key and catalog:
        class_available = [
            spell
            for spell in catalog
            if class_key
            in {
                str(cls or "").strip().lower().replace(" ", "_")
                for cls in (spell.get("classes") or [])
            }
            and _spell_is_available_at_level(
                spell,
                max_spell_level=max_spell_level,
                selected_keys=selected_keys,
            )
        ]
    has_selections = bool(spells["cantrips"] or spells["prepared"] or spells["known"])
    limits = resolve_spell_list_limits(spell_caps)
    return {
        "available": True,
        "has_selections": has_selections,
        "spells": spells,
        "catalog": catalog,
        "class_key": class_key,
        "class_available": class_available,
        "caps": spell_caps,
        "limits": limits,
        "max_spell_level": max_spell_level,
        "counts": {
            "cantrips": len(cantrip_keys),
            "prepared": len(prepared_keys),
            "known": len({str(k).strip().lower() for k in known_keys if str(k).strip()}),
        },
    }


def character_data_payload(player, campaign, *, equipment_slots=None):
    """Shape for /player/character-data (the Player_Home.html panel)."""
    sheet = get_or_default_sheet(player, campaign)
    ruleset = _ruleset_for_sheet(campaign, sheet)

    abilities, derived, saves, skills = _assemble_display_sections(ruleset, sheet)
    stat_display = abilities + derived + saves + skills
    class_details = _resolve_class_details(player, campaign, sheet)
    spell_details = _resolve_spell_details(campaign, sheet, class_details=class_details)
    species_details = _resolve_species_details(campaign, sheet)
    traits_details = _resolve_traits_details(campaign, sheet, species_details)

    equipment_derived: dict = {}
    combat_abilities: list[dict[str, str]] = []
    if player is not None and (_system_type_of(campaign) or "").lower() == "dnd5e":
        from app.services.equipment.item_rules import (
            build_weapon_attacks,
            compute_equipment_ac,
            count_attuned_items,
            get_equipped_items,
        )

        equipped = get_equipped_items(player)
        dex_score = int((sheet.get("abilities") or {}).get("dex", 10))
        str_score = int((sheet.get("abilities") or {}).get("str", 10))
        dex_mod = ruleset.compute_ability_mod(dex_score)
        str_mod = ruleset.compute_ability_mod(str_score)
        con_mod = ruleset.compute_ability_mod(int((sheet.get("abilities") or {}).get("con", 10)))
        wis_mod = ruleset.compute_ability_mod(int((sheet.get("abilities") or {}).get("wis", 10)))
        try:
            level = max(1, int(sheet.get("level") or 1))
        except (TypeError, ValueError):
            level = 1
        prof = ruleset.proficiency_bonus(level)
        from app.services.classes_compendium_service import get_class_entry
        from app.services.combat.combat_profile_builder import build_player_combat_profile
        from app.services.species_compendium_service import get_species_entry

        creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
        combat_profile = build_player_combat_profile(
            campaign.id,
            sheet,
            species_entry=get_species_entry(campaign.id, creation.get("species_key")),
            class_entry=get_class_entry(campaign.id, creation.get("class_key")),
        )
        equipment_derived = {
            "ac": compute_equipment_ac(
                equipped,
                dex_mod=dex_mod,
                con_mod=con_mod,
                wis_mod=wis_mod,
                unarmored_ac_add_ability=combat_profile.get("unarmored_ac_add_ability"),
                unarmored_defense_allows_shield=bool(
                    combat_profile.get("unarmored_defense_allows_shield", True)
                ),
            ),
            "attacks": build_weapon_attacks(
                equipped, str_mod=str_mod, dex_mod=dex_mod, prof_bonus=prof
            ),
            "attuned_count": count_attuned_items(equipped),
            "attunement_limit": 3,
        }
        combat_abilities = _combat_abilities_from_profile(
            combat_profile,
            campaign_id=campaign.id,
        )

    class_feature_history = _accumulated_class_features(campaign, sheet)
    class_features: list[dict[str, Any]] = []
    for level_row in class_feature_history:
        for feat in level_row.get("features") or []:
            if isinstance(feat, dict) and feat.get("name"):
                description = (
                    feat.get("description")
                    or feat.get("summary")
                    or ""
                )
                class_features.append(
                    {
                        "name": feat.get("name"),
                        "description": description,
                        "summary": feat.get("summary") or description,
                        "rules_text": feat.get("rules_text") or "",
                        "level": level_row.get("level"),
                    }
                )

    from app.services.character_creation.level_progression_service import preview_level_up
    from app.services.character_creation.campaign_settings import get_max_player_level

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None

    return {
        "system_type": ruleset.system_type,
        "stat_display": stat_display,
        "class_details": class_details,
        "class_features": class_features,
        "spell_details": spell_details,
        "species_details": species_details,
        "traits_details": traits_details,
        "combat_abilities": combat_abilities,
        "level_up_preview": preview_level_up(player, campaign),
        "max_player_level": get_max_player_level(campaign_id),
        "equipment_derived": equipment_derived,
        "class_name": sheet.get("class_name"),
        "level": sheet.get("level"),
        "stat_schema": {
            "abilities": [
                {"key": a.key, "label": a.label} for a in ruleset.abilities
            ],
            "skills": [
                {"key": s.key, "label": s.label, "ability_key": s.ability_key}
                for s in ruleset.skills
            ],
            "saves": [
                {"key": s.key, "label": s.label, "ability_key": s.ability_key}
                for s in ruleset.saves
            ],
            "derived": [
                {"key": d.key, "label": d.label, "header": bool(d.header)}
                for d in ruleset.derived
            ],
            "supports_skill_proficiency": ruleset.supports_skill_proficiency,
            "supports_save_proficiency": ruleset.supports_save_proficiency,
            "proficiency_tiers": [
                {"key": t.key, "label": t.label, "value": t.value}
                for t in ruleset.proficiency_tiers
            ],
        },
        "equipment_slots": equipment_slots or [],
    }


def _coerce_optional_int(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _coerce_optional_str(raw, max_len=500):
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    return s[:max_len]


def apply_sheet_update(player, campaign, form):
    """Validate + write a sheet update. Returns (ok: bool, errors: list[str]).

    ``form`` is any mapping-like (request.form works directly). All writes go
    through the rule set whitelist; unknown keys are dropped silently (we do
    NOT raise because the HTML form legitimately submits the CSRF token and
    other non-stat fields).
    """
    errors = []
    if player is None:
        return False, ["Player not found."]

    current = get_or_default_sheet(player, campaign)
    ruleset = _ruleset_for_sheet(campaign, current)

    # Identity fields
    current["name"] = _coerce_optional_str(form.get("name"), max_len=100)
    current["class_name"] = _coerce_optional_str(form.get("class_name"), max_len=100)
    current["species"] = _coerce_optional_str(form.get("species"), max_len=100)
    current["notes"] = _coerce_optional_str(form.get("notes"), max_len=5000)

    level_raw = form.get("level")
    if level_raw is not None and str(level_raw).strip() != "":
        try:
            lvl = int(level_raw)
            if getattr(player, "is_npc", False):
                current["level"] = max(0, min(lvl, 999))
            else:
                from app.services.character_creation.campaign_settings import get_max_player_level

                campaign_id = getattr(campaign, "id", None) if campaign is not None else None
                level_cap = get_max_player_level(campaign_id)
                current["level"] = max(1, min(lvl, level_cap))
        except (TypeError, ValueError):
            pass

    # Abilities + defenses + saves all come through the same stat_<id> inputs.
    ability_keys = set(ruleset.ability_keys())
    derived_keys = {d.key for d in ruleset.derived}
    save_keys = set(ruleset.save_keys())

    new_abilities = {}
    new_defenses = {}

    for field_name, raw in form.items():
        if not field_name.startswith("stat_"):
            continue
        token = field_name[len("stat_"):]
        if "_" not in token:
            continue
        kind, _, key = token.partition("_")
        value = _coerce_optional_int(raw)
        if kind == "ability" and key in ability_keys:
            if value is None:
                continue
            if getattr(player, "is_npc", False):
                clamped = max(1, min(int(value), 999))
            else:
                clamped = ruleset.clamp_ability(value)
            if clamped is None:
                continue
            new_abilities[key] = clamped
        elif kind == "defense" and key in derived_keys:
            if value is None:
                continue
            # HP / AC / etc.: accept any non-negative int up to a generous cap.
            new_defenses[key] = max(0, min(value, 10000))
        elif kind == "save":
            # Saves are computed; no raw input stored. Ignore.
            continue

    current["abilities"] = new_abilities
    current["defenses"] = new_defenses

    # Save proficiency flags.
    if ruleset.supports_save_proficiency:
        new_save_flags = {}
        for key in save_keys:
            field = f"save_prof_flag_{key}"
            if form.get(field):
                new_save_flags[key] = 1.0
        current["save_prof_flags"] = new_save_flags
    else:
        current["save_prof_flags"] = {}

    # Skill proficiency tiers.
    if ruleset.supports_skill_proficiency:
        new_skill_tiers = {}
        valid_tier_values = set(ruleset.tier_values())
        for sk in ruleset.skills:
            flag_field = f"skill_prof_flag_{sk.key}"
            tier_field = f"skill_prof_tier_{sk.key}"
            if not form.get(flag_field):
                continue
            tier_raw = form.get(tier_field)
            tier_val = _coerce_optional_int(tier_raw)
            if tier_val is None or tier_val not in valid_tier_values:
                # Fall back to the first non-zero tier (e.g. "trained" /
                # "normal") so checking the box without picking a tier still
                # persists proficiency.
                fallback = next(
                    (t.value for t in ruleset.proficiency_tiers if t.value > 0),
                    None,
                )
                if fallback is None:
                    continue
                tier_val = fallback
            new_skill_tiers[sk.key] = tier_val
        current["skill_prof_tiers"] = new_skill_tiers
    else:
        current["skill_prof_tiers"] = {}

    if campaign is not None and (_system_type_of(campaign) or "").lower() == "dnd5e":
        spells_state = dict(current.get("spells") or {})
        for field, bucket in (
            ("spells_cantrips", "cantrips"),
            ("spells_prepared", "prepared"),
            ("spells_known", "known"),
        ):
            if field not in form and field.replace("spells_", "spell_") not in form:
                continue
            raw = form.get(field)
            if raw is None:
                raw = form.getlist(field) if hasattr(form, "getlist") else None
            if raw is None:
                continue
            if isinstance(raw, list):
                keys = [str(item).strip() for item in raw if str(item).strip()]
            else:
                keys = [part.strip() for part in str(raw).split(",") if part.strip()]
            spells_state[bucket] = keys[:64]
        current["spells"] = spells_state

    current["schema_version"] = SHEET_SCHEMA_VERSION
    current["system_type"] = ruleset.system_type

    # Persist (upsert).
    if campaign is not None:
        row = PlayerCharacterSheet.query.filter_by(
            player_id=player.id, campaign_id=campaign.id
        ).first()
    else:
        row = (
            PlayerCharacterSheet.query.filter(
                PlayerCharacterSheet.player_id == player.id,
                PlayerCharacterSheet.campaign_id.is_(None),
            ).first()
        )
    if row is None:
        row = PlayerCharacterSheet(
            player_id=player.id,
            campaign_id=campaign.id if campaign is not None else None,
            sheet_json=current,
        )
        db.session.add(row)
    else:
        row.sheet_json = current
        row.updated_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, [f"Failed to save character sheet: {exc}"]

    return (len(errors) == 0), errors


def apply_player_spell_selection(
    player,
    campaign,
    *,
    cantrips: list[str] | None = None,
    prepared: list[str] | None = None,
    known: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Persist player-selected cantrips / prepared / known spell keys."""
    errors: list[str] = []
    if campaign is None:
        return False, ["Join a campaign to manage spells."]
    if (_system_type_of(campaign) or "").lower() != "dnd5e":
        return False, ["Spell selection is only available in D&D 5e campaigns."]

    sheet = get_or_default_sheet(player, campaign)
    spell_details = _resolve_spell_details(campaign, sheet)
    class_details = _resolve_class_details(player, campaign, sheet)
    spell_details = _resolve_spell_details(campaign, sheet, class_details=class_details)
    catalog = spell_details.get("class_available") or []
    catalog_by_key = {
        str(entry.get("key") or "").strip().lower(): entry
        for entry in catalog
        if str(entry.get("key") or "").strip()
    }
    if not catalog_by_key:
        return False, ["No spells are available for your class in this campaign."]

    def _clean_keys(raw_keys: list[str] | None, *, level: int | None) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in raw_keys or []:
            key = str(raw or "").strip().lower()
            if not key or key in seen:
                continue
            entry = catalog_by_key.get(key)
            if entry is None:
                errors.append(f"Spell '{key}' is not on your class list.")
                continue
            spell_level = int(entry.get("level") or 0)
            if level == 0 and spell_level != 0:
                errors.append(f"'{entry.get('name') or key}' is not a cantrip.")
                continue
            if level == 1 and spell_level < 1:
                errors.append(f"'{entry.get('name') or key}' must be a leveled spell.")
                continue
            seen.add(key)
            cleaned.append(key)
            if len(cleaned) >= 64:
                break
        return cleaned

    cantrip_keys = _clean_keys(cantrips, level=0)
    prepared_keys = _clean_keys(prepared, level=1)
    known_keys = _clean_keys(known, level=1)

    if errors:
        return False, errors

    prepared_keys = [k for k in prepared_keys if k not in cantrip_keys]
    known_keys = [
        k for k in known_keys if k not in cantrip_keys and k not in prepared_keys
    ]

    from app.services.character_creation.progression_helpers import resolve_spell_list_limits

    limits = spell_details.get("limits") or resolve_spell_list_limits(spell_details.get("caps") or {})
    cap_labels = {
        "cantrips": "cantrips",
        "prepared": "prepared spells",
        "known": "spells known",
    }
    selections = {
        "cantrips": cantrip_keys,
        "prepared": prepared_keys,
        "known": known_keys,
    }
    for bucket, keys in selections.items():
        rule = limits.get(bucket) or {}
        if not rule.get("enabled"):
            if keys:
                errors.append(
                    f"Your class does not use the {cap_labels[bucket]} list at this level."
                )
            selections[bucket] = []
            continue
        max_allowed = int(rule.get("max") or 0)
        if len(keys) > max_allowed:
            errors.append(
                f"Choose at most {max_allowed} {cap_labels[bucket]} "
                f"(selected {len(keys)})."
            )

    if errors:
        return False, errors

    cantrip_keys = selections["cantrips"]
    prepared_keys = selections["prepared"]
    known_keys = selections["known"]

    current = dict(sheet)
    spells_state = dict(current.get("spells") or {})
    spells_state["cantrips"] = cantrip_keys
    spells_state["prepared"] = prepared_keys
    spells_state["known"] = known_keys
    current["spells"] = spells_state
    current["schema_version"] = SHEET_SCHEMA_VERSION
    current["system_type"] = "dnd5e"

    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    if row is None:
        row = PlayerCharacterSheet(
            player_id=player.id,
            campaign_id=campaign.id,
            sheet_json=current,
        )
        db.session.add(row)
    else:
        row.sheet_json = current
        row.updated_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, [f"Failed to save spells: {exc}"]

    return True, []
