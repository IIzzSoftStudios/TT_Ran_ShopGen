"""Encounter lifecycle and turn flow for D&D 5e tactical combat.

Concurrency contract: every mutating entrypoint takes the encounter row
``with_for_update()`` via :func:`locked_encounter` and compares the client's
``expected_version`` against ``turn_version`` **under that lock** (no
check-then-lock TOCTOU window). Services flush but never commit -- the
owning route commits or rolls back.

All combatant/target lookups are scoped to the locked encounter id, so a
request can never act on combatants from another encounter or campaign.
"""

from __future__ import annotations

from random import Random

from app.extensions import db
from app.models import BattleActionLog, BattleCombatant, BattleEncounter
from app.services.combat import CombatValidationError, StaleTurnError
from app.services.combat import dnd5e_rules as rules
from app.services.combat import settings_service
from app.services.rulesets import get_ruleset

MAX_GRID = 60
MIN_GRID = 5
MAX_COMBATANTS = 60

_SKIP_TURN_STATUSES = ("dead", "removed")


def _fresh_resources() -> dict:
    return {
        "action": True,
        "bonus_action": True,
        "reaction": True,
        "concentrating": False,
        "death_saves": {"successes": 0, "failures": 0},
    }


# ---------------------------------------------------------------------------
# Encounter lifecycle
# ---------------------------------------------------------------------------

def create_encounter(campaign_id: int, name=None, grid_width=20, grid_height=20,
                     map_canvas_id=None, map_x=None, map_y=None) -> BattleEncounter:
    name = (str(name or "Encounter")).strip()[:120] or "Encounter"
    try:
        grid_width = int(grid_width)
        grid_height = int(grid_height)
    except (TypeError, ValueError):
        raise CombatValidationError("Grid dimensions must be integers.")
    if not (MIN_GRID <= grid_width <= MAX_GRID and MIN_GRID <= grid_height <= MAX_GRID):
        raise CombatValidationError(
            f"Grid dimensions must be between {MIN_GRID} and {MAX_GRID}."
        )
    resolved_canvas_id = _validated_map_canvas_id(campaign_id, map_canvas_id)
    coords = (
        _coerce_map_position(map_x, map_y)
        if resolved_canvas_id and map_x is not None and map_y is not None
        else (None, None)
    )
    encounter = BattleEncounter(
        campaign_id=campaign_id,
        map_canvas_id=resolved_canvas_id,
        map_x=coords[0],
        map_y=coords[1],
        name=name,
        status="setup",
        grid_width=grid_width,
        grid_height=grid_height,
        settings_json=settings_service.get_settings(campaign_id),
    )
    db.session.add(encounter)
    db.session.flush()
    _log(encounter, None, "encounter_created", {"name": name})
    return encounter


def list_encounters(campaign_id: int) -> list[BattleEncounter]:
    return (
        BattleEncounter.query.filter_by(campaign_id=campaign_id)
        .order_by(BattleEncounter.id.desc())
        .all()
    )


def encounter_for_campaign(encounter_id, campaign_id: int) -> BattleEncounter | None:
    if not isinstance(encounter_id, int):
        return None
    return BattleEncounter.query.filter_by(
        id=encounter_id, campaign_id=campaign_id
    ).first()


def locked_encounter(encounter_id, campaign_id: int, expected_version=None) -> BattleEncounter:
    """Fetch the encounter FOR UPDATE and verify turn_version under the lock."""
    if not isinstance(encounter_id, int):
        raise LookupError("Encounter not found in this campaign.")
    encounter = (
        BattleEncounter.query.filter_by(id=encounter_id, campaign_id=campaign_id)
        .with_for_update()
        .first()
    )
    if encounter is None:
        raise LookupError("Encounter not found in this campaign.")
    if expected_version is not None:
        try:
            expected = int(expected_version)
        except (TypeError, ValueError):
            raise CombatValidationError("turn_version must be an integer.")
        if expected != encounter.turn_version:
            raise StaleTurnError(
                "Encounter state changed; refresh before acting."
            )
    return encounter


def end_encounter(encounter: BattleEncounter) -> None:
    encounter.status = "ended"
    encounter.turn_version += 1
    _log(encounter, None, "encounter_ended", {})
    db.session.flush()


