"""Validate wizard payloads and build final D&D 5e vault character sheets."""

from __future__ import annotations

import random
import secrets
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Optional

from app.extensions import db
from app.models import Player, PlayerCharacterSheet
from app.services.character_creation.campaign_settings import (
    get_creation_settings,
    solo_default_creation_settings,
)
from app.services.character_creation.dnd5e_catalog import (
    ALL_SKILL_KEYS,
    catalog_entry_by_key,
    merged_creation_catalog,
)
from app.services.character_sheet_service import SHEET_SCHEMA_VERSION, _empty_sheet
from app.services.rulesets import get_ruleset

CREATION_SCHEMA_VERSION = 1
ROLL_DRAFT_SESSION_KEY = "dnd5e_creation_roll_draft"
FINALIZE_SESSION_KEY = "dnd5e_creation_finalize"
ROLL_DRAFT_TTL_MINUTES = 30

POINT_BUY_COSTS = {
    8: 0,
    9: 1,
    10: 2,
    11: 3,
    12: 4,
    13: 5,
    14: 7,
    15: 9,
}
POINT_BUY_MIN = 8
POINT_BUY_MAX = 15
GM_ABILITY_MIN = 1
GM_ABILITY_MAX = 999


class CreationValidationError(ValueError):
    """Raised when wizard input fails server-side validation."""


def _ability_keys() -> tuple[str, ...]:
    return tuple(a.key for a in get_ruleset("dnd5e").abilities)


def _clamp_ability_value(value: int, *, uncapped: bool = False) -> int:
    if uncapped:
        if value < GM_ABILITY_MIN:
            return GM_ABILITY_MIN
        if value > GM_ABILITY_MAX:
            return GM_ABILITY_MAX
        return value
    ruleset = get_ruleset("dnd5e")
    clamped = ruleset.clamp_ability(value)
    if clamped is None:
        raise CreationValidationError("Ability score is out of range.")
    return clamped


def roll_4d6_drop_lowest(rng: Optional[random.Random] = None) -> tuple[list[int], int]:
    source = rng or random.SystemRandom()
    dice = sorted(source.randint(1, 6) for _ in range(4))
    kept = dice[1:]
    return dice, sum(kept)


def point_buy_spend(scores: dict[str, int]) -> int:
    total = 0
    for score in scores.values():
        if score not in POINT_BUY_COSTS:
            raise CreationValidationError(
                f"Point-buy scores must be between {POINT_BUY_MIN} and {POINT_BUY_MAX} before species modifiers."
            )
        total += POINT_BUY_COSTS[score]
    return total


def _species_modifiers(
    species_entry: dict[str, Any],
    flex_assignments: Optional[dict[str, int]] = None,
) -> dict[str, int]:
    mods = {k: int(v) for k, v in (species_entry.get("ability_modifiers") or {}).items()}
    flex_count = int(species_entry.get("flex_ability_bonuses") or 0)
    if flex_count <= 0:
        return mods
    flex_assignments = flex_assignments or {}
    assigned = 0
    for ability, bonus in flex_assignments.items():
        if ability not in _ability_keys():
            raise CreationValidationError("Invalid flexible ability bonus target.")
        try:
            val = int(bonus)
        except (TypeError, ValueError):
            raise CreationValidationError("Flexible ability bonus must be an integer.")
        if val <= 0:
            continue
        mods[ability] = mods.get(ability, 0) + val
        assigned += 1
    if assigned != flex_count:
        raise CreationValidationError(
            f"Species requires exactly {flex_count} flexible ability bonus(es)."
        )
    return mods


def apply_species_modifiers(
    base_scores: dict[str, int],
    species_entry: dict[str, Any],
    *,
    flex_assignments: Optional[dict[str, int]] = None,
    uncapped: bool = False,
) -> dict[str, int]:
    mods = _species_modifiers(species_entry, flex_assignments)
    final_scores = {}
    for key in _ability_keys():
        base = int(base_scores.get(key, get_ruleset("dnd5e").ability_default))
        score = base + mods.get(key, 0)
        final_scores[key] = _clamp_ability_value(score, uncapped=uncapped)
    return final_scores


def _roll_draft_settings_key(settings: dict[str, Any]) -> str:
    return str(settings.get("settings_version") or "solo-default")


