"""SRD-style level up / level down for D&D 5e character sheets."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from app.extensions import db
from app.models import Player, PlayerCharacterSheet
from app.services.character_creation.dnd5e_catalog import catalog_entry_by_key, merged_creation_catalog
from app.services.character_creation.progression_helpers import (
    apply_progression_row_to_sheet,
    apply_subclass_grants_for_level,
    class_progression_caps_from_row,
    progression_row_delta,
    resolve_spell_slots_from_row,
)
from app.services.character_creation.progression_helpers import (
    _pending_choices_from_row as _progression_pending_choices_from_row,
)
from app.services.classes_compendium_service import _default_class_entry, _level_row
from app.services.rulesets import get_ruleset

SRD_MAX_LEVEL = 20
SRD_MIN_LEVEL = 1
_LEDGER_KEY = "level_ledger"
_PENDING_CHOICES_KEY = "pending_level_choices"
_APPLIED_CHOICES_KEY = "applied_level_choices"
_SPELL_CHOICE_TYPES = frozenset({"spell", "spells", "cantrip", "cantrips"})


class LevelProgressionError(ValueError):
    """Raised when level up/down cannot be applied."""


def _system_type(campaign, sheet: Optional[dict[str, Any]] = None) -> str:
    if campaign is not None:
        return (getattr(campaign, "system_type", None) or "generic").strip().lower()
    if isinstance(sheet, dict):
        st = (sheet.get("system_type") or "").strip().lower()
        if st and st != "generic":
            return st
    return "generic"


def _class_entry_for_sheet(campaign_id: Optional[int], sheet: dict[str, Any]) -> Optional[dict[str, Any]]:
    creation = sheet.get("creation") or {}
    class_key = str(creation.get("class_key") or "").strip().lower()
    class_name = sheet.get("class_name")
    if campaign_id:
        from app.services.classes_compendium_service import _find_entry_for_character

        return _find_entry_for_character(
            campaign_id,
            class_key=class_key or None,
            class_name_fallback=class_name,
        )
    if not class_key:
        return None
    catalog = merged_creation_catalog()
    raw = catalog_entry_by_key(catalog, "classes", class_key)
    if raw is None:
        return None
    return _default_class_entry(raw, source="base")


def srd_average_hit_die_gain(hit_die: int, con_mod: int) -> int:
    """5e level-up HP: hit die average (rounded up) + CON modifier, minimum 1."""
    die = max(4, int(hit_die or 8))
    average = (die // 2) + 1
    return max(1, average + int(con_mod))


def _con_mod(sheet: dict[str, Any]) -> int:
    ruleset = get_ruleset("dnd5e")
    abilities = sheet.get("abilities") or {}
    return ruleset.compute_ability_mod(abilities.get("con"))


def _max_level_for(campaign) -> int:
    from app.services.character_creation.campaign_settings import get_max_player_level

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    return min(SRD_MAX_LEVEL, get_max_player_level(campaign_id))


def _current_level(sheet: dict[str, Any], *, campaign=None) -> int:
    cap = _max_level_for(campaign) if campaign is not None else SRD_MAX_LEVEL
    try:
        return max(SRD_MIN_LEVEL, min(cap, int(sheet.get("level") or 1)))
    except (TypeError, ValueError):
        return SRD_MIN_LEVEL


def _ledger(sheet: dict[str, Any]) -> list[dict[str, Any]]:
    raw = sheet.get(_LEDGER_KEY)
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _feature_names(features: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in features or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "description": str(item.get("description") or "").strip(),
            }
        )
    return out


def _is_asi_feature(name: str) -> bool:
    lowered = name.lower()
    return "ability score" in lowered and ("improvement" in lowered or "increase" in lowered)


def _player_choices_from_row(row: dict[str, Any], *, level: int) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    seen: set[str] = set()
    for choice in row.get("player_choices") or []:
        if not isinstance(choice, dict):
            continue
        choice_type = str(choice.get("type") or "custom").strip().lower()
        if choice_type in _SPELL_CHOICE_TYPES:
            continue
        title = str(choice.get("title") or choice.get("name") or "").strip()
        if not title:
            continue
        key = f"{choice_type}:{title.lower()}"
        if key in seen:
            continue
        seen.add(key)
        choices.append(
            {
                "level": level,
                "type": choice_type,
                "title": title,
                "description": str(choice.get("description") or "").strip(),
                "skipped": False,
            }
        )
    for feature in row.get("features") or []:
        if not isinstance(feature, dict):
            continue
        name = str(feature.get("name") or "").strip()
        if not name or not _is_asi_feature(name):
            continue
        key = f"ability_scores:{name.lower()}"
        if key in seen:
            continue
        seen.add(key)
        choices.append(
            {
                "level": level,
                "type": "ability_scores",
                "title": "Ability Score Improvement",
                "description": (
                    "Add +2 to one ability score, or +1 to two different scores, "
                    "on your full character sheet."
                ),
                "skipped": False,
            }
        )
    return choices


def _all_player_choices_from_row(row: dict[str, Any], *, level: int) -> list[dict[str, Any]]:
    """Trait pools, row player_choices, and feature-derived ASI for level-up wizards."""
    choices = _progression_pending_choices_from_row(row, level=level)
    if any(str(c.get("type") or "").strip().lower() == "ability_scores" for c in choices):
        return choices
    for feature in row.get("features") or []:
        if not isinstance(feature, dict):
            continue
        name = str(feature.get("name") or "").strip()
        if not name or not _is_asi_feature(name):
            continue
        choices.append(
            {
                "level": level,
                "type": "ability_scores",
                "title": "Ability Score Improvement",
                "description": (
                    "Add +2 to one ability score, or +1 to two different scores."
                ),
                "skipped": False,
            }
        )
        break
    return choices


_ASI_ABILITIES = frozenset({"str", "dex", "con", "int", "wis", "cha"})


def _validate_asi_increases(increases: dict[str, int]) -> str | None:
    if not increases:
        return "Select ability score increases totaling +2."
    total = sum(increases.values())
    if total != 2:
        return "Ability increases must total exactly +2."
    for ability, delta in increases.items():
        ab = str(ability or "").strip().lower()
        if ab not in _ASI_ABILITIES:
            return f"Invalid ability: {ability!r}."
        try:
            delta_int = int(delta)
        except (TypeError, ValueError):
            return "Each increase must be +1 or +2."
        if delta_int not in (1, 2):
            return "Each increase must be +1 or +2."
    if any(int(v) == 2 for v in increases.values()) and len(increases) != 1:
        return "+2 can only apply to a single ability."
    if len(increases) == 2 and not all(int(v) == 1 for v in increases.values()):
        return "Two ability increases must each be +1."
    return None


def _clear_pending_choice(
    sheet: dict[str, Any],
    *,
    level: int,
    choice_type: str,
    pool_tag: str | None = None,
    skipped: bool = False,
) -> bool:
    pending = list(sheet.get(_PENDING_CHOICES_KEY) or [])
    if not pending:
        return False
    needle_type = str(choice_type or "").strip().lower()
    needle_pool = str(pool_tag or "").strip().lower()
    updated = False
    kept: list[dict[str, Any]] = []
    for choice in pending:
        if not isinstance(choice, dict):
            kept.append(choice)
            continue
        if int(choice.get("level") or 0) != int(level):
            kept.append(choice)
            continue
        if str(choice.get("type") or "").strip().lower() != needle_type:
            kept.append(choice)
            continue
        if needle_type == "trait_pick" and str(choice.get("pool_tag") or "").strip().lower() != needle_pool:
            kept.append(choice)
            continue
        updated = True
        if skipped:
            choice = dict(choice)
            choice["skipped"] = True
            kept.append(choice)
    if updated:
        sheet[_PENDING_CHOICES_KEY] = kept
    return updated


def _applied_choices(sheet: dict[str, Any]) -> dict[str, Any]:
    raw = sheet.get(_APPLIED_CHOICES_KEY)
    if not isinstance(raw, dict):
        raw = {}
        sheet[_APPLIED_CHOICES_KEY] = raw
    return raw


def _record_applied_choice(sheet: dict[str, Any], key: str, record: dict[str, Any]) -> None:
    applied = _applied_choices(sheet)
    applied[str(key)] = deepcopy(record)


def _reverse_asi(sheet: dict[str, Any], increases: dict[str, int]) -> None:
    abilities = dict(sheet.get("abilities") or {})
    for ability, delta in (increases or {}).items():
        ab = str(ability or "").strip().lower()
        if ab not in _ASI_ABILITIES:
            continue
        try:
            current = int(abilities.get(ab) or 10)
            delta_int = int(delta)
        except (TypeError, ValueError):
            continue
        abilities[ab] = min(30, max(1, current - delta_int))
    sheet["abilities"] = abilities


def _remove_trait_keys_from_level(
    sheet: dict[str, Any],
    level: int,
    keys: list[str],
) -> None:
    remove_set = {
        str(key or "").strip().lower()
        for key in keys
        if str(key or "").strip()
    }
    if not remove_set:
        return
    selections = sheet.get("class_trait_selections")
    if not isinstance(selections, dict):
        return
    level_key = str(level)
    existing = [
        str(key or "").strip().lower()
        for key in (selections.get(level_key) or selections.get(level) or [])
        if str(key or "").strip()
    ]
    filtered = [key for key in existing if key not in remove_set]
    if filtered:
        selections[level_key] = filtered
    else:
        selections.pop(level_key, None)
        selections.pop(level, None)
    sheet["class_trait_selections"] = selections


def _reverse_subclass_choice(
    sheet: dict[str, Any],
    class_entry: dict[str, Any] | None,
    subclass_key: str,
) -> None:
    creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
    cleaned = str(subclass_key or "").strip().lower()
    if not cleaned or str(creation.get("subclass_key") or "").strip().lower() != cleaned:
        return
    creation.pop("subclass_key", None)
    sheet["creation"] = creation
    if not class_entry:
        return
    from app.services.classes_compendium_service import find_subclass_on_class

    subclass = find_subclass_on_class(class_entry, cleaned)
    if not subclass:
        return
    for grant in subclass.get("feature_grants") or []:
        if not isinstance(grant, dict):
            continue
        try:
            grant_level = int(grant.get("level") or 0)
        except (TypeError, ValueError):
            continue
        trait_keys = [
            str(key or "").strip().lower()
            for key in (grant.get("trait_keys") or [])
            if str(key or "").strip()
        ]
        _remove_trait_keys_from_level(sheet, grant_level, trait_keys)


def _applied_choice_keys_for_level(sheet: dict[str, Any], level: int) -> list[str]:
    applied = _applied_choices(sheet)
    keys: list[str] = []
    for key, record in applied.items():
        if not isinstance(record, dict):
            continue
        choice_type = str(record.get("type") or "").strip().lower()
        if choice_type == "trait_pick":
            if int(record.get("level") or 0) == int(level):
                keys.append(str(key))
        elif choice_type == "subclass":
            pick_level = int(record.get("pick_level") or record.get("level") or 0)
            if pick_level == int(level):
                keys.append(str(key))
        elif str(key) == str(level) or int(key) == int(level):
            keys.append(str(key))
    return keys


def _reverse_applied_choices_for_level(
    sheet: dict[str, Any],
    class_entry: dict[str, Any] | None,
    level: int,
) -> None:
    applied = _applied_choices(sheet)
    for key in _applied_choice_keys_for_level(sheet, level):
        record = applied.pop(key, None)
        if not isinstance(record, dict):
            continue
        choice_type = str(record.get("type") or "").strip().lower()
        if choice_type == "ability_scores":
            _reverse_asi(sheet, record.get("increases") or {})
        elif choice_type == "subclass":
            _reverse_subclass_choice(sheet, class_entry, str(record.get("subclass_key") or ""))
        elif choice_type == "trait_pick":
            _remove_trait_keys_from_level(
                sheet,
                int(record.get("level") or level),
                list(record.get("trait_keys") or []),
            )


def _restore_pending_choices_for_level(
    sheet: dict[str, Any],
    entry: dict[str, Any],
    level: int,
) -> None:
    restored: list[dict[str, Any]] = []
    for choice in entry.get("player_choices") or []:
        if not isinstance(choice, dict):
            continue
        if int(choice.get("level") or 0) != int(level):
            continue
        copy = dict(choice)
        copy["skipped"] = False
        restored.append(copy)
    pending = [
        choice
        for choice in (sheet.get(_PENDING_CHOICES_KEY) or [])
        if not (isinstance(choice, dict) and int(choice.get("level") or 0) == int(level))
    ]
    pending.extend(restored)
    sheet[_PENDING_CHOICES_KEY] = pending


def enrich_level_up_summary_for_wizard(
    player: Player,
    campaign,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Attach wizard steps, ability scores, and trait options for the level-up UI."""
    if not isinstance(summary, dict):
        return summary
    sheet = _load_sheet(player, campaign)
    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    abilities = {
        ab: int((sheet.get("abilities") or {}).get(ab) or 10)
        for ab in ("str", "dex", "con", "int", "wis", "cha")
    }
    summary = deepcopy(summary)
    summary["abilities"] = abilities

    wizard_steps: list[dict[str, Any]] = [
        {
            "type": "summary",
            "title": f"Level {summary.get('level')}",
            "description": "Your character advanced. Review what changed, then complete any choices.",
        }
    ]

    from app.services.traits_compendium_service import (
        _prerequisites_met,
        list_traits_by_tag,
        trait_prerequisite_context_from_sheet,
    )

    ctx = trait_prerequisite_context_from_sheet(sheet)
    for choice in summary.get("player_choices") or []:
        if not isinstance(choice, dict):
            continue
        step = deepcopy(choice)
        choice_type = str(step.get("type") or "custom").strip().lower()
        if choice_type == "trait_pick" and campaign_id is not None:
            pool_tag = str(step.get("pool_tag") or "").strip().lower()
            try:
                pick_count = max(1, int(step.get("pick") or 1))
            except (TypeError, ValueError):
                pick_count = 1
            step["pick_count"] = pick_count
            options: list[dict[str, str]] = []
            for entry in list_traits_by_tag(campaign_id, pool_tag):
                prereqs = entry.get("prerequisites") or {}
                if prereqs and not _prerequisites_met(prereqs, ctx):
                    continue
                options.append(
                    {
                        "key": str(entry.get("key") or "").strip().lower(),
                        "name": str(entry.get("name") or entry.get("key") or "Trait"),
                        "summary": str(entry.get("summary") or entry.get("notes") or "")[:500],
                    }
                )
            step["options"] = options
        elif choice_type == "subclass" and campaign_id is not None:
            class_entry = _enrich_class_entry(_class_entry_for_sheet(campaign_id, sheet) or {})
            from app.services.classes_compendium_service import list_visible_subclasses_for_class

            step["options"] = [
                {
                    "key": str(row.get("key") or "").strip().lower(),
                    "name": str(row.get("name") or row.get("key") or "Subclass"),
                    "tagline": str(row.get("tagline") or "")[:120],
                    "summary": str(row.get("summary") or "")[:500],
                }
                for row in list_visible_subclasses_for_class(class_entry)
            ]
        elif choice_type == "ability_scores":
            step["abilities"] = dict(abilities)
        wizard_steps.append(step)

    summary["wizard_steps"] = wizard_steps
    return summary