def rename_encounter(encounter: BattleEncounter, name) -> None:
    """Update the encounter display name (does not bump turn_version)."""
    cleaned = (str(name or "")).strip()[:120]
    if not cleaned:
        raise CombatValidationError("Encounter name is required.")
    encounter.name = cleaned
    db.session.flush()


def delete_encounter(encounter: BattleEncounter) -> None:
    """Permanently remove an encounter and its dependent battle state."""
    BattleActionLog.query.filter_by(encounter_id=encounter.id).delete(
        synchronize_session=False
    )
    BattleCombatant.query.filter_by(encounter_id=encounter.id).delete(
        synchronize_session=False
    )
    db.session.delete(encounter)
    db.session.flush()


def set_player_visibility(encounter: BattleEncounter, visible) -> None:
    """Toggle whether players in the campaign can see or open this encounter."""
    encounter.visible_to_players = bool(visible)
    db.session.flush()


def _validated_map_canvas_id(campaign_id: int, map_canvas_id) -> int | None:
    if map_canvas_id is None:
        return None
    from app.models import MapCanvas

    try:
        canvas_id = int(map_canvas_id)
    except (TypeError, ValueError):
        raise CombatValidationError("map_canvas_id must be an integer.")
    canvas = MapCanvas.query.filter_by(id=canvas_id, campaign_id=campaign_id).first()
    if canvas is None:
        raise CombatValidationError("Map canvas not found in this campaign.")
    return canvas.id


def _coerce_map_position(x, y) -> tuple[float, float]:
    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        raise CombatValidationError("Map position x and y must be numbers.")
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise CombatValidationError("Map position must be within the map bounds.")
    return x, y


def place_encounter_on_canvas(encounter: BattleEncounter, campaign_id: int,
                              map_canvas_id, x, y) -> None:
    encounter.map_canvas_id = _validated_map_canvas_id(campaign_id, map_canvas_id)
    encounter.map_x, encounter.map_y = _coerce_map_position(x, y)
    db.session.flush()


def encounter_for_canvas(campaign_id: int, map_canvas_id: int) -> BattleEncounter | None:
    """Latest non-ended encounter linked to a map canvas, if any."""
    if not isinstance(map_canvas_id, int):
        return None
    return (
        BattleEncounter.query.filter_by(
            campaign_id=campaign_id,
            map_canvas_id=map_canvas_id,
        )
        .filter(BattleEncounter.status != "ended")
        .order_by(BattleEncounter.id.desc())
        .first()
    )


def default_encounter_name_for_canvas(canvas) -> str:
    if canvas.scope == "world" or not canvas.city_id:
        return "World encounter"
    city = canvas.city
    if city and getattr(city, "name", None):
        return f"{city.name} encounter"
    return "Encounter"


def get_or_create_encounter_for_canvas(campaign_id: int, map_canvas_id: int,
                                       name=None, x=None, y=None
                                       ) -> tuple[BattleEncounter, bool]:
    """Return (encounter, created). Reuses an active encounter on the canvas."""
    from app.models import MapCanvas

    canvas = MapCanvas.query.filter_by(id=map_canvas_id, campaign_id=campaign_id).first()
    if canvas is None:
        raise CombatValidationError("Map canvas not found in this campaign.")
    existing = encounter_for_canvas(campaign_id, canvas.id)
    if existing is not None:
        if x is not None and y is not None:
            place_encounter_on_canvas(existing, campaign_id, canvas.id, x, y)
        return existing, False
    label = (str(name or "")).strip() or default_encounter_name_for_canvas(canvas)
    encounter = create_encounter(
        campaign_id,
        name=label,
        map_canvas_id=canvas.id,
        map_x=x,
        map_y=y,
    )
    return encounter, True


def settings_for(encounter: BattleEncounter) -> dict:
    merged = dict(settings_service.DEFAULT_SETTINGS)
    stored = encounter.settings_json or {}
    for key in merged:
        if key in stored:
            merged[key] = stored[key]
    return merged


# ---------------------------------------------------------------------------
# Combatants
# ---------------------------------------------------------------------------

def _check_capacity(encounter: BattleEncounter) -> None:
    count = BattleCombatant.query.filter_by(encounter_id=encounter.id).count()
    if count >= MAX_COMBATANTS:
        raise CombatValidationError(
            f"Encounter is full ({MAX_COMBATANTS} combatants max)."
        )


