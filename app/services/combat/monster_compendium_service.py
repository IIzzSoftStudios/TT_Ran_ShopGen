"""Campaign-scoped monster compendium CRUD (D&D 5e mechanical templates).

Services flush but never commit; the owning route commits or rolls back.
All lookups are scoped by ``campaign_id`` so entries can never leak across
campaigns.
"""

from __future__ import annotations

from random import Random

from app.extensions import db
from app.models import MonsterCompendiumEntry
from app.services.combat import CombatValidationError
from app.services.combat import dnd5e_rules, monster_generator

_MAX_NAME_LEN = 120
_ALLOWED_SOURCES = ("custom", "generated")


def list_entries(campaign_id: int) -> list[MonsterCompendiumEntry]:
    return (
        MonsterCompendiumEntry.query.filter_by(campaign_id=campaign_id)
        .order_by(MonsterCompendiumEntry.name.asc(), MonsterCompendiumEntry.id.asc())
        .all()
    )


def entry_for_campaign(entry_id, campaign_id: int) -> MonsterCompendiumEntry | None:
    if not isinstance(entry_id, int):
        return None
    return MonsterCompendiumEntry.query.filter_by(
        id=entry_id, campaign_id=campaign_id
    ).first()


def _validated_stats(stat_json) -> dict:
    """Validate the mechanical stat block shape GMs may submit."""
    if not isinstance(stat_json, dict):
        raise CombatValidationError("stats must be an object.")
    stats = dict(stat_json)

    for key, lo, hi, default in (
        ("hp_max", 1, 2000, 10),
        ("ac", 1, 30, 10),
        ("speed_ft", 0, 120, 30),
    ):
        try:
            value = int(stats.get(key, default))
        except (TypeError, ValueError):
            raise CombatValidationError(f"{key} must be an integer.")
        if not (lo <= value <= hi):
            raise CombatValidationError(f"{key} must be between {lo} and {hi}.")
        stats[key] = value

    abilities = stats.get("abilities") or {}
    if not isinstance(abilities, dict):
        raise CombatValidationError("abilities must be an object.")
    clean_abilities = {}
    for ability in ("str", "dex", "con", "int", "wis", "cha"):
        try:
            score = int(abilities.get(ability, 10))
        except (TypeError, ValueError):
            raise CombatValidationError(f"Ability {ability} must be an integer.")
        if not (1 <= score <= 30):
            raise CombatValidationError(f"Ability {ability} must be 1-30.")
        clean_abilities[ability] = score
    stats["abilities"] = clean_abilities

    attacks = stats.get("attacks") or []
    if not isinstance(attacks, list) or len(attacks) > 10:
        raise CombatValidationError("attacks must be a list of at most 10 entries.")
    clean_attacks = []
    for index, attack in enumerate(attacks):
        if not isinstance(attack, dict):
            raise CombatValidationError("Each attack must be an object.")
        name = str(attack.get("name") or f"Attack {index + 1}")[:60]
        try:
            attack_mod = int(attack.get("attack_mod", 0))
            range_ft = int(attack.get("range_ft", 5))
        except (TypeError, ValueError):
            raise CombatValidationError("attack_mod and range_ft must be integers.")
        if not (-10 <= attack_mod <= 30):
            raise CombatValidationError("attack_mod must be between -10 and 30.")
        if not (5 <= range_ft <= 600):
            raise CombatValidationError("range_ft must be between 5 and 600.")
        damage = str(attack.get("damage") or "1d6")
        try:
            dnd5e_rules.parse_dice(damage)
        except ValueError as exc:
            raise CombatValidationError(f"Attack damage: {exc}")
        clean_attacks.append(
            {
                "key": str(attack.get("key") or f"attack_{index}")[:30],
                "name": name,
                "kind": "ranged" if attack.get("kind") == "ranged" else "melee",
                "attack_mod": attack_mod,
                "damage": damage,
                "damage_type": str(attack.get("damage_type") or "bludgeoning")[:20],
                "range_ft": range_ft,
            }
        )
    stats["attacks"] = clean_attacks

    legendary_actions = stats.get("legendary_actions") or []
    if not isinstance(legendary_actions, list) or len(legendary_actions) > 10:
        raise CombatValidationError(
            "legendary_actions must be a list of at most 10 entries."
        )
    clean_legendary = []
    for index, action in enumerate(legendary_actions):
        if not isinstance(action, dict):
            raise CombatValidationError("Each legendary action must be an object.")
        name = str(action.get("name") or f"Legendary action {index + 1}").strip()[:60]
        try:
            cost = int(action.get("cost", 1))
        except (TypeError, ValueError):
            raise CombatValidationError("Legendary action cost must be an integer.")
        if not (1 <= cost <= 3):
            raise CombatValidationError("Legendary action cost must be between 1 and 3.")
        damage = str(action.get("damage") or "").strip()
        if damage:
            try:
                dnd5e_rules.parse_dice(damage)
            except ValueError as exc:
                raise CombatValidationError(f"Legendary action damage: {exc}")
        try:
            attack_mod = (
                int(action["attack_mod"])
                if action.get("attack_mod") not in (None, "")
                else None
            )
            range_ft = (
                int(action["range_ft"])
                if action.get("range_ft") not in (None, "")
                else None
            )
        except (TypeError, ValueError):
            raise CombatValidationError(
                "Legendary action attack_mod and range_ft must be integers."
            )
        if attack_mod is not None and not (-10 <= attack_mod <= 30):
            raise CombatValidationError(
                "Legendary action attack_mod must be between -10 and 30."
            )
        if range_ft is not None and not (5 <= range_ft <= 600):
            raise CombatValidationError(
                "Legendary action range_ft must be between 5 and 600."
            )
        clean_legendary.append(
            {
                "key": str(action.get("key") or f"legendary_{index}")[:30],
                "name": name,
                "cost": cost,
                "description": str(action.get("description") or "")[:500],
                "attack_mod": attack_mod,
                "damage": damage,
                "damage_type": str(action.get("damage_type") or "")[:20],
                "range_ft": range_ft,
            }
        )
    stats["legendary_actions"] = clean_legendary
    return stats