def get_roll_draft(session_obj: dict, user_id: int) -> Optional[dict[str, Any]]:
    draft = session_obj.get(ROLL_DRAFT_SESSION_KEY)
    if not isinstance(draft, dict):
        return None
    if draft.get("user_id") != user_id:
        return None
    expires = draft.get("expires_at")
    if expires:
        try:
            exp_dt = datetime.fromisoformat(str(expires))
            if datetime.utcnow() > exp_dt:
                return None
        except ValueError:
            return None
    return draft


def clear_roll_draft(session_obj: dict) -> None:
    session_obj.pop(ROLL_DRAFT_SESSION_KEY, None)
    session_obj.modified = True


def init_roll_draft(
    session_obj: dict,
    *,
    user_id: int,
    settings: dict[str, Any],
    campaign_scope: Optional[int],
) -> dict[str, Any]:
    draft = {
        "user_id": user_id,
        "campaign_scope": campaign_scope,
        "settings_version": _roll_draft_settings_key(settings),
        "ability_method": settings.get("ability_method"),
        "expires_at": (datetime.utcnow() + timedelta(minutes=ROLL_DRAFT_TTL_MINUTES)).isoformat(),
        "abilities": {},
        "draft_id": secrets.token_urlsafe(16),
    }
    session_obj[ROLL_DRAFT_SESSION_KEY] = draft
    session_obj.modified = True
    return draft


def issue_random_roll(
    session_obj: dict,
    *,
    user_id: int,
    settings: dict[str, Any],
    campaign_scope: Optional[int],
    ability_key: str,
    reroll: bool = False,
) -> dict[str, Any]:
    ability_key = (ability_key or "").strip().lower()
    if ability_key not in _ability_keys():
        raise CreationValidationError("Invalid ability key.")
    if settings.get("ability_method") != "random_roll":
        raise CreationValidationError("Campaign is not using random roll stat generation.")
    draft = get_roll_draft(session_obj, user_id)
    if (
        draft is None
        or draft.get("settings_version") != _roll_draft_settings_key(settings)
        or draft.get("campaign_scope") != campaign_scope
    ):
        draft = init_roll_draft(
            session_obj,
            user_id=user_id,
            settings=settings,
            campaign_scope=campaign_scope,
        )
    abilities = draft.setdefault("abilities", {})
    entry = abilities.get(ability_key) or {"rerolls_used": 0, "accepted": None, "history": []}
    max_rerolls = int(settings.get("random_rerolls_per_ability") or 0)
    if reroll:
        if entry.get("accepted") is None:
            raise CreationValidationError("Roll once before rerolling.")
        if int(entry.get("rerolls_used") or 0) >= max_rerolls:
            raise CreationValidationError("Reroll limit reached for this ability.")
        entry["rerolls_used"] = int(entry.get("rerolls_used") or 0) + 1
    dice, total = roll_4d6_drop_lowest()
    roll_record = {
        "dice": dice,
        "total": total,
        "reroll": bool(reroll),
        "issued_at": datetime.utcnow().isoformat(),
    }
    entry.setdefault("history", []).append(roll_record)
    entry["accepted"] = total
    abilities[ability_key] = entry
    session_obj[ROLL_DRAFT_SESSION_KEY] = draft
    session_obj.modified = True
    return {
        "ability_key": ability_key,
        "dice": dice,
        "total": total,
        "rerolls_used": entry["rerolls_used"],
        "rerolls_remaining": max(0, max_rerolls - int(entry["rerolls_used"] or 0)),
        "draft_id": draft.get("draft_id"),
    }