def _free_tile(encounter: BattleEncounter, x: int, y: int) -> tuple[int, int]:
    """Return (x, y) if free, otherwise the nearest free tile to the request."""
    occupied = {
        (c.x, c.y)
        for c in BattleCombatant.query.filter_by(encounter_id=encounter.id).all()
        if c.status not in ("dead", "removed")
    }
    if (x, y) not in occupied:
        return x, y
    candidates: list[tuple[int, tuple[int, int]]] = []
    for j in range(encounter.grid_height):
        for i in range(encounter.grid_width):
            if (i, j) not in occupied:
                dist = abs(i - x) + abs(j - y)
                candidates.append((dist, (i, j)))
    if not candidates:
        raise CombatValidationError("No free tile available on the grid.")
    candidates.sort(key=lambda item: (item[0], item[1][1], item[1][0]))
    return candidates[0][1]


def _coerce_tile(encounter: BattleEncounter, x, y) -> tuple[int, int]:
    try:
        x = int(x)
        y = int(y)
    except (TypeError, ValueError):
        raise CombatValidationError("x and y must be integers.")
    if not (0 <= x < encounter.grid_width and 0 <= y < encounter.grid_height):
        raise CombatValidationError("Position is outside the encounter grid.")
    return x, y


def combatant_in_encounter(encounter: BattleEncounter, combatant_id) -> BattleCombatant | None:
    """Encounter-scoped combatant lookup (cross-encounter injection guard)."""
    if not isinstance(combatant_id, int):
        return None
    return BattleCombatant.query.filter_by(
        id=combatant_id, encounter_id=encounter.id
    ).first()


def add_player_combatant(encounter: BattleEncounter, player, campaign,
                         x=0, y=0, name=None) -> BattleCombatant:
    """Snapshot a D&D 5e character sheet into a party-side combatant."""
    from app.services.character_sheet_service import get_or_default_sheet

    if player is None or player.campaign_id != encounter.campaign_id:
        raise CombatValidationError("Player is not part of this campaign.")
    _check_capacity(encounter)

    sheet = get_or_default_sheet(player, campaign)
    abilities = {
        key: int(score)
        for key, score in (sheet.get("abilities") or {}).items()
        if isinstance(score, (int, float))
    }
    defenses = sheet.get("defenses") or {}

    def _defense(key, default):
        try:
            return max(0, int(defenses.get(key, default)))
        except (TypeError, ValueError):
            return default

    hp_max = max(1, _defense("hp_max", 10))
    hp_current = min(hp_max, max(0, _defense("hp_current", hp_max)))
    display_name = (str(name or "")).strip() or (
        player.user.username if player.user else f"Character {player.id}"
    )

    ruleset = get_ruleset("dnd5e")
    dex_mod = ruleset.compute_ability_mod(abilities.get("dex", 10))
    str_mod = ruleset.compute_ability_mod(abilities.get("str", 10))
    prof = ruleset.proficiency_bonus(1)

    x, y = _free_tile(encounter, *_coerce_tile(encounter, x, y))
    combatant = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=encounter.campaign_id,
        player_id=player.id,
        name=display_name[:120],
        side="party",
        status="active",
        x=x,
        y=y,
        hp_max=hp_max,
        hp_current=hp_current,
        temp_hp=0,
        ac=max(1, _defense("ac", 10)),
        speed_ft=30,
        dex_mod=dex_mod,
        ability_json=abilities,
        action_data_json={
            "attacks": [
                {
                    "key": "weapon",
                    "name": "Weapon Attack",
                    "kind": "melee",
                    "attack_mod": str_mod + prof,
                    "damage": f"1d8+{max(0, str_mod)}",
                    "damage_type": "slashing",
                    "range_ft": 5,
                }
            ]
        },
        resources_json=_fresh_resources(),
        spell_slots_json={},
        conditions_json=[],
    )
    db.session.add(combatant)
    db.session.flush()
    encounter.turn_version += 1
    _log(encounter, combatant, "combatant_added", {"source": "player", "player_id": player.id})
    return combatant