def level_up_summary_needs_wizard(summary: dict[str, Any]) -> bool:
    """True when the post-level-up wizard should open (player choices remain)."""
    if not isinstance(summary, dict):
        return False
    for step in summary.get("wizard_steps") or []:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type") or "").strip().lower()
        if step_type == "summary":
            continue
        if step_type == "ability_scores":
            return True
        if step_type in ("trait_pick", "subclass"):
            if step.get("options"):
                return True
            continue
        return True
    return False


def apply_ability_score_improvement(
    player: Player,
    campaign,
    *,
    level: int,
    increases: dict[str, int],
) -> tuple[bool, str]:
    """Apply ASI (+2 one or +1 two) and clear the pending choice for ``level``."""
    sheet = _load_sheet(player, campaign)
    if _system_type(campaign, sheet) != "dnd5e":
        return False, "Ability score improvements are only available in D&D 5e campaigns."

    clean: dict[str, int] = {}
    for ability, delta in (increases or {}).items():
        ab = str(ability or "").strip().lower()
        if not ab:
            continue
        try:
            clean[ab] = int(delta)
        except (TypeError, ValueError):
            return False, "Invalid ability increase."
    err = _validate_asi_increases(clean)
    if err:
        return False, err

    abilities = dict(sheet.get("abilities") or {})
    for ab, delta in clean.items():
        try:
            current = int(abilities.get(ab) or 10)
        except (TypeError, ValueError):
            current = 10
        abilities[ab] = min(30, max(1, current + delta))
    sheet["abilities"] = abilities
    _clear_pending_choice(sheet, level=level, choice_type="ability_scores")
    _record_applied_choice(
        sheet,
        str(level),
        {"type": "ability_scores", "increases": dict(clean)},
    )

    try:
        _persist_sheet(player, campaign, sheet)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, f"Failed to save ability scores: {exc}"
    return True, "Ability scores updated."