def _parse_base_scores(
    payload: dict[str, Any],
    settings: dict[str, Any],
    draft: Optional[dict],
    *,
    uncapped: bool = False,
) -> dict[str, int]:
    keys = _ability_keys()
    if uncapped:
        raw = payload.get("base_abilities") or payload.get("abilities") or {}
        if not isinstance(raw, dict):
            raise CreationValidationError("Ability scores must be an object.")
        scores = {}
        for key in keys:
            try:
                scores[key] = _clamp_ability_value(int(raw.get(key)), uncapped=True)
            except (TypeError, ValueError):
                raise CreationValidationError(f"Missing or invalid score for {key.upper()}.")
        return scores
    method = settings.get("ability_method")
    if method == "point_buy":
        raw = payload.get("base_abilities") or payload.get("abilities") or {}
        if not isinstance(raw, dict):
            raise CreationValidationError("Ability scores must be an object.")
        scores = {}
        for key in keys:
            try:
                scores[key] = int(raw.get(key))
            except (TypeError, ValueError):
                raise CreationValidationError(f"Missing or invalid score for {key.upper()}.")
        spend = point_buy_spend(scores)
        budget = int(settings.get("point_buy_budget") or 27)
        if spend > budget:
            raise CreationValidationError("Point-buy spend exceeds the allowed budget.")
        return scores
    if method == "random_roll":
        if draft is None:
            raise CreationValidationError("Random roll draft is missing or expired.")
        abilities = draft.get("abilities") or {}
        scores = {}
        for key in keys:
            entry = abilities.get(key)
            if not entry or entry.get("accepted") is None:
                raise CreationValidationError(f"Missing accepted roll for {key.upper()}.")
            max_rerolls = int(settings.get("random_rerolls_per_ability") or 0)
            if int(entry.get("rerolls_used") or 0) > max_rerolls:
                raise CreationValidationError("Reroll count exceeds campaign allowance.")
            scores[key] = int(entry["accepted"])
        return scores
    if method == "player_set":
        raw = payload.get("base_abilities") or payload.get("abilities") or {}
        if not isinstance(raw, dict):
            raise CreationValidationError("Ability scores must be an object.")
        ruleset = get_ruleset("dnd5e")
        scores = {}
        for key in keys:
            try:
                val = int(raw.get(key))
            except (TypeError, ValueError):
                raise CreationValidationError(f"Missing or invalid score for {key.upper()}.")
            clamped = ruleset.clamp_ability(val)
            if clamped is None:
                raise CreationValidationError(f"Score for {key.upper()} is out of range.")
            scores[key] = clamped
        return scores
    raise CreationValidationError("Unsupported ability generation method.")


def _merge_proficiencies(
    class_entry: dict[str, Any],
    background_entry: dict[str, Any],
    chosen_skills: list[str],
) -> tuple[dict[str, float], dict[str, int]]:
    save_flags = {key: 1.0 for key in (class_entry.get("save_proficiencies") or [])}
    skill_tiers: dict[str, int] = {}
    for skill in background_entry.get("skill_proficiencies") or []:
        sk = str(skill).strip().lower()
        if sk in ALL_SKILL_KEYS:
            skill_tiers[sk] = 2
    for skill in chosen_skills:
        sk = str(skill).strip().lower()
        if sk in ALL_SKILL_KEYS:
            skill_tiers[sk] = 2
    return save_flags, skill_tiers


from app.services.character_creation.dnd5e_species import DRAGONBORN_ANCESTRY_META

DRAGONBORN_ANCESTRY_OPTIONS = tuple(DRAGONBORN_ANCESTRY_META.keys())


def _validate_flex_assignments(
    species_entry: dict[str, Any],
    flex_assignments: dict[str, Any] | None,
) -> dict[str, int]:
    flex_count = int(species_entry.get("flex_ability_bonuses") or 0)
    if flex_count <= 0:
        return {}
    if not isinstance(flex_assignments, dict):
        raise CreationValidationError("Species flexible ability bonuses are required.")
    cleaned: dict[str, int] = {}
    for ability, bonus in flex_assignments.items():
        ab = str(ability or "").strip().lower()
        if ab not in _ability_keys():
            raise CreationValidationError("Invalid flexible ability bonus target.")
        try:
            val = int(bonus)
        except (TypeError, ValueError):
            raise CreationValidationError("Flexible ability bonus must be an integer.")
        if val <= 0:
            continue
        cleaned[ab] = val
    if len(cleaned) != flex_count:
        raise CreationValidationError(
            f"Species requires exactly {flex_count} flexible ability bonus(es)."
        )
    if len(set(cleaned.keys())) != len(cleaned):
        raise CreationValidationError("Flexible bonuses must target different abilities.")
    if species_entry.get("key") == "half-elf" and "cha" in cleaned:
        raise CreationValidationError("Half-Elf flexible bonuses cannot apply to Charisma.")
    return cleaned