def add_monster_combatant(encounter: BattleEncounter, entry, x=0, y=0,
                          name=None) -> BattleCombatant:
    """Clone a compendium entry into a foe-side combatant (snapshot copy)."""
    if entry is None or entry.campaign_id != encounter.campaign_id:
        raise CombatValidationError("Monster not found in this campaign.")
    _check_capacity(encounter)

    stats = entry.stat_json or {}
    abilities = stats.get("abilities") or {}
    ruleset = get_ruleset("dnd5e")
    dex_mod = ruleset.compute_ability_mod(abilities.get("dex", 10))
    hp_max = max(1, int(stats.get("hp_max", 1)))

    x, y = _free_tile(encounter, *_coerce_tile(encounter, x, y))
    combatant = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=encounter.campaign_id,
        compendium_entry_id=entry.id,
        name=(str(name or entry.name)).strip()[:120] or entry.name,
        side="foe",
        status="active",
        x=x,
        y=y,
        hp_max=hp_max,
        hp_current=hp_max,
        temp_hp=0,
        ac=max(1, int(stats.get("ac", 10))),
        speed_ft=max(0, int(stats.get("speed_ft", 30))),
        dex_mod=dex_mod,
        ability_json=dict(abilities),
        action_data_json={
            "attacks": list(stats.get("attacks") or []),
            "legendary_actions": list(stats.get("legendary_actions") or []),
        },
        resources_json=_fresh_resources(),
        spell_slots_json={},
        conditions_json=[],
    )
    db.session.add(combatant)
    db.session.flush()
    encounter.turn_version += 1
    _log(encounter, combatant, "combatant_added", {"source": "compendium", "entry_id": entry.id})
    return combatant


def remove_combatant(encounter: BattleEncounter, combatant: BattleCombatant) -> None:
    combatant.status = "removed"
    encounter.turn_version += 1
    _log(encounter, combatant, "combatant_removed", {})
    db.session.flush()


# ---------------------------------------------------------------------------
# Turn order
# ---------------------------------------------------------------------------

def ordered_combatants(encounter: BattleEncounter) -> list[BattleCombatant]:
    """Combatants in initiative order (those with an order assigned)."""
    return (
        BattleCombatant.query.filter(
            BattleCombatant.encounter_id == encounter.id,
            BattleCombatant.initiative_order.isnot(None),
            BattleCombatant.status.notin_(("removed",)),
        )
        .order_by(BattleCombatant.initiative_order.asc())
        .all()
    )


def current_combatant(encounter: BattleEncounter) -> BattleCombatant | None:
    if encounter.status != "active":
        return None
    order = ordered_combatants(encounter)
    if not order:
        return None
    return order[encounter.turn_index % len(order)]


def roll_initiative(encounter: BattleEncounter, rng: Random) -> list[BattleCombatant]:
    """Roll initiative for every combatant and start round 1."""
    if encounter.status == "ended":
        raise CombatValidationError("Encounter has ended.")
    combatants = [
        c
        for c in BattleCombatant.query.filter_by(encounter_id=encounter.id).all()
        if c.status not in ("removed",)
    ]
    if not combatants:
        raise CombatValidationError("Add combatants before rolling initiative.")

    settings = settings_for(encounter)
    rolls = {}
    for combatant in combatants:
        result = rules.roll_initiative(combatant.dex_mod, rng)
        combatant.initiative = result["total"]
        rolls[combatant.id] = result

    entries = [
        {"id": c.id, "initiative": c.initiative, "dex_mod": c.dex_mod}
        for c in combatants
    ]
    ordered = rules.order_initiative(
        entries, rng, tie_mode=settings["initiative_tie_mode"]
    )
    by_id = {c.id: c for c in combatants}
    for position, entry in enumerate(ordered):
        by_id[entry["id"]].initiative_order = position

    encounter.status = "active"
    encounter.round_number = 1
    encounter.turn_index = 0
    encounter.turn_version += 1

    first = by_id[ordered[0]["id"]]
    _begin_turn(first)
    _log(
        encounter,
        None,
        "initiative_rolled",
        {
            "order": [entry["id"] for entry in ordered],
            "rolls": {str(cid): r["total"] for cid, r in rolls.items()},
        },
    )
    db.session.flush()
    return [by_id[entry["id"]] for entry in ordered]


def _begin_turn(combatant: BattleCombatant) -> None:
    """Turn start: reset movement and action economy, clear the wait flag."""
    combatant.movement_used_ft = 0
    combatant.has_waited = False
    resources = dict(combatant.resources_json or _fresh_resources())
    resources["action"] = True
    resources["bonus_action"] = True
    resources["reaction"] = True
    combatant.resources_json = resources