def skip_pending_level_choice(
    player: Player,
    campaign,
    *,
    level: int,
    choice_type: str,
    pool_tag: str | None = None,
) -> tuple[bool, str]:
    """Mark one pending level choice as skipped."""
    sheet = _load_sheet(player, campaign)
    if not _clear_pending_choice(
        sheet,
        level=level,
        choice_type=choice_type,
        pool_tag=pool_tag,
        skipped=True,
    ):
        return True, "No matching pending choice."
    try:
        _persist_sheet(player, campaign, sheet)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, f"Failed to save: {exc}"
    return True, "Choice skipped for now."


def _ledger_entry_for_level(
    class_entry: dict[str, Any],
    *,
    target_level: int,
    sheet: dict[str, Any],
) -> dict[str, Any]:
    row = _level_row(class_entry, target_level) or {}
    hit_die = int(class_entry.get("hit_die") or 8)
    hp_gain = srd_average_hit_die_gain(hit_die, _con_mod(sheet))
    spell_slots = resolve_spell_slots_from_row(row)
    caps = class_progression_caps_from_row(row)
    return {
        "level": target_level,
        "hp_gain": hp_gain,
        "features": _feature_names(row.get("features") or []),
        "spell_slots": spell_slots,
        "proficiency_bonus": caps.get("proficiency_bonus", int(row.get("proficiency_bonus") or 2)),
        "class_progression": caps,
        "class_resources": dict(row.get("resources") or {}),
        "player_choices": _all_player_choices_from_row(row, level=target_level),
    }


