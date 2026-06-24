"""Player-facing monster bestiary — personal journals, not GM stat blocks."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models import MonsterCompendiumEntry, PlayerMonsterJournal
from app.services.combat import CombatValidationError
from app.services.combat.monster_compendium_service import _validated_stats

_BLANK_PLAYER_STATS: dict[str, Any] = {
    "attacks": [],
    "legendary_actions": [],
    "trait_keys": [],
}


def blank_player_monster_stats() -> dict[str, Any]:
    return dict(_BLANK_PLAYER_STATS)


def _validated_player_journal_stats(stat_json: Any) -> dict[str, Any]:
    """Validate optional player-observed stats (all fields may be omitted)."""
    if not isinstance(stat_json, dict):
        raise CombatValidationError("stats must be an object.")
    raw = dict(stat_json)
    cleaned: dict[str, Any] = {}

    for key, lo, hi in (
        ("hp_max", 1, 2000),
        ("ac", 1, 30),
        ("speed_ft", 0, 120),
    ):
        if key not in raw or raw[key] in (None, ""):
            continue
        try:
            value = int(raw[key])
        except (TypeError, ValueError):
            raise CombatValidationError(f"{key} must be an integer.")
        if not (lo <= value <= hi):
            raise CombatValidationError(f"{key} must be between {lo} and {hi}.")
        cleaned[key] = value

    abilities = raw.get("abilities")
    if isinstance(abilities, dict) and abilities:
        clean_abilities: dict[str, int] = {}
        for ability in ("str", "dex", "con", "int", "wis", "cha"):
            if ability not in abilities or abilities[ability] in (None, ""):
                continue
            try:
                score = int(abilities[ability])
            except (TypeError, ValueError):
                raise CombatValidationError(f"Ability {ability} must be an integer.")
            if not (1 <= score <= 30):
                raise CombatValidationError(f"Ability {ability} must be 1-30.")
            clean_abilities[ability] = score
        if clean_abilities:
            cleaned["abilities"] = clean_abilities

    # Attacks / legendary — reuse GM validator when any rows submitted.
    partial = dict(cleaned)
    attacks = raw.get("attacks")
    if isinstance(attacks, list) and attacks:
        partial["attacks"] = attacks
    else:
        partial["attacks"] = []
    legendary = raw.get("legendary_actions")
    if isinstance(legendary, list) and legendary:
        partial["legendary_actions"] = legendary
    else:
        partial["legendary_actions"] = []

    for text_key in (
        "size",
        "creature_type",
        "senses",
        "skills",
        "saving_throws",
        "damage_resistances",
        "damage_immunities",
        "damage_vulnerabilities",
        "condition_immunities",
        "notes",
    ):
        if text_key in raw and str(raw.get(text_key) or "").strip():
            cleaned[text_key] = str(raw[text_key]).strip()[:500]

    trait_keys = raw.get("trait_keys")
    if isinstance(trait_keys, list):
        cleaned["trait_keys"] = [
            str(k).strip().lower() for k in trait_keys if str(k or "").strip()
        ][:24]
    elif isinstance(trait_keys, str) and trait_keys.strip():
        cleaned["trait_keys"] = [
            part.strip().lower()
            for part in trait_keys.split(",")
            if part.strip()
        ][:24]

    if partial["attacks"] or partial["legendary_actions"]:
        validated = _validated_stats(
            {
                **partial,
                "hp_max": cleaned.get("hp_max", 10),
                "ac": cleaned.get("ac", 10),
                "speed_ft": cleaned.get("speed_ft", 30),
                "abilities": cleaned.get(
                    "abilities",
                    {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
                ),
            }
        )
        if partial["attacks"]:
            cleaned["attacks"] = validated.get("attacks") or []
        if partial["legendary_actions"]:
            cleaned["legendary_actions"] = validated.get("legendary_actions") or []

    return cleaned


def journal_for_viewer(
    viewer_player_id: int, monster_entry_id: int
) -> PlayerMonsterJournal | None:
    return PlayerMonsterJournal.query.filter_by(
        viewer_player_id=viewer_player_id,
        monster_entry_id=monster_entry_id,
    ).first()


def monster_visible_to_player(
    entry: MonsterCompendiumEntry,
    viewer_player_id: int,
) -> bool:
    if bool(getattr(entry, "known_to_players", False)):
        return True
    return (
        journal_for_viewer(viewer_player_id, entry.id) is not None
    )


def entry_for_player_view(
    campaign_id: int, entry_id: int, viewer_player_id: int
) -> MonsterCompendiumEntry | None:
    entry = MonsterCompendiumEntry.query.filter_by(
        id=entry_id, campaign_id=campaign_id
    ).first()
    if entry is None:
        return None
    if not monster_visible_to_player(entry, viewer_player_id):
        return None
    return entry


def build_known_monster_entries(campaign_id: int, viewer_player_id: int) -> list[dict]:
    """Monsters GM pre-shared or the player added to their bestiary."""
    journals = {
        row.monster_entry_id: row
        for row in PlayerMonsterJournal.query.filter_by(
            campaign_id=campaign_id,
            viewer_player_id=viewer_player_id,
        ).all()
    }
    entries = (
        MonsterCompendiumEntry.query.filter_by(campaign_id=campaign_id)
        .order_by(MonsterCompendiumEntry.name.asc(), MonsterCompendiumEntry.id.asc())
        .all()
    )
    out: list[dict] = []
    for entry in entries:
        journal = journals.get(entry.id)
        if not bool(getattr(entry, "known_to_players", False)) and journal is None:
            continue
        out.append(_serialize_list_row(entry, journal))
    return out


def _serialize_list_row(
    entry: MonsterCompendiumEntry, journal: PlayerMonsterJournal | None
) -> dict:
    player_stats = dict((journal.stat_json if journal else {}) or {})
    summary_bits: list[str] = []
    if player_stats.get("hp_max") is not None:
        summary_bits.append(f"HP {player_stats['hp_max']}")
    if player_stats.get("ac") is not None:
        summary_bits.append(f"AC {player_stats['ac']}")
    if player_stats.get("creature_type"):
        summary_bits.append(str(player_stats["creature_type"]))
    return {
        "id": entry.id,
        "name": entry.name,
        "challenge_rating": entry.challenge_rating,
        "source": entry.source,
        "gm_known": bool(getattr(entry, "known_to_players", False)),
        "in_journal": journal is not None,
        "player_summary": ", ".join(summary_bits) or None,
    }


def build_monster_journal_profile(
    entry: MonsterCompendiumEntry,
    viewer_player_id: int,
) -> dict:
    journal = journal_for_viewer(viewer_player_id, entry.id)
    return {
        "id": entry.id,
        "name": entry.name,
        "challenge_rating": entry.challenge_rating,
        "source": entry.source,
        "gm_known": bool(getattr(entry, "known_to_players", False)),
        "in_journal": journal is not None,
        "stats": dict((journal.stat_json if journal else blank_player_monster_stats()) or {}),
    }


def add_monster_to_journal(
    *,
    campaign_id: int,
    viewer_player_id: int,
    monster_entry_id: int,
) -> PlayerMonsterJournal:
    entry = MonsterCompendiumEntry.query.filter_by(
        id=monster_entry_id, campaign_id=campaign_id
    ).first()
    if entry is None:
        raise CombatValidationError("Monster not found in this campaign.")

    existing = journal_for_viewer(viewer_player_id, monster_entry_id)
    if existing is not None:
        return existing

    row = PlayerMonsterJournal(
        campaign_id=campaign_id,
        viewer_player_id=viewer_player_id,
        monster_entry_id=monster_entry_id,
        stat_json=blank_player_monster_stats(),
    )
    db.session.add(row)
    db.session.flush()
    return row


def save_player_monster_journal(
    *,
    campaign_id: int,
    viewer_player_id: int,
    monster_entry_id: int,
    stat_json: dict[str, Any],
) -> PlayerMonsterJournal:
    entry = entry_for_player_view(campaign_id, monster_entry_id, viewer_player_id)
    if entry is None:
        raise CombatValidationError("That monster is not in your bestiary.")

    cleaned = _validated_player_journal_stats(stat_json)
    row = journal_for_viewer(viewer_player_id, monster_entry_id)
    if row is None:
        row = PlayerMonsterJournal(
            campaign_id=campaign_id,
            viewer_player_id=viewer_player_id,
            monster_entry_id=monster_entry_id,
            stat_json=cleaned,
        )
        db.session.add(row)
    else:
        row.stat_json = cleaned
        row.campaign_id = campaign_id
    db.session.flush()
    return row