def _validate_species_skill_choices(
    species_entry: dict[str, Any],
    chosen_skills: list[str] | None,
) -> list[str]:
    cfg = species_entry.get("species_skill_choices") or {}
    count = int(cfg.get("count") or 0)
    if count <= 0:
        return []
    options = cfg.get("options") or []
    if options == "any":
        option_set = set(ALL_SKILL_KEYS)
    else:
        option_set = {str(o).strip().lower() for o in options}
    cleaned: list[str] = []
    for skill in chosen_skills or []:
        sk = str(skill).strip().lower()
        if sk not in option_set:
            raise CreationValidationError(f"Skill {sk} is not allowed for this species.")
        if sk in cleaned:
            continue
        cleaned.append(sk)
    if len(cleaned) != count:
        raise CreationValidationError(
            f"Pick exactly {count} species skill(s); received {len(cleaned)}."
        )
    return cleaned


def _apply_species_skill_grants(
    species_entry: dict[str, Any],
    skill_tiers: dict[str, int],
    species_skill_choices: list[str],
) -> dict[str, int]:
    for skill in species_entry.get("species_skill_proficiencies") or []:
        sk = str(skill).strip().lower()
        if sk in ALL_SKILL_KEYS:
            skill_tiers[sk] = max(int(skill_tiers.get(sk, 0)), 2)
    for skill in species_skill_choices:
        skill_tiers[skill] = max(int(skill_tiers.get(skill, 0)), 2)
    return skill_tiers


def _validate_dragonborn_ancestry(
    species_entry: dict[str, Any],
    ancestry: str | None,
) -> str | None:
    if not species_entry.get("requires_dragonborn_ancestry"):
        return None
    choice = str(ancestry or "").strip().lower()
    if choice not in DRAGONBORN_ANCESTRY_OPTIONS:
        raise CreationValidationError("Choose a draconic ancestry damage type.")
    return choice


def _validate_class_skills(class_entry: dict[str, Any], chosen_skills: list[str]) -> list[str]:
    cfg = class_entry.get("skill_choices") or {}
    count = int(cfg.get("count") or 0)
    options = {str(o).strip().lower() for o in (cfg.get("options") or [])}
    cleaned = []
    for skill in chosen_skills:
        sk = str(skill).strip().lower()
        if sk not in options:
            raise CreationValidationError(f"Skill {sk} is not allowed for this class.")
        if sk in cleaned:
            continue
        cleaned.append(sk)
    if len(cleaned) != count:
        raise CreationValidationError(
            f"Pick exactly {count} class skill(s); received {len(cleaned)}."
        )
    return cleaned


def _starter_defenses(
    final_abilities: dict[str, int],
    class_entry: dict[str, Any],
    skill_tiers: dict[str, int],
) -> dict[str, int]:
    ruleset = get_ruleset("dnd5e")
    con_mod = ruleset.compute_ability_mod(final_abilities.get("con"))
    dex_mod = ruleset.compute_ability_mod(final_abilities.get("dex"))
    wis_mod = ruleset.compute_ability_mod(final_abilities.get("wis"))
    hit_die = int(class_entry.get("hit_die") or 8)
    hp_max = max(1, hit_die + con_mod)
    prof_bonus = ruleset.proficiency_bonus(1)
    perception_tier = skill_tiers.get("perception", 0)
    prof_component = prof_bonus if perception_tier >= 2 else int(prof_bonus * 0.5) if perception_tier == 1 else 0
    passive_perception = 10 + wis_mod + prof_component
    return {
        "hp_max": hp_max,
        "hp_current": hp_max,
        "ac": 10 + dex_mod,
        "initiative": dex_mod,
        "passive_perception": passive_perception,
    }