def _apply_hp_delta(sheet: dict[str, Any], delta: int) -> None:
    defenses = dict(sheet.get("defenses") or {})
    try:
        hp_max = int(defenses.get("hp_max") or 0)
    except (TypeError, ValueError):
        hp_max = 0
    try:
        hp_current = int(defenses.get("hp_current") if defenses.get("hp_current") is not None else hp_max)
    except (TypeError, ValueError):
        hp_current = hp_max
    new_max = max(1, hp_max + delta)
    new_current = max(0, min(new_max, hp_current + delta))
    defenses["hp_max"] = new_max
    defenses["hp_current"] = new_current
    sheet["defenses"] = defenses


def _cap_messages(caps: dict[str, Any], *, gained: bool) -> list[str]:
    messages: list[str] = []
    labels = {
        "cantrips_known": "Cantrips known",
        "spells_known": "Spells known",
        "spells_prepared": "Spells prepared",
        "invocations_known": "Invocations known",
    }
    verb = "Now" if gained else "Reverted to"
    for key, label in labels.items():
        if key in caps:
            messages.append(f"{verb} {label.lower()}: {caps[key]}.")
    return messages


def _messages_for_entry(entry: dict[str, Any], *, gained: bool) -> list[str]:
    messages: list[str] = []
    level = entry.get("level")
    hp_gain = int(entry.get("hp_gain") or 0)
    verb = "Gained" if gained else "Removed"
    if hp_gain and gained:
        messages.append(f"Hit points increased by {hp_gain}.")
    elif hp_gain and not gained:
        messages.append(f"Hit points decreased by {hp_gain}.")
    for feature in entry.get("features") or []:
        if not isinstance(feature, dict):
            continue
        name = feature.get("name") or "Class feature"
        desc = feature.get("description") or ""
        if _is_asi_feature(str(name)):
            if gained:
                messages.append(
                    "Ability Score Improvement: add +2 to one ability or +1 to two "
                    "abilities on your character sheet."
                )
            else:
                messages.append(
                    "Ability Score Improvement from this level was reversed on your sheet."
                )
            continue
        line = f"{verb}: {name}"
        if desc:
            line += f" — {desc}"
        messages.append(line)
    spell_slots = entry.get("spell_slots") or {}
    if spell_slots:
        slots_text = ", ".join(
            f"level {slot_level}: {count}"
            for slot_level, count in sorted(spell_slots.items(), key=lambda pair: int(pair[0]))
            if int(count or 0) > 0
        )
        if slots_text:
            if gained:
                messages.append(f"Spell slots at level {level}: {slots_text}.")
            else:
                messages.append(f"Reverted spell slots from level {level}.")
    messages.extend(_cap_messages(entry.get("class_progression") or {}, gained=gained))
    resources = entry.get("class_resources") or {}
    if resources and gained:
        res_text = ", ".join(f"{key}: {value}" for key, value in sorted(resources.items()))
        if res_text:
            messages.append(f"Class resources: {res_text}.")
    return messages


