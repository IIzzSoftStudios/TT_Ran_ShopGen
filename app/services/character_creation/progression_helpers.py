"""Shared helpers for class level progression rows and sheet application."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

_SPELLCASTING_TYPES = frozenset({"none", "full", "half", "third", "pact", "known"})
_PLAYER_CHOICE_TYPES = frozenset(
    {
        "ability_scores",
        "invocations",
        "pact_boon",
        "mystic_arcanum",
        "subclass",
        "feat",
        "custom",
        "trait_pick",
    }
)


def proficiency_bonus(level: int) -> int:
    if level <= 0:
        return 2
    return 2 + ((level - 1) // 4)


def resolve_spell_slots_from_row(row: dict[str, Any] | None) -> dict[str, int]:
    """Convert pact_magic or spell_slots on a progression row to a slot map."""
    if not isinstance(row, dict):
        return {}
    pact = row.get("pact_magic")
    if isinstance(pact, dict):
        try:
            count = int(pact.get("slots") or 0)
            slot_level = int(pact.get("slot_level") or 1)
        except (TypeError, ValueError):
            count, slot_level = 0, 1
        if count > 0 and slot_level > 0:
            return {str(slot_level): count}
    out: dict[str, int] = {}
    for key, value in (row.get("spell_slots") or {}).items():
        try:
            slots = int(value)
        except (TypeError, ValueError):
            continue
        if slots > 0:
            out[str(key)] = slots
    return out


def class_progression_caps_from_row(row: dict[str, Any] | None) -> dict[str, Any]:
    """Extract spellcasting caps from a progression row."""
    if not isinstance(row, dict):
        return {}
    caps: dict[str, Any] = {
        "proficiency_bonus": int(row.get("proficiency_bonus") or 2),
    }
    for field in ("cantrips_known", "spells_known", "spells_prepared", "invocations_known"):
        raw = row.get(field)
        if raw is not None and raw != "":
            try:
                caps[field] = int(raw)
            except (TypeError, ValueError):
                continue
    return caps


def resolve_spell_list_limits(caps: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Map class progression caps to player spell list limits."""
    caps = caps if isinstance(caps, dict) else {}
    limits: dict[str, dict[str, Any]] = {}
    for bucket, field in (
        ("cantrips", "cantrips_known"),
        ("prepared", "spells_prepared"),
        ("known", "spells_known"),
    ):
        raw = caps.get(field)
        if raw is None or raw == "":
            limits[bucket] = {"enabled": False, "max": 0}
            continue
        try:
            max_val = int(raw)
        except (TypeError, ValueError):
            limits[bucket] = {"enabled": False, "max": 0}
            continue
        limits[bucket] = {"enabled": max_val > 0, "max": max(0, max_val)}
    return limits


def apply_progression_row_to_sheet(
    sheet: dict[str, Any],
    row: dict[str, Any],
    *,
    level: Optional[int] = None,
    append_pending_choices: bool = False,
) -> None:
    """Sync sheet caps, resources, and spell slots from a progression row."""
    if not isinstance(sheet, dict) or not isinstance(row, dict):
        return
    caps = class_progression_caps_from_row(row)
    if caps:
        sheet["class_progression"] = caps
    resources = dict(row.get("resources") or {})
    if resources:
        sheet["class_resources"] = resources
    elif "class_resources" in sheet and not resources:
        sheet["class_resources"] = {}

    slots = resolve_spell_slots_from_row(row)
    if slots:
        sheet["spell_slots"] = slots
    elif row.get("pact_magic") is None and not row.get("spell_slots"):
        sheet.pop("spell_slots", None)

    if append_pending_choices:
        target_level = level if level is not None else int(row.get("level") or 1)
        pending = _pending_choices_from_row(row, level=target_level)
        if pending:
            existing = list(sheet.get("pending_level_choices") or [])
            existing.extend(pending)
            sheet["pending_level_choices"] = existing

    target_level = level if level is not None else int(row.get("level") or 1)
    _apply_row_trait_keys_to_sheet(sheet, row, target_level)