def _require_active(encounter: BattleEncounter) -> None:
    if encounter.status != "active":
        raise CombatValidationError("Encounter is not active. Roll initiative first.")


def _require_turn(encounter: BattleEncounter, combatant: BattleCombatant) -> None:
    current = current_combatant(encounter)
    if current is None or current.id != combatant.id:
        raise CombatValidationError(f"It is not {combatant.name}'s turn.")


def end_turn(encounter: BattleEncounter) -> BattleCombatant | None:
    """Advance to the next live combatant; wrap increments round_number."""
    _require_active(encounter)
    order = ordered_combatants(encounter)
    if not order:
        raise CombatValidationError("No combatants in initiative order.")

    previous = order[encounter.turn_index % len(order)]
    for _ in range(len(order)):
        next_index = (encounter.turn_index + 1) % len(order)
        if next_index <= encounter.turn_index:
            encounter.round_number += 1
        encounter.turn_index = next_index
        candidate = order[next_index]
        if candidate.status not in _SKIP_TURN_STATUSES:
            _begin_turn(candidate)
            encounter.turn_version += 1
            _log(
                encounter,
                previous,
                "turn_ended",
                {"next_combatant_id": candidate.id, "round": encounter.round_number},
            )
            db.session.flush()
            return candidate
    # Everyone is dead/removed; nothing to advance to.
    encounter.turn_version += 1
    db.session.flush()
    return None


def wait_action(encounter: BattleEncounter, combatant: BattleCombatant) -> BattleCombatant | None:
    """Drop the current combatant to the bottom of the round order.

    Does not increment ``round_number``; ``has_waited`` stays set until that
    combatant's next turn starts (enforces once-per-turn).
    """
    _require_active(encounter)
    _require_turn(encounter, combatant)
    if combatant.has_waited:
        raise CombatValidationError("Wait can only be used once per turn.")

    order = ordered_combatants(encounter)
    reordered = [c for c in order if c.id != combatant.id] + [combatant]
    for position, entry in enumerate(reordered):
        entry.initiative_order = position
    combatant.has_waited = True
    encounter.turn_version += 1

    # turn_index now points at the combatant that shifted into this slot.
    # If the waiter was already last, the same combatant keeps the turn but
    # has_waited blocks a second wait.
    next_up = reordered[encounter.turn_index % len(reordered)]
    if next_up.id != combatant.id:
        _begin_turn(next_up)
    _log(encounter, combatant, "wait", {"next_combatant_id": next_up.id})
    db.session.flush()
    return next_up


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def move_action(encounter: BattleEncounter, combatant: BattleCombatant,
                to_x, to_y) -> dict:
    """Move the current combatant to a tile within its remaining speed."""
    _require_active(encounter)
    _require_turn(encounter, combatant)
    if combatant.status != "active":
        raise CombatValidationError(f"{combatant.name} cannot move right now.")

    to_x, to_y = _coerce_tile(encounter, to_x, to_y)
    settings = settings_for(encounter)
    cost = rules.grid_distance_ft(
        combatant.x, combatant.y, to_x, to_y, settings["diagonal_mode"]
    )
    if cost == 0:
        raise CombatValidationError("Already on that tile.")

    occupied = (
        BattleCombatant.query.filter(
            BattleCombatant.encounter_id == encounter.id,
            BattleCombatant.id != combatant.id,
            BattleCombatant.x == to_x,
            BattleCombatant.y == to_y,
            BattleCombatant.status.notin_(("dead", "removed")),
        ).first()
    )
    if occupied is not None:
        raise CombatValidationError("That tile is occupied.")

    remaining = combatant.speed_ft - combatant.movement_used_ft
    if cost > remaining:
        raise CombatValidationError(
            f"Not enough movement: {cost} ft needed, {remaining} ft remaining."
        )

    from_pos = {"x": combatant.x, "y": combatant.y}
    combatant.x = to_x
    combatant.y = to_y
    combatant.movement_used_ft += cost
    encounter.turn_version += 1
    payload = {
        "from": from_pos,
        "to": {"x": to_x, "y": to_y},
        "cost_ft": cost,
        "movement_used_ft": combatant.movement_used_ft,
    }
    _log(encounter, combatant, "move", payload)
    db.session.flush()
    return payload


def _attack_definition(combatant: BattleCombatant, attack_key) -> dict:
    attacks = (combatant.action_data_json or {}).get("attacks") or []
    for attack in attacks:
        if attack.get("key") == attack_key:
            return attack
    raise CombatValidationError("Unknown attack for this combatant.")