def _level_up_summary(entry: dict[str, Any], *, new_level: int, gained: bool) -> dict[str, Any]:
    features = entry.get("features") or []
    return {
        "level": new_level,
        "hp_gain": int(entry.get("hp_gain") or 0),
        "features": features,
        "spell_slots": dict(entry.get("spell_slots") or {}),
        "class_progression": dict(entry.get("class_progression") or {}),
        "class_resources": dict(entry.get("class_resources") or {}),
        "player_choices": list(entry.get("player_choices") or []),
        "messages": _messages_for_entry(entry, gained=gained),
    }


def preview_level_up(player: Player, campaign) -> dict[str, Any]:
    """Preview the next level before the player commits to leveling up."""
    sheet = _load_sheet(player, campaign)
    if _system_type(campaign, sheet) != "dnd5e":
        return {
            "available": False,
            "message": "Level progression is only available in D&D 5e campaigns.",
        }

    current = _current_level(sheet, campaign=campaign)
    max_level = _max_level_for(campaign)
    if current >= max_level:
        return {
            "available": False,
            "message": f"Already at maximum level ({max_level}).",
            "current_level": current,
            "max_player_level": max_level,
        }

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    class_entry = _class_entry_for_sheet(campaign_id, sheet)
    if class_entry is None:
        return {
            "available": False,
            "message": "Class progression data was not found for this character.",
            "current_level": current,
        }

    class_entry = _enrich_class_entry(class_entry)
    next_level = current + 1
    entry = _ledger_entry_for_level(class_entry, target_level=next_level, sheet=sheet)
    current_row = _level_row(class_entry, current) or {}
    next_row = _level_row(class_entry, next_level) or {}
    deltas = progression_row_delta(current_row, next_row)
    next_slots = dict(entry.get("spell_slots") or {})
    prev_slots = resolve_spell_slots_from_row(current_row)
    slot_changes = {
        key: next_slots[key]
        for key in next_slots
        if int(next_slots.get(key) or 0) > int(prev_slots.get(key) or 0)
    }

    return {
        "available": True,
        "message": None,
        "current_level": current,
        "next_level": next_level,
        "max_player_level": max_level,
        "hp_gain": int(entry.get("hp_gain") or 0),
        "hit_die": int(class_entry.get("hit_die") or 8),
        "features": entry.get("features") or [],
        "spell_slots": next_slots,
        "spell_slot_changes": slot_changes or deltas.get("spell_slot_changes") or {},
        "proficiency_bonus": int(entry.get("proficiency_bonus") or 2),
        "class_progression": dict(entry.get("class_progression") or {}),
        "progression_deltas": deltas,
        "player_choices": entry.get("player_choices") or [],
    }