def apply_subclass_grants_for_level(
    sheet: dict[str, Any],
    class_entry: dict[str, Any] | None,
    level: int,
) -> None:
    """Grant subclass feature traits when character reaches grant level."""
    if not class_entry:
        return
    creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
    subclass_key = str(creation.get("subclass_key") or "").strip().lower()
    if not subclass_key:
        return
    from app.services.classes_compendium_service import find_subclass_on_class

    subclass = find_subclass_on_class(class_entry, subclass_key)
    if not subclass:
        return
    for grant in subclass.get("feature_grants") or []:
        if not isinstance(grant, dict):
            continue
        try:
            grant_level = int(grant.get("level") or 0)
        except (TypeError, ValueError):
            continue
        if grant_level != level:
            continue
        apply_trait_keys_at_level(sheet, list(grant.get("trait_keys") or []), grant_level)


def apply_trait_keys_at_level(
    sheet: dict[str, Any],
    trait_keys: list[str],
    level: int,
) -> None:
    """Merge trait keys into class_trait_selections for a level."""
    keys = [
        str(key or "").strip().lower()
        for key in trait_keys
        if str(key or "").strip()
    ]
    if not keys:
        return
    selections = sheet.get("class_trait_selections")
    if not isinstance(selections, dict):
        selections = {}
    level_key = str(level)
    existing = [
        str(key or "").strip().lower()
        for key in (selections.get(level_key) or [])
        if str(key or "").strip()
    ]
    merged: list[str] = []
    seen: set[str] = set()
    for key in existing + keys:
        if key and key not in seen:
            seen.add(key)
            merged.append(key)
    selections[level_key] = merged
    sheet["class_trait_selections"] = selections


def _apply_row_trait_keys_to_sheet(
    sheet: dict[str, Any],
    row: dict[str, Any],
    level: int,
) -> None:
    """Persist automatic trait grants from a progression row onto the sheet."""
    keys = [
        str(key or "").strip().lower()
        for key in (row.get("trait_keys") or [])
        if str(key or "").strip()
    ]
    if not keys:
        return
    apply_trait_keys_at_level(sheet, keys, level)


def _pending_choices_from_row(row: dict[str, Any], *, level: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pool in row.get("trait_pools") or []:
        if not isinstance(pool, dict):
            continue
        pool_tag = str(pool.get("pool_tag") or "").strip().lower()
        if not pool_tag:
            continue
        try:
            pick = max(1, int(pool.get("pick") or 1))
        except (TypeError, ValueError):
            pick = 1
        out.append(
            {
                "level": level,
                "type": "trait_pick",
                "title": str(pool.get("title") or "Trait choice").strip()[:80],
                "description": str(pool.get("description") or "").strip(),
                "pool_tag": pool_tag,
                "pick": pick,
                "skipped": False,
            }
        )
    for choice in row.get("player_choices") or []:
        if not isinstance(choice, dict):
            continue
        choice_type = str(choice.get("type") or "custom").strip().lower()
        if choice_type in ("spell", "spells", "cantrip", "cantrips", "trait_pick"):
            continue
        title = str(choice.get("title") or choice.get("name") or "Choice").strip()
        if not title:
            continue
        out.append(
            {
                "level": level,
                "type": choice_type,
                "title": title,
                "description": str(choice.get("description") or "").strip(),
                "skipped": False,
            }
        )
    return out


def progression_row_delta(
    current_row: dict[str, Any] | None,
    next_row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute numeric deltas between two progression rows for previews."""
    current_row = current_row if isinstance(current_row, dict) else {}
    next_row = next_row if isinstance(next_row, dict) else {}
    delta: dict[str, Any] = {}
    for field in ("cantrips_known", "spells_known", "spells_prepared", "invocations_known"):
        try:
            cur = int(current_row.get(field) or 0)
            nxt = int(next_row.get(field) or 0)
        except (TypeError, ValueError):
            continue
        if nxt > cur:
            delta[field] = nxt - cur
    cur_slots = resolve_spell_slots_from_row(current_row)
    nxt_slots = resolve_spell_slots_from_row(next_row)
    slot_changes = {
        key: nxt_slots[key]
        for key in nxt_slots
        if int(nxt_slots.get(key) or 0) > int(cur_slots.get(key) or 0)
    }
    if slot_changes:
        delta["spell_slot_changes"] = slot_changes
    return delta