def create_entry(campaign_id: int, name, stat_json, challenge_rating=None,
                 source: str = "custom", generation_seed: str | None = None
                 ) -> MonsterCompendiumEntry:
    name = (str(name or "")).strip()
    if not name:
        raise CombatValidationError("Monster name is required.")
    if len(name) > _MAX_NAME_LEN:
        raise CombatValidationError(f"Monster name must be at most {_MAX_NAME_LEN} characters.")
    if source not in _ALLOWED_SOURCES:
        raise CombatValidationError("Invalid monster source.")
    cr = None
    if challenge_rating is not None:
        try:
            cr = float(challenge_rating)
        except (TypeError, ValueError):
            raise CombatValidationError("challenge_rating must be a number.")
        if not (0 <= cr <= 30):
            raise CombatValidationError("challenge_rating must be between 0 and 30.")

    entry = MonsterCompendiumEntry(
        campaign_id=campaign_id,
        name=name,
        source=source,
        generation_seed=generation_seed,
        challenge_rating=cr,
        stat_json=_validated_stats(stat_json),
    )
    db.session.add(entry)
    db.session.flush()
    return entry


def update_entry(entry: MonsterCompendiumEntry, name=None, stat_json=None,
                 challenge_rating=None) -> MonsterCompendiumEntry:
    if name is not None:
        name = str(name).strip()
        if not name or len(name) > _MAX_NAME_LEN:
            raise CombatValidationError("Monster name must be 1-120 characters.")
        entry.name = name
    if stat_json is not None:
        entry.stat_json = _validated_stats(stat_json)
    if challenge_rating is not None:
        try:
            cr = float(challenge_rating)
        except (TypeError, ValueError):
            raise CombatValidationError("challenge_rating must be a number.")
        if not (0 <= cr <= 30):
            raise CombatValidationError("challenge_rating must be between 0 and 30.")
        entry.challenge_rating = cr
    db.session.flush()
    return entry


def delete_entry(entry: MonsterCompendiumEntry) -> None:
    db.session.delete(entry)
    db.session.flush()


def generate_entry(campaign_id: int, raw_seed=None, challenge=1.0,
                   rng: Random | None = None) -> MonsterCompendiumEntry:
    """Generate a deterministic template and persist it as a compendium entry."""
    seed_hex = monster_generator.derive_seed(raw_seed, rng=rng)
    template = monster_generator.generate_monster_template(seed_hex, challenge)
    stats = {
        "hp_max": template["hp_max"],
        "ac": template["ac"],
        "speed_ft": template["speed_ft"],
        "abilities": template["abilities"],
        "attacks": template["attacks"],
        "role": template["role"],
    }
    return create_entry(
        campaign_id,
        template["name"],
        stats,
        challenge_rating=template["challenge_rating"],
        source="generated",
        generation_seed=seed_hex,
    )


def serialize_entry(entry: MonsterCompendiumEntry) -> dict:
    return {
        "id": entry.id,
        "name": entry.name,
        "source": entry.source,
        "generation_seed": entry.generation_seed,
        "challenge_rating": entry.challenge_rating,
        "stats": entry.stat_json or {},
    }