def skip_pending_level_choices(player: Player, campaign, *, level: Optional[int] = None) -> tuple[bool, str]:
    """Mark pending level choices as skipped for the given level (or all)."""
    sheet = _load_sheet(player, campaign)
    pending = list(sheet.get(_PENDING_CHOICES_KEY) or [])
    if not pending:
        return True, "No pending choices."
    updated = False
    for choice in pending:
        if not isinstance(choice, dict) or choice.get("skipped"):
            continue
        if level is None or int(choice.get("level") or 0) == int(level):
            choice["skipped"] = True
            updated = True
    if not updated:
        return True, "No matching pending choices."
    sheet[_PENDING_CHOICES_KEY] = pending
    try:
        _persist_sheet(player, campaign, sheet)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, f"Failed to save: {exc}"
    return True, "Choices skipped for now."


def apply_class_trait_choices(
    player: Player,
    campaign,
    *,
    level: int,
    trait_keys: list[str],
    pool_tag: str | None = None,
) -> tuple[bool, str]:
    """Validate and persist player trait picks for a level (trait pools)."""
    from app.services.classes_compendium_service import _level_row
    from app.services.traits_compendium_service import (
        list_traits_by_tag,
        trait_prerequisite_context_from_sheet,
    )

    sheet = _load_sheet(player, campaign)
    if _system_type(campaign, sheet) != "dnd5e":
        return False, "Trait choices are only available in D&D 5e campaigns."

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    class_entry = _enrich_class_entry(_class_entry_for_sheet(campaign_id, sheet) or {})
    row = _level_row(class_entry, level) or {}
    pools = [
        pool
        for pool in (row.get("trait_pools") or [])
        if isinstance(pool, dict)
        and str(pool.get("pool_tag") or "").strip().lower()
        == str(pool_tag or "").strip().lower()
    ]
    if not pools:
        return False, "No trait choices for this level."

    pool = pools[0]
    try:
        pick_count = max(1, int(pool.get("pick") or 1))
    except (TypeError, ValueError):
        pick_count = 1
    cleaned = [str(key or "").strip().lower() for key in trait_keys if str(key or "").strip()]
    if len(cleaned) != pick_count:
        return False, f"Select exactly {pick_count} trait(s)."

    if campaign_id is None:
        return False, "Campaign context is required for trait choices."

    allowed = {
        str(entry.get("key") or "").strip().lower()
        for entry in list_traits_by_tag(campaign_id, str(pool_tag or ""))
    }
    if not allowed:
        return False, "No traits are configured for this choice pool."

    ctx = trait_prerequisite_context_from_sheet(sheet)
    from app.services.traits_compendium_service import ensure_traits_compendium

    by_key = {
        str(entry.get("key") or "").strip().lower(): entry
        for entry in ensure_traits_compendium(campaign_id)
    }
    for key in cleaned:
        if key not in allowed:
            return False, f"Trait {key!r} is not allowed for this choice."
        trait = by_key.get(key) or {}
        prereqs = trait.get("prerequisites") or {}
        if prereqs:
            from app.services.traits_compendium_service import _prerequisites_met

            if not _prerequisites_met(prereqs, ctx):
                return False, f"Prerequisites not met for trait {trait.get('name') or key}."

    selections = sheet.get("class_trait_selections")
    if not isinstance(selections, dict):
        selections = {}
    level_key = str(level)
    existing = [
        str(key or "").strip().lower()
        for key in (selections.get(level_key) or [])
        if str(key or "").strip()
    ]
    merged = list(dict.fromkeys(existing + cleaned))
    selections[level_key] = merged
    sheet["class_trait_selections"] = selections

    pending = [
        choice
        for choice in (sheet.get(_PENDING_CHOICES_KEY) or [])
        if not (
            isinstance(choice, dict)
            and int(choice.get("level") or 0) == int(level)
            and str(choice.get("type") or "") == "trait_pick"
            and str(choice.get("pool_tag") or "") == str(pool_tag or "")
        )
    ]
    sheet[_PENDING_CHOICES_KEY] = pending
    _record_applied_choice(
        sheet,
        f"{level}:{pool_tag}",
        {
            "type": "trait_pick",
            "level": int(level),
            "pool_tag": str(pool_tag or ""),
            "trait_keys": list(cleaned),
        },
    )

    try:
        _persist_sheet(player, campaign, sheet)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, f"Failed to save trait choices: {exc}"
    return True, "Trait choices saved."