def _apply_outcome_to_target(encounter: BattleEncounter, target: BattleCombatant,
                             damage_total: int, settings: dict, rng: Random) -> dict:
    """Apply damage temp-HP-first; handle down/dead and concentration."""
    outcome = rules.apply_damage(target.hp_current, target.temp_hp, damage_total)
    target.hp_current = outcome["hp_current"]
    target.temp_hp = outcome["temp_hp"]

    result = {"damage": outcome, "target_status": target.status}
    if target.hp_current <= 0 and target.status == "active":
        if target.player_id is not None and settings["death_saves"]:
            target.status = "down"
        else:
            target.status = "dead"
        result["target_status"] = target.status

    resources = dict(target.resources_json or {})
    if (
        settings["concentration_checks"]
        and outcome["taken"] > 0
        and resources.get("concentrating")
        and target.status == "active"
    ):
        ruleset = get_ruleset("dnd5e")
        con_mod = ruleset.compute_ability_mod(
            (target.ability_json or {}).get("con", 10)
        )
        dc = rules.concentration_dc(outcome["taken"])
        save = rules.saving_throw(con_mod, dc, rng)
        if not save["success"]:
            resources["concentrating"] = False
            target.resources_json = resources
        result["concentration"] = save
    return result


def attack_action(encounter: BattleEncounter, attacker: BattleCombatant,
                  target_id, attack_key, rng: Random,
                  roll_mode: str = "normal") -> dict:
    """Fully resolve one attack: to-hit, damage, HP application, conditions."""
    _require_active(encounter)
    _require_turn(encounter, attacker)
    if attacker.status != "active":
        raise CombatValidationError(f"{attacker.name} cannot act right now.")

    target = combatant_in_encounter(encounter, target_id)
    if target is None or target.status in ("dead", "removed"):
        raise CombatValidationError("Target not found in this encounter.")
    if target.id == attacker.id:
        raise CombatValidationError("A combatant cannot attack itself.")

    settings = settings_for(encounter)
    resources = dict(attacker.resources_json or _fresh_resources())
    if settings["track_action_economy"] and not resources.get("action", True):
        raise CombatValidationError(f"{attacker.name} has already used their action.")

    attack = _attack_definition(attacker, attack_key)
    distance = rules.grid_distance_ft(
        attacker.x, attacker.y, target.x, target.y, settings["diagonal_mode"]
    )
    if distance > int(attack.get("range_ft", 5)):
        raise CombatValidationError(
            f"Target is out of range ({distance} ft > {attack.get('range_ft', 5)} ft)."
        )

    if roll_mode not in rules.ROLL_MODES:
        raise CombatValidationError("Invalid roll mode.")
    to_hit = rules.resolve_attack_roll(
        int(attack.get("attack_mod", 0)), target.ac, rng, roll_mode
    )
    result = {
        "attacker_id": attacker.id,
        "target_id": target.id,
        "attack": {"key": attack.get("key"), "name": attack.get("name")},
        "distance_ft": distance,
        "to_hit": to_hit,
        "hit": to_hit["hit"],
        "crit": to_hit["crit"],
    }
    if to_hit["hit"]:
        crit = to_hit["crit"] and settings["crit_mode"] == "double_dice"
        damage = rules.roll_damage(str(attack.get("damage", "1d6")), rng, crit=crit)
        result["damage_roll"] = damage
        if settings["auto_apply_damage"]:
            result["outcome"] = _apply_outcome_to_target(
                encounter, target, damage["total"], settings, rng
            )

    if settings["track_action_economy"]:
        resources["action"] = False
        attacker.resources_json = resources

    encounter.turn_version += 1
    _log(encounter, attacker, "attack", result)
    db.session.flush()
    return result