def build_final_sheet_json(
    payload: dict[str, Any],
    *,
    catalog: dict[str, Any],
    settings: dict[str, Any],
    roll_draft: Optional[dict[str, Any]] = None,
    uncapped: bool = False,
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()[:100] or None
    species_key = str(payload.get("species_key") or "").strip().lower()
    class_key = str(payload.get("class_key") or "").strip().lower()
    background_key = str(payload.get("background_key") or "").strip().lower()
    species_entry = catalog_entry_by_key(catalog, "species", species_key)
    class_entry = catalog_entry_by_key(catalog, "classes", class_key)
    background_entry = catalog_entry_by_key(catalog, "backgrounds", background_key)
    if species_entry is None:
        raise CreationValidationError("Invalid species selection.")
    if class_entry is None:
        raise CreationValidationError("Invalid class selection.")
    if background_entry is None:
        raise CreationValidationError("Invalid background selection.")

    flex_assignments = payload.get("species_flex_assignments")
    if flex_assignments is not None and not isinstance(flex_assignments, dict):
        raise CreationValidationError("Invalid species flexible bonus payload.")
    flex_assignments = _validate_flex_assignments(species_entry, flex_assignments)

    species_skill_choices = _validate_species_skill_choices(
        species_entry,
        payload.get("species_skill_choices") or [],
    )
    dragonborn_ancestry = _validate_dragonborn_ancestry(
        species_entry,
        payload.get("dragonborn_ancestry"),
    )
    dragonborn_meta = (
        DRAGONBORN_ANCESTRY_META.get(dragonborn_ancestry or "")
        if dragonborn_ancestry
        else None
    )

    chosen_skills = payload.get("class_skill_choices") or []
    if not isinstance(chosen_skills, list):
        raise CreationValidationError("Class skill choices must be a list.")
    validated_skills = _validate_class_skills(class_entry, [str(s) for s in chosen_skills])

    base_scores = _parse_base_scores(payload, settings, roll_draft, uncapped=uncapped)
    final_abilities = apply_species_modifiers(
        base_scores,
        species_entry,
        flex_assignments=flex_assignments,
        uncapped=uncapped,
    )
    save_flags, skill_tiers = _merge_proficiencies(
        class_entry, background_entry, validated_skills
    )
    skill_tiers = _apply_species_skill_grants(
        species_entry, skill_tiers, species_skill_choices
    )
    defenses = _starter_defenses(final_abilities, class_entry, skill_tiers)

    sheet = _empty_sheet("dnd5e")
    sheet["name"] = name
    sheet["species"] = species_entry.get("name")
    sheet["class_name"] = class_entry.get("name")
    sheet["level"] = 1
    sheet["abilities"] = final_abilities
    sheet["defenses"] = defenses
    sheet["save_prof_flags"] = save_flags
    sheet["skill_prof_tiers"] = skill_tiers
    sheet["traits"] = deepcopy(species_entry.get("traits") or [])
    trait_keys = list(species_entry.get("trait_keys") or [])
    if dragonborn_meta:
        resist_key = dragonborn_meta.get("trait_key")
        if resist_key and resist_key not in trait_keys:
            trait_keys.append(resist_key)
    sheet["creation"] = {
        "schema_version": CREATION_SCHEMA_VERSION,
        "species_key": species_key,
        "class_key": class_key,
        "background_key": background_key,
        "trait_keys": trait_keys,
        "class_skill_choices": validated_skills,
        "species_skill_choices": species_skill_choices,
        "dragonborn_ancestry": dragonborn_ancestry,
        "dragonborn_breath_summary": (dragonborn_meta or {}).get("breath_summary"),
        "dragonborn_breath_shape": (dragonborn_meta or {}).get("breath_shape"),
        "ability_method": "gm_set" if uncapped else settings.get("ability_method"),
        "point_buy_budget_used": int(settings.get("point_buy_budget") or 27),
        "point_buy_spend": point_buy_spend(base_scores)
        if not uncapped and settings.get("ability_method") == "point_buy"
        else None,
        "base_abilities": base_scores,
        "species_flex_assignments": flex_assignments or {},
        "roll_draft_id": (roll_draft or {}).get("draft_id"),
        "ability_rolls": deepcopy((roll_draft or {}).get("abilities") or {}),
        "species_source": species_entry.get("source") or species_entry.get("provenance"),
        "class_source": class_entry.get("source") or class_entry.get("provenance"),
        "settings_version": settings.get("settings_version"),
        "stat_modifiers": str(species_entry.get("stat_modifiers") or "").strip(),
    }
    from app.services.character_creation.level_progression_service import apply_level_one_progression

    apply_level_one_progression(sheet, class_entry)
    return sheet


def copy_vault_sheet_to_campaign(player_id: int, campaign_id: int) -> Optional[PlayerCharacterSheet]:
    """Copy vault sheet JSON to a campaign-scoped row when joining a campaign."""
    existing = PlayerCharacterSheet.query.filter_by(
        player_id=player_id, campaign_id=campaign_id
    ).first()
    if existing is not None:
        return existing
    vault = PlayerCharacterSheet.query.filter(
        PlayerCharacterSheet.player_id == player_id,
        PlayerCharacterSheet.campaign_id.is_(None),
    ).first()
    if vault is None or not isinstance(vault.sheet_json, dict):
        return None
    row = PlayerCharacterSheet(
        player_id=player_id,
        campaign_id=campaign_id,
        sheet_json=deepcopy(vault.sheet_json),
    )
    db.session.add(row)
    db.session.flush()
    return row


def get_finalize_result(session_obj: dict, user_id: int) -> Optional[dict[str, Any]]:
    result = session_obj.get(FINALIZE_SESSION_KEY)
    if not isinstance(result, dict):
        return None
    if result.get("user_id") != user_id:
        return None
    return result


def store_finalize_result(session_obj: dict, *, user_id: int, player_id: int, draft_token: str) -> None:
    session_obj[FINALIZE_SESSION_KEY] = {
        "user_id": user_id,
        "player_id": player_id,
        "draft_token": draft_token,
        "created_at": datetime.utcnow().isoformat(),
    }
    session_obj.modified = True


def finalize_vault_character(
    user_id: int,
    payload: dict[str, Any],
    *,
    campaign_id: Optional[int] = None,
    species_compendium: Optional[list[dict[str, Any]]] = None,
    classes_compendium: Optional[list[dict[str, Any]]] = None,
    character_options: Optional[dict[str, Any]] = None,
    roll_draft: Optional[dict[str, Any]] = None,
    draft_token: Optional[str] = None,
    existing_finalize: Optional[dict[str, Any]] = None,
) -> tuple[Player, dict[str, Any]]:
    """Build sheet JSON and insert Player + vault sheet. Caller must commit."""
    if existing_finalize and existing_finalize.get("draft_token") == draft_token:
        player = Player.query.filter_by(
            id=int(existing_finalize["player_id"]),
            user_id=user_id,
            is_npc=False,
        ).first()
        if player is None:
            raise CreationValidationError("Duplicate finalize token did not match a character.")
        sheet_row = PlayerCharacterSheet.query.filter(
            PlayerCharacterSheet.player_id == player.id,
            PlayerCharacterSheet.campaign_id.is_(None),
        ).first()
        if sheet_row is None:
            raise CreationValidationError("Duplicate finalize token did not match a sheet.")
        return player, deepcopy(sheet_row.sheet_json)

    settings = (
        get_creation_settings(campaign_id)
        if campaign_id is not None
        else solo_default_creation_settings()
    )
    catalog = merged_creation_catalog(
        campaign_id=campaign_id,
        species_compendium=species_compendium,
        classes_compendium=classes_compendium,
        character_options=character_options,
    )
    sheet_json = build_final_sheet_json(
        payload,
        catalog=catalog,
        settings=settings,
        roll_draft=roll_draft,
    )
    player = Player(
        user_id=user_id,
        campaign_id=None,
        currency=0,
        is_npc=False,
    )
    db.session.add(player)
    db.session.flush()
    row = PlayerCharacterSheet(
        player_id=player.id,
        campaign_id=None,
        sheet_json=sheet_json,
    )
    db.session.add(row)
    db.session.flush()
    return player, sheet_json


def wizard_catalog_for_user(
    *,
    campaign_id: Optional[int] = None,
    species_compendium: Optional[list[dict[str, Any]]] = None,
    classes_compendium: Optional[list[dict[str, Any]]] = None,
    character_options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    settings = (
        get_creation_settings(campaign_id)
        if campaign_id is not None
        else solo_default_creation_settings()
    )
    catalog = merged_creation_catalog(
        campaign_id=campaign_id,
        species_compendium=species_compendium,
        classes_compendium=classes_compendium,
        character_options=character_options,
    )
    return {
        "settings": settings,
        "catalog": catalog,
        "point_buy_costs": POINT_BUY_COSTS,
        "point_buy_range": {"min": POINT_BUY_MIN, "max": POINT_BUY_MAX},
        "dragonborn_ancestry_options": DRAGONBORN_ANCESTRY_META,
    }