def apply_subclass_choice(
    player: Player,
    campaign,
    *,
    level: int,
    subclass_key: str,
) -> tuple[bool, str]:
    """Validate and persist player subclass selection."""
    from app.services.classes_compendium_service import (
        find_subclass_on_class,
        list_visible_subclasses_for_class,
    )
    from app.services.character_creation.progression_helpers import apply_trait_keys_at_level

    sheet = _load_sheet(player, campaign)
    if _system_type(campaign, sheet) != "dnd5e":
        return False, "Subclass choices are only available in D&D 5e campaigns."

    creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
    existing = str(creation.get("subclass_key") or "").strip().lower()
    cleaned = str(subclass_key or "").strip().lower()
    if not cleaned:
        return False, "Subclass is required."
    if existing and existing != cleaned:
        return False, "Subclass is already chosen and cannot be changed."

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    class_entry = _enrich_class_entry(_class_entry_for_sheet(campaign_id, sheet) or {})
    if not class_entry:
        return False, "Class data was not found for this character."

    visible = list_visible_subclasses_for_class(
        class_entry,
        owner_subclass_key=cleaned,
    )
    if not any(str(row.get("key") or "").strip().lower() == cleaned for row in visible):
        return False, "That subclass is not available."

    subclass_row = find_subclass_on_class(class_entry, cleaned)
    if not subclass_row:
        return False, "Invalid subclass."

    try:
        pick_level = max(1, int(subclass_row.get("pick_level") or level))
    except (TypeError, ValueError):
        pick_level = level
    current_level = _current_level(sheet, campaign=campaign)
    if int(level) != pick_level and current_level < pick_level:
        return False, f"Subclass choice is available at level {pick_level}."

    if existing:
        return False, "Subclass is already chosen."

    creation["subclass_key"] = cleaned
    sheet["creation"] = creation

    for grant in subclass_row.get("feature_grants") or []:
        if not isinstance(grant, dict):
            continue
        try:
            grant_level = int(grant.get("level") or 0)
        except (TypeError, ValueError):
            continue
        if grant_level <= current_level:
            apply_trait_keys_at_level(
                sheet,
                list(grant.get("trait_keys") or []),
                grant_level,
            )

    pending = [
        choice
        for choice in (sheet.get(_PENDING_CHOICES_KEY) or [])
        if not (
            isinstance(choice, dict)
            and str(choice.get("type") or "").strip().lower() == "subclass"
            and int(choice.get("level") or 0) == pick_level
        )
    ]
    sheet[_PENDING_CHOICES_KEY] = pending
    _record_applied_choice(
        sheet,
        str(pick_level),
        {
            "type": "subclass",
            "pick_level": pick_level,
            "subclass_key": cleaned,
        },
    )

    try:
        _persist_sheet(player, campaign, sheet)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, f"Failed to save subclass choice: {exc}"
    return True, "Subclass choice saved."


def _persist_sheet(player: Player, campaign, sheet: dict[str, Any]) -> None:
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
            sheet_json=deepcopy(sheet),
        )
        db.session.add(row)
    else:
        row.sheet_json = deepcopy(sheet)
        row.updated_at = datetime.utcnow()


def apply_level_up(player: Player, campaign) -> tuple[bool, list[str], dict[str, Any] | None]:
    """Increment level and apply SRD progression for the new level."""
    sheet = _load_sheet(player, campaign)
    if _system_type(campaign, sheet) != "dnd5e":
        return False, ["Level progression is only available in D&D 5e campaigns."], None

    current = _current_level(sheet, campaign=campaign)
    max_level = _max_level_for(campaign)
    if current >= max_level:
        return False, [f"Already at maximum level ({max_level})."], None

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    class_entry = _class_entry_for_sheet(campaign_id, sheet)
    if class_entry is None:
        return False, ["Class progression data was not found for this character."], None

    class_entry = _enrich_class_entry(class_entry)
    new_level = current + 1
    row = _level_row(class_entry, new_level) or {}
    entry = _ledger_entry_for_level(class_entry, target_level=new_level, sheet=sheet)
    ledger = _ledger(sheet)
    ledger.append(entry)
    sheet[_LEDGER_KEY] = ledger
    sheet["level"] = new_level

    apply_progression_row_to_sheet(sheet, row, level=new_level, append_pending_choices=True)
    apply_subclass_grants_for_level(sheet, class_entry, new_level)
    _apply_hp_delta(sheet, int(entry.get("hp_gain") or 0))

    summary = _level_up_summary(entry, new_level=new_level, gained=True)
    messages = [f"Advanced to level {new_level}."]
    messages.extend(summary["messages"])

    try:
        _persist_sheet(player, campaign, sheet)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, [f"Failed to save level change: {exc}"], None

    return True, messages, summary