def batch_attack_action(encounter: BattleEncounter, attacker_ids, target_id,
                        attack_key, rng: Random,
                        roll_mode: str = "normal") -> list[dict]:
    """GM batch roll: the current foe plus checked allies attack one target.

    Every attacker must be a GM-controlled foe in this encounter and the
    current turn holder must be among them; each gets independent rolls and
    consumes its own action.
    """
    _require_active(encounter)
    if not isinstance(attacker_ids, list) or not attacker_ids:
        raise CombatValidationError("attacker_ids must be a non-empty list.")
    if len(attacker_ids) > 20:
        raise CombatValidationError("At most 20 attackers per batch roll.")

    attackers = []
    for raw_id in attacker_ids:
        combatant = combatant_in_encounter(encounter, raw_id)
        if combatant is None:
            raise CombatValidationError("Attacker not found in this encounter.")
        if combatant.side != "foe" or combatant.player_id is not None:
            raise CombatValidationError("Batch rolls are only for GM-controlled foes.")
        if combatant.status != "active":
            raise CombatValidationError(f"{combatant.name} cannot act right now.")
        attackers.append(combatant)

    current = current_combatant(encounter)
    if current is None or current.id not in {a.id for a in attackers}:
        raise CombatValidationError(
            "The current turn's combatant must be included in the batch roll."
        )

    settings = settings_for(encounter)
    results = []
    for attacker in attackers:
        target = combatant_in_encounter(encounter, target_id)
        if target is None or target.status in ("dead", "removed"):
            results.append(
                {"attacker_id": attacker.id, "skipped": "Target is already down."}
            )
            continue
        resources = dict(attacker.resources_json or _fresh_resources())
        attack = _attack_definition(attacker, attack_key)
        distance = rules.grid_distance_ft(
            attacker.x, attacker.y, target.x, target.y, settings["diagonal_mode"]
        )
        if distance > int(attack.get("range_ft", 5)):
            results.append(
                {"attacker_id": attacker.id, "skipped": "Target out of range."}
            )
            continue
        to_hit = rules.resolve_attack_roll(
            int(attack.get("attack_mod", 0)), target.ac, rng, roll_mode
        )
        entry = {
            "attacker_id": attacker.id,
            "target_id": target.id,
            "to_hit": to_hit,
            "hit": to_hit["hit"],
            "crit": to_hit["crit"],
        }
        if to_hit["hit"]:
            crit = to_hit["crit"] and settings["crit_mode"] == "double_dice"
            damage = rules.roll_damage(str(attack.get("damage", "1d6")), rng, crit=crit)
            entry["damage_roll"] = damage
            if settings["auto_apply_damage"]:
                entry["outcome"] = _apply_outcome_to_target(
                    encounter, target, damage["total"], settings, rng
                )
        resources["action"] = False
        attacker.resources_json = resources
        results.append(entry)

    encounter.turn_version += 1
    _log(encounter, current, "batch_attack", {"results_count": len(results)})
    db.session.flush()
    return results


def death_save_action(encounter: BattleEncounter, combatant: BattleCombatant,
                      rng: Random) -> dict:
    """Roll one death save for a downed PC on its turn (when enabled)."""
    _require_active(encounter)
    _require_turn(encounter, combatant)
    settings = settings_for(encounter)
    if not settings["death_saves"]:
        raise CombatValidationError("Death saves are disabled in battle settings.")
    if combatant.status != "down":
        raise CombatValidationError(f"{combatant.name} is not dying.")

    roll = rules.roll_death_save(rng)
    resources = dict(combatant.resources_json or _fresh_resources())
    saves = dict(resources.get("death_saves") or {"successes": 0, "failures": 0})
    saves["successes"] = saves.get("successes", 0) + roll["successes"]
    saves["failures"] = saves.get("failures", 0) + roll["failures"]

    result = {"roll": roll, "death_saves": saves, "status": combatant.status}
    if roll["revived"]:
        combatant.status = "active"
        combatant.hp_current = 1
        saves = {"successes": 0, "failures": 0}
        result["status"] = "active"
    elif saves["failures"] >= 3:
        combatant.status = "dead"
        result["status"] = "dead"
    elif saves["successes"] >= 3:
        combatant.status = "stable"
        saves = {"successes": 0, "failures": 0}
        result["status"] = "stable"

    resources["death_saves"] = saves
    combatant.resources_json = resources
    result["death_saves"] = saves
    encounter.turn_version += 1
    _log(encounter, combatant, "death_save", result)
    db.session.flush()
    return result


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(encounter: BattleEncounter, combatant, action_type: str, payload: dict) -> None:
    db.session.add(
        BattleActionLog(
            encounter_id=encounter.id,
            campaign_id=encounter.campaign_id,
            combatant_id=combatant.id if combatant is not None else None,
            round_number=encounter.round_number,
            action_type=action_type,
            payload_json=payload,
        )
    )