def apply_level_down(player: Player, campaign) -> tuple[bool, list[str]]:
    """Decrement level and reverse the last applied progression entry."""
    sheet = _load_sheet(player, campaign)
    if _system_type(campaign, sheet) != "dnd5e":
        return False, ["Level progression is only available in D&D 5e campaigns."]

    current = _current_level(sheet, campaign=campaign)
    if current <= SRD_MIN_LEVEL:
        return False, ["Already at level 1."]

    campaign_id = getattr(campaign, "id", None) if campaign is not None else None
    class_entry = _class_entry_for_sheet(campaign_id, sheet)
    ledger = _ledger(sheet)

    if ledger and int(ledger[-1].get("level") or 0) == current:
        entry = ledger.pop()
    elif class_entry is not None:
        entry = _ledger_entry_for_level(class_entry, target_level=current, sheet=sheet)
    else:
        return False, ["No level history found to reverse."]

    sheet[_LEDGER_KEY] = ledger
    new_level = current - 1
    sheet["level"] = new_level
    _apply_hp_delta(sheet, -int(entry.get("hp_gain") or 0))

    if class_entry is not None:
        class_entry = _enrich_class_entry(class_entry)

    _reverse_applied_choices_for_level(sheet, class_entry, current)
    selections = sheet.get("class_trait_selections")
    if isinstance(selections, dict):
        selections.pop(str(current), None)
        selections.pop(current, None)
        sheet["class_trait_selections"] = selections
    _restore_pending_choices_for_level(sheet, entry, current)

    if class_entry is not None:
        prev_row = _level_row(class_entry, new_level) or {}
        apply_progression_row_to_sheet(sheet, prev_row, level=new_level)
    elif ledger:
        prev_entry = ledger[-1]
        sheet["spell_slots"] = dict(prev_entry.get("spell_slots") or {})
        sheet["class_progression"] = dict(prev_entry.get("class_progression") or {})
        sheet["class_resources"] = dict(prev_entry.get("class_resources") or {})
    else:
        sheet.pop("spell_slots", None)
        sheet.pop("class_progression", None)
        sheet.pop("class_resources", None)

    messages = [f"Returned to level {new_level}."]
    messages.extend(_messages_for_entry(entry, gained=False))

    try:
        _persist_sheet(player, campaign, sheet)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, [f"Failed to save level change: {exc}"]
    return True, messages


def _enrich_class_entry(class_entry: dict[str, Any]) -> dict[str, Any]:
    """Fill SRD progression when catalog entry is still a shell."""
    key = str(class_entry.get("key") or "").strip().lower()
    row = _level_row(class_entry, 1) or {}
    has_data = bool(
        resolve_spell_slots_from_row(row)
        or row.get("cantrips_known") is not None
        or len(row.get("features") or []) > 1
    )
    if has_data:
        return class_entry
    from app.services.character_creation.dnd5e_srd_class_progression import SRD_CLASS_PROGRESSIONS

    seed = SRD_CLASS_PROGRESSIONS.get(key)
    if not seed:
        return class_entry
    merged = deepcopy(class_entry)
    if seed.get("spellcasting"):
        merged["spellcasting"] = deepcopy(seed["spellcasting"])
    if seed.get("level_progression"):
        merged["level_progression"] = deepcopy(seed["level_progression"])
    from app.services.character_creation.dnd5e_srd_subclasses import CORE_SUBCLASSES_BY_CLASS
    from app.services.classes_compendium_service import _ensure_subclass_player_choice

    sub_seeds = CORE_SUBCLASSES_BY_CLASS.get(key)
    if sub_seeds and not merged.get("subclasses"):
        merged["subclasses"] = [deepcopy(row) for row in sub_seeds]
        _ensure_subclass_player_choice(merged)
    return merged


def apply_level_one_progression(sheet: dict[str, Any], class_entry: dict[str, Any]) -> None:
    """Apply level 1 class progression row during character creation."""
    entry = _enrich_class_entry(class_entry)
    row = _level_row(entry, 1) or {}
    apply_progression_row_to_sheet(sheet, row, level=1, append_pending_choices=True)


def _load_sheet(player: Player, campaign) -> dict[str, Any]:
    from app.services.character_sheet_service import get_or_default_sheet

    return deepcopy(get_or_default_sheet(player, campaign))
