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
from app.services.combat import dnd5e_combat_profile as combat_profile
from app.services.combat import dnd5e_rules as rules
from app.services.combat import settings_service
from app.services.rulesets import get_ruleset

MIN_GRID = 5
MAX_GRID = 1000
MAX_GRID_ABUSE = 100000
MAX_COMBATANTS = 60

_SKIP_TURN_STATUSES = ("dead", "removed")


def _fresh_resources(*, legendary_points_max: int = 0) -> dict:
    return {
        "action": True,
        "bonus_action": True,
        "reaction": True,
        "concentrating": False,
        "concentration": None,
        "death_saves": {"successes": 0, "failures": 0},
        "legendary_points_remaining": legendary_points_max,
        "relentless_endurance_used": False,
        "disengage": False,
    }


def _active_combatants(encounter: BattleEncounter) -> list[BattleCombatant]:
    return [
        c
        for c in BattleCombatant.query.filter_by(encounter_id=encounter.id).all()
        if c.status not in ("dead", "removed")
    ]


def _combat_profile(combatant: BattleCombatant) -> dict:
    return combat_profile.profile_from_action_data(combatant.action_data_json)


def _save_modifier(combatant: BattleCombatant, ability: str) -> int:
    profile = _combat_profile(combatant)
    action_data = combatant.action_data_json or {}
    level = int(action_data.get("character_level") or profile.get("character_level") or 1)
    abilities = combatant.ability_json or {}
    score = abilities.get(str(ability or "dex"), 10)
    return combat_profile.compute_save_modifier(
        int(score),
        ability,
        profile,
        level=level,
        save_prof_flags=action_data.get("save_prof_flags"),
    )


def _resolve_save_roll(
    combatant: BattleCombatant,
    ability: str,
    dc: int,
    rng: Random,
    *,
    client_mode: str = "normal",
    vs_condition: str | None = None,
    is_magic: bool = False,
) -> dict:
    profile = _combat_profile(combatant)
    cond_mode = combat_profile.condition_save_modifiers(
        list(combatant.conditions_json or []),
        ability,
    )
    if cond_mode == "auto_fail":
        return {
            "rolls": [],
            "natural": 1,
            "total": 0,
            "mode": "auto_fail",
            "is_nat20": False,
            "is_nat1": True,
            "dc": int(dc),
            "success": False,
            "auto_fail": True,
        }
    modes = [client_mode, cond_mode]
    if combat_profile.save_advantage_for_profile(
        profile,
        ability=ability,
        vs_condition=vs_condition,
        is_magic=is_magic,
    ):
        modes.append("advantage")
    mode = combat_profile.combine_roll_modes(*modes)
    save_mod = _save_modifier(combatant, ability)
    result = combat_profile.roll_d20_with_lucky(save_mod, rng, mode, profile)
    result.update({"dc": int(dc), "success": result["total"] >= int(dc)})
    return result


def _effective_target_ac(
    encounter: BattleEncounter,
    attacker: BattleCombatant,
    target: BattleCombatant,
    settings: dict,
    *,
    attack_kind: str,
) -> tuple[int, dict]:
    ac = int(target.ac)
    detail: dict = {"base_ac": ac, "cover_bonus": 0}
    if not settings.get("cover"):
        return ac, detail
    blockers = [
        (c.x, c.y)
        for c in _active_combatants(encounter)
        if c.id not in (attacker.id, target.id)
    ]
    bonus = combat_profile.cover_ac_bonus(attacker.x, attacker.y, target.x, target.y, blockers)
    detail["cover_bonus"] = bonus
    return ac + bonus, detail


def _attack_roll_mode(
    encounter: BattleEncounter,
    attacker: BattleCombatant,
    target: BattleCombatant,
    attack: dict,
    settings: dict,
    client_mode: str,
) -> tuple[str, dict]:
    atk_conds = list(attacker.conditions_json or [])
    tgt_conds = list(target.conditions_json or [])
    kind = str(attack.get("kind") or "melee")
    atk_part, tgt_part = combat_profile.condition_attack_modifiers(
        atk_conds, tgt_conds, attack_kind=kind
    )
    modes = [client_mode, atk_part]
    if tgt_part == "advantage":
        modes.append("advantage")
    elif tgt_part == "disadvantage":
        modes.append("disadvantage")
    if settings.get("flanking") and combat_profile.is_flanking(
        attacker.x,
        attacker.y,
        target.x,
        target.y,
        [
            (c.x, c.y)
            for c in _active_combatants(encounter)
            if c.side == attacker.side and c.id != attacker.id
        ],
        attack_kind=kind,
    ):
        modes.append("advantage")
    detail = {
        "attacker_conditions": atk_part,
        "target_conditions": tgt_part,
        "flanking": "advantage" in modes and settings.get("flanking"),
    }
    return combat_profile.combine_roll_modes(*modes), detail


def _resolve_attack_to_hit(
    attacker: BattleCombatant,
    target_ac: int,
    attack_mod: int,
    rng: Random,
    roll_mode: str,
) -> dict:
    profile = _combat_profile(attacker)
    result = combat_profile.roll_d20_with_lucky(int(attack_mod), rng, roll_mode, profile)
    crit = result["is_nat20"]
    hit = crit or (not result["is_nat1"] and result["total"] >= int(target_ac))
    result.update({"hit": hit, "crit": crit, "target_ac": int(target_ac)})
    return result


def _melee_reach_ft(combatant: BattleCombatant) -> int:
    attacks = (combatant.action_data_json or {}).get("attacks") or []
    reach = 5
    for attack in attacks:
        if str(attack.get("kind") or "melee").lower() == "melee":
            try:
                reach = max(reach, int(attack.get("range_ft") or 5))
            except (TypeError, ValueError):
                pass
    return reach


def _resolve_opportunity_attacks(
    encounter: BattleEncounter,
    mover: BattleCombatant,
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    settings: dict,
    rng: Random,
) -> list[dict]:
    if not settings.get("opportunity_attacks"):
        return []
    if (mover.resources_json or {}).get("disengage"):
        return []
    reach_cells = max(1, _melee_reach_ft(mover) // rules.GRID_CELL_FT)
    hostiles = [
        (c.id, c.x, c.y)
        for c in _active_combatants(encounter)
        if c.id != mover.id and c.side != mover.side and c.status == "active"
    ]
    triggered_ids = combat_profile.leaving_melee_reach(
        from_x, from_y, to_x, to_y, hostiles, reach_cells=reach_cells
    )
    results: list[dict] = []
    for cid in triggered_ids:
        reactor = combatant_in_encounter(encounter, cid)
        if reactor is None or combat_profile.incapacitated(list(reactor.conditions_json or [])):
            continue
        resources = dict(reactor.resources_json or _fresh_resources())
        if not resources.get("reaction", True):
            results.append({"reactor_id": cid, "skipped": "No reaction available."})
            continue
        attacks = (reactor.action_data_json or {}).get("attacks") or []
        melee = next(
            (a for a in attacks if str(a.get("kind") or "melee").lower() == "melee"),
            attacks[0] if attacks else None,
        )
        if not melee:
            results.append({"reactor_id": cid, "skipped": "No melee attack available."})
            continue
        target_ac, ac_detail = _effective_target_ac(
            encounter, reactor, mover, settings, attack_kind="melee"
        )
        roll_mode, _ = _attack_roll_mode(
            encounter, reactor, mover, melee, settings, "normal"
        )
        to_hit = _resolve_attack_to_hit(
            reactor, target_ac, int(melee.get("attack_mod") or 0), rng, roll_mode
        )
        entry = {
            "type": "opportunity_attack",
            "reactor_id": reactor.id,
            "target_id": mover.id,
            "attack": {"key": melee.get("key"), "name": melee.get("name")},
            "to_hit": to_hit,
            "ac_detail": ac_detail,
            "hit": to_hit["hit"],
            "crit": to_hit["crit"],
        }
        if to_hit["hit"]:
            crit = to_hit["crit"] and settings["crit_mode"] == "double_dice"
            damage = rules.roll_damage(str(melee.get("damage", "1d6")), rng, crit=crit)
            profile = _combat_profile(mover)
            modified = combat_profile.apply_damage_modifiers(
                damage["total"], melee.get("damage_type"), profile
            )
            damage = dict(damage)
            damage["total"] = modified["total"]
            damage["damage_modifiers"] = modified
            entry["damage_roll"] = damage
            if settings["auto_apply_damage"]:
                entry["outcome"] = _apply_outcome_to_target(
                    encounter,
                    mover,
                    damage["total"],
                    settings,
                    rng,
                    damage_type=melee.get("damage_type"),
                )
        resources["reaction"] = False
        reactor.resources_json = resources
        results.append(entry)
        _log(encounter, reactor, "opportunity_attack", entry)
    return results


# ---------------------------------------------------------------------------
# Grid dimension validation
# ---------------------------------------------------------------------------


def parse_grid_dimension(value, field_name: str = "Grid dimension") -> int:
    """Parse and validate a single grid axis; reject floats, bools, and 1e6-style input."""
    if isinstance(value, bool):
        raise CombatValidationError(f"{field_name} must be an integer.")
    if isinstance(value, float):
        raise CombatValidationError(f"{field_name} must be an integer.")
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in {"true", "false"}:
            raise CombatValidationError(f"{field_name} must be an integer.")
        lowered = cleaned.lower()
        if "e" in lowered or "." in cleaned:
            raise CombatValidationError(f"{field_name} must be an integer.")
        try:
            parsed = int(cleaned, 10)
        except ValueError as exc:
            raise CombatValidationError(f"{field_name} must be an integer.") from exc
        if str(parsed) != cleaned and str(parsed) != cleaned.lstrip("+"):
            raise CombatValidationError(f"{field_name} must be an integer.")
        value = parsed
    else:
        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise CombatValidationError(f"{field_name} must be an integer.") from exc
    if value > MAX_GRID_ABUSE:
        raise CombatValidationError(
            f"Grid dimensions cannot exceed {MAX_GRID_ABUSE}."
        )
    return value


def validate_grid_dimensions(width, height) -> tuple[int, int]:
    width = parse_grid_dimension(width, "Grid width")
    height = parse_grid_dimension(height, "Grid height")
    if not (MIN_GRID <= width <= MAX_GRID and MIN_GRID <= height <= MAX_GRID):
        raise CombatValidationError(
            f"Grid dimensions must be between {MIN_GRID} and {MAX_GRID}."
        )
    return width, height


# ---------------------------------------------------------------------------
# Encounter lifecycle
# ---------------------------------------------------------------------------

def create_encounter(campaign_id: int, name=None, grid_width=20, grid_height=20,
                     map_canvas_id=None, map_x=None, map_y=None,
                     terrain_preset=None) -> BattleEncounter:
    name = (str(name or "Encounter")).strip()[:120] or "Encounter"
    grid_width, grid_height = validate_grid_dimensions(grid_width, grid_height)
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
    if terrain_preset is not None:
        from app.services.combat import battle_map_service

        battle_map_service.initialize_generated_map(encounter, preset=terrain_preset)
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
    from app.services.combat import battle_map_service

    battle_map_service.cleanup_encounter_assets(encounter)
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


def _spell_attack_mod(combatant: BattleCombatant, *, level: int = 1) -> int:
    abilities = combatant.ability_json or {}
    ruleset = get_ruleset("dnd5e")
    prof = ruleset.proficiency_bonus(max(1, int(level or 1)))
    mods = [
        ruleset.compute_ability_mod(abilities.get(key, 10))
        for key in ("int", "wis", "cha")
    ]
    return max(mods) + prof


def _build_spell_slots_snapshot(class_row: dict | None) -> dict:
    slots = (class_row or {}).get("spell_slots") or {}
    snapshot: dict[str, dict[str, int]] = {}
    for key, total in slots.items():
        try:
            slot_total = int(total)
        except (TypeError, ValueError):
            continue
        if slot_total > 0:
            snapshot[str(key)] = {"total": slot_total, "remaining": slot_total}
    return snapshot


def _player_spell_keys(sheet: dict) -> list[str]:
    spells_state = sheet.get("spells") if isinstance(sheet.get("spells"), dict) else {}
    keys: list[str] = []
    seen: set[str] = set()
    for bucket in ("cantrips", "prepared", "known"):
        for raw in spells_state.get(bucket) or []:
            key = str(raw or "").strip()
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


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
    try:
        char_level = max(1, int(sheet.get("level") or 1))
    except (TypeError, ValueError):
        char_level = 1
    prof = ruleset.proficiency_bonus(char_level)

    from app.services.classes_compendium_service import (
        get_class_entry,
        resolve_character_class_details,
    )
    from app.services.combat.combat_profile_builder import (
        build_monster_combat_profile,
        build_player_combat_profile,
    )
    from app.services.species_compendium_service import get_species_entry
    from app.services.traits_compendium_service import ensure_traits_compendium

    ensure_traits_compendium(encounter.campaign_id)
    creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
    species_entry = get_species_entry(encounter.campaign_id, creation.get("species_key"))
    class_entry = get_class_entry(encounter.campaign_id, creation.get("class_key"))

    class_details = resolve_character_class_details(
        encounter.campaign_id,
        class_key=creation.get("class_key"),
        level=char_level,
        class_name_fallback=sheet.get("class_name"),
        owner_class_key=creation.get("class_key"),
    )
    from app.services.spells_compendium_service import combat_spell_snapshots

    spell_keys = _player_spell_keys(sheet)
    spell_snapshots = combat_spell_snapshots(encounter.campaign_id, spell_keys)
    spell_slots = _build_spell_slots_snapshot(class_details.get("current_level_row"))
    spell_mod = _spell_attack_mod(
        BattleCombatant(ability_json=abilities), level=char_level
    )

    from app.services.equipment.item_rules import (
        build_weapon_attacks,
        combat_equipment_snapshots,
        compute_equipment_ac,
        get_equipped_items,
    )

    equipped = get_equipped_items(player)
    equipment_ac = compute_equipment_ac(equipped, dex_mod=dex_mod)
    weapon_attacks = build_weapon_attacks(
        equipped, str_mod=str_mod, dex_mod=dex_mod, prof_bonus=prof
    )
    if not weapon_attacks:
        weapon_attacks = [
            {
                "key": "unarmed",
                "name": "Unarmed Strike",
                "kind": "melee",
                "attack_mod": str_mod + prof,
                "damage": f"1+{max(0, str_mod)}",
                "damage_type": "bludgeoning",
                "range_ft": 5,
                "automation": "auto",
            }
        ]
    equipment_snapshot = combat_equipment_snapshots(player)

    species_key = creation.get("species_key")
    player_combat_profile = build_player_combat_profile(
        encounter.campaign_id,
        sheet,
        species_entry=species_entry,
        class_entry=class_entry,
    )
    speed_ft = max(5, int(player_combat_profile.get("speed_ft") or 30))

    class_resources = dict((class_details.get("current_level_row") or {}).get("resources") or {})
    resources = _fresh_resources()
    if class_resources:
        resources["class_resources"] = class_resources

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
        ac=max(1, equipment_ac),
        speed_ft=speed_ft,
        dex_mod=dex_mod,
        ability_json=abilities,
        action_data_json={
            "attacks": weapon_attacks,
            "spells": spell_snapshots,
            "spell_attack_mod": spell_mod,
            "character_level": char_level,
            "equipment": equipment_snapshot,
            "save_prof_flags": dict(sheet.get("save_prof_flags") or {}),
            "combat_profile": player_combat_profile,
            "species_key": species_key,
            "class_key": creation.get("class_key"),
        },
        resources_json=resources,
        spell_slots_json=spell_slots,
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
    from app.services.combat.combat_profile_builder import build_monster_combat_profile
    from app.services.traits_compendium_service import ensure_traits_compendium

    ensure_traits_compendium(encounter.campaign_id)
    monster_combat_profile = build_monster_combat_profile(stats, encounter.campaign_id)
    legendary_max = int(monster_combat_profile.get("legendary_points_max") or 0)

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
            "combat_profile": monster_combat_profile,
        },
        resources_json=_fresh_resources(legendary_points_max=legendary_max),
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
    action_data = combatant.action_data_json or {}
    profile = combat_profile.profile_from_action_data(action_data)
    legendary_max = int(profile.get("legendary_points_max") or 0)
    if not legendary_max and (action_data.get("legendary_actions") or []):
        legendary_max = 3
    resources = dict(combatant.resources_json or _fresh_resources())
    resources["action"] = True
    resources["bonus_action"] = True
    resources["reaction"] = True
    resources["disengage"] = False
    if legendary_max > 0:
        resources["legendary_points_remaining"] = legendary_max
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
    if combat_profile.has_condition(list(combatant.conditions_json or []), "grappled"):
        raise CombatValidationError(f"{combatant.name} is grappled and cannot move.")

    to_x, to_y = _coerce_tile(encounter, to_x, to_y)
    settings = settings_for(encounter)
    from_x, from_y = combatant.x, combatant.y
    cost = rules.grid_distance_ft(
        from_x, from_y, to_x, to_y, settings["diagonal_mode"]
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

    rng = Random()
    opportunity_attacks = _resolve_opportunity_attacks(
        encounter,
        combatant,
        from_x,
        from_y,
        to_x,
        to_y,
        settings,
        rng,
    )

    from_pos = {"x": from_x, "y": from_y}
    combatant.x = to_x
    combatant.y = to_y
    combatant.movement_used_ft += cost
    encounter.turn_version += 1
    payload = {
        "from": from_pos,
        "to": {"x": to_x, "y": to_y},
        "cost_ft": cost,
        "movement_used_ft": combatant.movement_used_ft,
        "opportunity_attacks": opportunity_attacks,
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


def _get_concentration(resources: dict) -> dict | None:
    conc = resources.get("concentration")
    if isinstance(conc, dict) and conc.get("spell_key"):
        return conc
    return None


def _sync_concentrating_flag(resources: dict) -> dict:
    resources["concentrating"] = _get_concentration(resources) is not None
    return resources


def _clear_concentration_linked_effects(
    encounter: BattleEncounter,
    caster: BattleCombatant,
    linked_effects: list,
    settings: dict,
) -> list[dict]:
    if not settings.get("concentration_cleanup_tracked_effects", True):
        return []
    removed: list[dict] = []
    for effect in linked_effects or []:
        if not isinstance(effect, dict) or not effect.get("applied"):
            continue
        if effect.get("type") != "condition":
            continue
        target = combatant_in_encounter(encounter, effect.get("target_id")) or caster
        if target is None or not settings.get("conditions_enabled", True):
            continue
        cond = str(effect.get("value") or "").strip().lower()
        if not cond:
            continue
        conditions = list(target.conditions_json or [])
        if cond in conditions:
            conditions.remove(cond)
            target.conditions_json = conditions
            removed.append(effect)
    return removed


def _end_concentration(
    encounter: BattleEncounter,
    combatant: BattleCombatant,
    settings: dict,
    *,
    reason: str,
    log_actor: BattleCombatant | None = None,
) -> dict | None:
    resources = dict(combatant.resources_json or _fresh_resources())
    conc = _get_concentration(resources)
    if conc is None:
        return None
    linked = list(conc.get("linked_effects") or [])
    cleaned = _clear_concentration_linked_effects(
        encounter, combatant, linked, settings
    )
    resources["concentration"] = None
    _sync_concentrating_flag(resources)
    combatant.resources_json = resources
    payload = {
        "reason": reason,
        "ended_spell": {
            "key": conc.get("spell_key"),
            "name": conc.get("spell_name"),
        },
        "cleaned_effects": cleaned,
        "gm_manual_remainder": bool(linked and not cleaned),
    }
    _log(encounter, log_actor or combatant, "concentration_end", payload)
    return payload


def _register_concentration_linked_effects(
    spell: dict,
    target: BattleCombatant,
    *,
    apply_conditions: bool,
    settings: dict,
) -> list[dict]:
    linked: list[dict] = []
    for raw in spell.get("conditions") or []:
        cond = str(raw or "").strip().lower()
        if not cond:
            continue
        applied = False
        if apply_conditions and settings.get("conditions_enabled", True):
            conditions = list(target.conditions_json or [])
            if cond not in conditions:
                conditions.append(cond)
                target.conditions_json = conditions
                applied = True
        linked.append(
            {
                "type": "condition",
                "target_id": target.id,
                "value": cond,
                "applied": applied,
            }
        )
    return linked


def _start_concentration(
    encounter: BattleEncounter,
    caster: BattleCombatant,
    spell: dict,
    target: BattleCombatant,
    settings: dict,
) -> dict | None:
    if not settings.get("concentration_tracking", True):
        return None
    resources = dict(caster.resources_json or _fresh_resources())
    if settings.get("concentration_auto_replace", True) and _get_concentration(resources):
        _end_concentration(encounter, caster, settings, reason="replaced")
        resources = dict(caster.resources_json or _fresh_resources())

    from app.services.spells_compendium_service import is_direct_numeric_automation

    apply_conditions = is_direct_numeric_automation(spell.get("automation"))
    linked_effects = _register_concentration_linked_effects(
        spell,
        target,
        apply_conditions=apply_conditions,
        settings=settings,
    )
    resources["concentration"] = {
        "spell_key": spell.get("key"),
        "spell_name": spell.get("name"),
        "target_id": target.id,
        "round_number": encounter.round_number,
        "linked_effects": linked_effects,
    }
    _sync_concentrating_flag(resources)
    caster.resources_json = resources
    payload = {
        "spell": {"key": spell.get("key"), "name": spell.get("name")},
        "target_id": target.id,
        "linked_effects": linked_effects,
        "gm_manual_remainder": bool(
            (spell.get("conditions") or []) and not linked_effects
        ),
    }
    _log(encounter, caster, "concentration_start", payload)
    return resources["concentration"]


def _resolve_concentration_damage_check(
    combatant: BattleCombatant,
    damage_taken: int,
    settings: dict,
    rng: Random,
    *,
    gm_override=None,
) -> dict | None:
    con_mod = _save_modifier(combatant, "con")
    dc = rules.concentration_dc(damage_taken)
    mode = settings.get("concentration_check_mode", "server_and_gm")
    if mode == "gm_entered":
        if gm_override is None:
            return None
        success = bool(
            gm_override.get("success")
            if isinstance(gm_override, dict)
            else gm_override
        )
        return {
            "dc": dc,
            "success": success,
            "source": "gm_override",
            "ability_mod": con_mod,
        }
    if gm_override is not None and mode == "server_and_gm":
        success = bool(
            gm_override.get("success")
            if isinstance(gm_override, dict)
            else gm_override
        )
        return {
            "dc": dc,
            "success": success,
            "source": "gm_override",
            "ability_mod": con_mod,
        }
    save = _resolve_save_roll(combatant, "con", dc, rng, is_magic=True)
    save["source"] = "server_roll"
    return save


def _apply_outcome_to_target(
    encounter: BattleEncounter,
    target: BattleCombatant,
    damage_total: int,
    settings: dict,
    rng: Random,
    *,
    concentration_check_override=None,
    damage_type: str | None = None,
) -> dict:
    """Apply damage temp-HP-first; handle down/dead and concentration."""
    profile = _combat_profile(target)
    modified = combat_profile.apply_damage_modifiers(damage_total, damage_type, profile)
    damage_total = modified["total"]

    outcome = rules.apply_damage(target.hp_current, target.temp_hp, damage_total)
    relentless = False
    if (
        outcome["hp_current"] <= 0
        and target.status == "active"
        and profile.get("relentless_endurance")
    ):
        resources = dict(target.resources_json or _fresh_resources())
        if not resources.get("relentless_endurance_used"):
            outcome["hp_current"] = 1
            outcome["taken"] = max(0, target.hp_current - 1)
            resources["relentless_endurance_used"] = True
            target.resources_json = resources
            relentless = True

    target.hp_current = outcome["hp_current"]
    target.temp_hp = outcome["temp_hp"]

    result = {
        "damage": outcome,
        "damage_modifiers": modified,
        "target_status": target.status,
    }
    if relentless:
        result["relentless_endurance"] = True
    if target.hp_current <= 0 and target.status == "active" and not relentless:
        if target.player_id is not None and settings["death_saves"]:
            target.status = "down"
        else:
            target.status = "dead"
        result["target_status"] = target.status

    resources = dict(target.resources_json or _fresh_resources())
    conc = _get_concentration(resources)
    if (
        settings.get("concentration_checks", True)
        and settings.get("concentration_tracking", True)
        and outcome["taken"] > 0
        and conc is not None
        and target.status == "active"
    ):
        save = _resolve_concentration_damage_check(
            target,
            outcome["taken"],
            settings,
            rng,
            gm_override=concentration_check_override,
        )
        if save is not None:
            result["concentration"] = save
            if not save["success"]:
                _end_concentration(
                    encounter,
                    target,
                    settings,
                    reason="damage_check_failed",
                )

    if (
        target.status in ("down", "dead")
        and settings.get("concentration_tracking", True)
        and _get_concentration(dict(target.resources_json or {}))
    ):
        end_payload = _end_concentration(
            encounter,
            target,
            settings,
            reason="incapacitated",
        )
        if end_payload:
            result["concentration_end"] = end_payload
    return result


def attack_action(encounter: BattleEncounter, attacker: BattleCombatant,
                  target_id, attack_key, rng: Random,
                  roll_mode: str = "normal") -> dict:
    """Fully resolve one attack: to-hit, damage, HP application, conditions."""
    _require_active(encounter)
    _require_turn(encounter, attacker)
    if attacker.status != "active":
        raise CombatValidationError(f"{attacker.name} cannot act right now.")
    if combat_profile.incapacitated(list(attacker.conditions_json or [])):
        raise CombatValidationError(f"{attacker.name} is incapacitated.")

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
    effective_ac, ac_detail = _effective_target_ac(
        encounter, attacker, target, settings, attack_kind=str(attack.get("kind") or "melee")
    )
    resolved_mode, roll_detail = _attack_roll_mode(
        encounter, attacker, target, attack, settings, roll_mode
    )
    to_hit = _resolve_attack_to_hit(
        attacker, effective_ac, int(attack.get("attack_mod", 0)), rng, resolved_mode
    )
    result = {
        "attacker_id": attacker.id,
        "target_id": target.id,
        "attack": {"key": attack.get("key"), "name": attack.get("name")},
        "distance_ft": distance,
        "to_hit": to_hit,
        "ac_detail": ac_detail,
        "roll_detail": roll_detail,
        "hit": to_hit["hit"],
        "crit": to_hit["crit"],
    }
    if to_hit["hit"]:
        crit = to_hit["crit"] and settings["crit_mode"] == "double_dice"
        damage = rules.roll_damage(str(attack.get("damage", "1d6")), rng, crit=crit)
        profile = _combat_profile(attacker)
        extra = combat_profile.savage_attacks_extra_damage(
            str(attack.get("damage", "1d6")),
            rng,
            enabled=bool(profile.get("savage_attacks")),
            crit=to_hit["crit"],
            melee=str(attack.get("kind") or "melee").lower() == "melee",
        )
        if extra:
            damage = dict(damage)
            damage["total"] += extra["total"]
            damage["savage_attacks"] = extra
        target_profile = _combat_profile(target)
        modified = combat_profile.apply_damage_modifiers(
            damage["total"], attack.get("damage_type"), target_profile
        )
        damage = dict(damage)
        damage["total"] = modified["total"]
        damage["damage_modifiers"] = modified
        result["damage_roll"] = damage
        if settings["auto_apply_damage"]:
            result["outcome"] = _apply_outcome_to_target(
                encounter,
                target,
                damage["total"],
                settings,
                rng,
                damage_type=attack.get("damage_type"),
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
        if combatant.status != "active":
            results.append(
                {"attacker_id": attacker.id, "skipped": f"{combatant.name} cannot act."}
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
        effective_ac, ac_detail = _effective_target_ac(
            encounter, attacker, target, settings, attack_kind=str(attack.get("kind") or "melee")
        )
        resolved_mode, roll_detail = _attack_roll_mode(
            encounter, attacker, target, attack, settings, roll_mode
        )
        to_hit = _resolve_attack_to_hit(
            attacker, effective_ac, int(attack.get("attack_mod", 0)), rng, resolved_mode
        )
        entry = {
            "attacker_id": attacker.id,
            "target_id": target.id,
            "to_hit": to_hit,
            "ac_detail": ac_detail,
            "roll_detail": roll_detail,
            "hit": to_hit["hit"],
            "crit": to_hit["crit"],
        }
        if to_hit["hit"]:
            crit = to_hit["crit"] and settings["crit_mode"] == "double_dice"
            damage = rules.roll_damage(str(attack.get("damage", "1d6")), rng, crit=crit)
            target_profile = _combat_profile(target)
            modified = combat_profile.apply_damage_modifiers(
                damage["total"], attack.get("damage_type"), target_profile
            )
            damage = dict(damage)
            damage["total"] = modified["total"]
            damage["damage_modifiers"] = modified
            entry["damage_roll"] = damage
            if settings["auto_apply_damage"]:
                entry["outcome"] = _apply_outcome_to_target(
                    encounter,
                    target,
                    damage["total"],
                    settings,
                    rng,
                    damage_type=attack.get("damage_type"),
                )
        resources["action"] = False
        attacker.resources_json = resources
        results.append(entry)

    encounter.turn_version += 1
    _log(encounter, current, "batch_attack", {"results_count": len(results)})
    db.session.flush()
    return results


def _spell_definition(combatant: BattleCombatant, spell_key) -> dict:
    spells = (combatant.action_data_json or {}).get("spells") or []
    needle = str(spell_key or "").strip().lower()
    for spell in spells:
        if str(spell.get("key") or "").lower() == needle:
            return spell
    raise CombatValidationError("Unknown spell for this combatant.")


def _spell_uses_bonus_action(spell: dict) -> bool:
    return "bonus action" in str(spell.get("casting_time") or "").lower()


def _consume_spell_slot(combatant: BattleCombatant, cast_level: int) -> None:
    if cast_level <= 0:
        return
    slots = dict(combatant.spell_slots_json or {})
    bucket = slots.get(str(cast_level))
    if not isinstance(bucket, dict):
        raise CombatValidationError(f"No spell slot available at level {cast_level}.")
    remaining = int(bucket.get("remaining") or 0)
    if remaining <= 0:
        raise CombatValidationError(f"No spell slot available at level {cast_level}.")
    bucket = dict(bucket)
    bucket["remaining"] = remaining - 1
    slots[str(cast_level)] = bucket
    combatant.spell_slots_json = slots


def _roll_spell_damage(spell: dict, cast_level: int, rng: Random, *, crit: bool = False) -> dict | None:
    notation = spell.get("damage")
    if not notation:
        return None
    damage = rules.roll_damage(str(notation), rng, crit=crit)
    base_level = int(spell.get("level") or 0)
    upcast = spell.get("upcast") or {}
    per_slot = upcast.get("damage_per_slot")
    if cast_level > base_level and per_slot:
        slots_above = cast_level - max(base_level, 1)
        for _ in range(slots_above):
            extra = rules.roll_damage(str(per_slot), rng)
            damage["total"] += extra["total"]
            damage.setdefault("upcast_rolls", []).append(extra)
    return damage


def _roll_spell_healing(spell: dict, cast_level: int, rng: Random) -> dict | None:
    notation = spell.get("healing")
    if not notation:
        return None
    healing = rules.roll_damage(str(notation), rng)
    base_level = int(spell.get("level") or 0)
    upcast = spell.get("upcast") or {}
    per_slot = upcast.get("healing_per_slot")
    if cast_level > base_level and per_slot:
        slots_above = cast_level - max(base_level, 1)
        for _ in range(slots_above):
            extra = rules.roll_damage(str(per_slot), rng)
            healing["total"] += extra["total"]
            healing.setdefault("upcast_rolls", []).append(extra)
    return healing


def cast_spell_action(
    encounter: BattleEncounter,
    attacker: BattleCombatant,
    target_id,
    spell_key,
    cast_level,
    rng: Random,
    roll_mode: str = "normal",
    *,
    concentration_check_override=None,
) -> dict:
    """Resolve a prepared spell from the combatant snapshot."""
    from app.services.spells_compendium_service import (
        AUTOMATION_MANUAL,
        is_direct_numeric_automation,
        normalize_automation,
    )

    _require_active(encounter)
    _require_turn(encounter, attacker)
    if attacker.status != "active":
        raise CombatValidationError(f"{attacker.name} cannot act right now.")

    spell = _spell_definition(attacker, spell_key)
    try:
        spell_level = int(spell.get("level") or 0)
    except (TypeError, ValueError):
        spell_level = 0
    try:
        cast_level_int = spell_level if cast_level in (None, "") else int(cast_level)
    except (TypeError, ValueError):
        raise CombatValidationError("cast_level must be an integer.")
    if cast_level_int < spell_level or cast_level_int > 9:
        raise CombatValidationError(
            f"cast_level must be between {spell_level} and 9."
        )

    target = combatant_in_encounter(encounter, target_id)
    if target is None or target.status in ("dead", "removed"):
        raise CombatValidationError("Target not found in this encounter.")

    settings = settings_for(encounter)
    resources = dict(attacker.resources_json or _fresh_resources())
    uses_bonus = _spell_uses_bonus_action(spell)
    if settings["track_action_economy"]:
        economy_key = "bonus_action" if uses_bonus else "action"
        if not resources.get(economy_key, True):
            raise CombatValidationError(
                f"{attacker.name} has already used their {'bonus action' if uses_bonus else 'action'}."
            )

    distance = rules.grid_distance_ft(
        attacker.x, attacker.y, target.x, target.y, settings["diagonal_mode"]
    )
    range_ft = int(spell.get("range_ft") or 0)
    if range_ft > 0 and target.id != attacker.id and distance > range_ft:
        raise CombatValidationError(
            f"Target is out of range ({distance} ft > {range_ft} ft)."
        )

    automation = normalize_automation(spell.get("automation"))
    direct_numeric = is_direct_numeric_automation(automation)
    consume_slot = (
        settings["track_spell_slots"]
        and cast_level_int > 0
        and (
            direct_numeric
            or settings.get("manual_spell_slot_consumption", True)
        )
    )
    if consume_slot:
        _consume_spell_slot(attacker, cast_level_int)

    action_data = dict(attacker.action_data_json or {})
    spell_mod = int(action_data.get("spell_attack_mod") or 0)
    auto_resolve = (
        direct_numeric and settings.get("direct_numeric_auto_resolution", True)
    )
    manual_resolution = automation == AUTOMATION_MANUAL or not auto_resolve

    result: dict = {
        "attacker_id": attacker.id,
        "target_id": target.id,
        "spell": {"key": spell.get("key"), "name": spell.get("name"), "level": spell_level},
        "cast_level": cast_level_int,
        "distance_ft": distance,
        "automation": automation,
        "manual_resolution": manual_resolution,
    }

    if auto_resolve:
        spell_dtype = spell.get("damage_type")
        attack_type = spell.get("attack_type")
        if attack_type == "spell_attack" and spell.get("damage"):
            if roll_mode not in rules.ROLL_MODES:
                raise CombatValidationError("Invalid roll mode.")
            effective_ac, ac_detail = _effective_target_ac(
                encounter,
                attacker,
                target,
                settings,
                attack_kind="ranged",
            )
            atk_part, tgt_part = combat_profile.condition_attack_modifiers(
                list(attacker.conditions_json or []),
                list(target.conditions_json or []),
                attack_kind="ranged",
            )
            modes = [roll_mode, atk_part]
            if tgt_part == "advantage":
                modes.append("advantage")
            elif tgt_part == "disadvantage":
                modes.append("disadvantage")
            resolved_mode = combat_profile.combine_roll_modes(*modes)
            profile = _combat_profile(attacker)
            to_hit = combat_profile.roll_d20_with_lucky(
                spell_mod, rng, resolved_mode, profile
            )
            crit = to_hit["is_nat20"]
            hit = crit or (not to_hit["is_nat1"] and to_hit["total"] >= effective_ac)
            to_hit.update({"hit": hit, "crit": crit, "target_ac": effective_ac})
            result["to_hit"] = to_hit
            result["ac_detail"] = ac_detail
            result["hit"] = to_hit["hit"]
            if to_hit["hit"]:
                crit = to_hit["crit"] and settings["crit_mode"] == "double_dice"
                damage = _roll_spell_damage(spell, cast_level_int, rng, crit=crit)
                if damage:
                    modified = combat_profile.apply_damage_modifiers(
                        damage["total"], spell_dtype, _combat_profile(target)
                    )
                    damage = dict(damage)
                    damage["total"] = modified["total"]
                    damage["damage_modifiers"] = modified
                result["damage_roll"] = damage
                if damage and settings["auto_apply_damage"]:
                    result["outcome"] = _apply_outcome_to_target(
                        encounter,
                        target,
                        damage["total"],
                        settings,
                        rng,
                        concentration_check_override=concentration_check_override,
                        damage_type=spell_dtype,
                    )
        elif attack_type == "save" and spell.get("damage"):
            save_ability = str(spell.get("save_ability") or "dex")
            save = _resolve_save_roll(
                target,
                save_ability,
                8 + spell_mod,
                rng,
                client_mode=roll_mode,
                is_magic=True,
            )
            result["save"] = save
            damage = _roll_spell_damage(spell, cast_level_int, rng)
            if damage and save.get("success"):
                damage = dict(damage)
                damage["total"] = damage["total"] // 2
            if damage:
                modified = combat_profile.apply_damage_modifiers(
                    damage["total"], spell_dtype, _combat_profile(target)
                )
                damage = dict(damage)
                damage["total"] = modified["total"]
                damage["damage_modifiers"] = modified
            result["damage_roll"] = damage
            if damage and settings["auto_apply_damage"] and damage["total"] > 0:
                result["outcome"] = _apply_outcome_to_target(
                    encounter,
                    target,
                    damage["total"],
                    settings,
                    rng,
                    concentration_check_override=concentration_check_override,
                    damage_type=spell_dtype,
                )
        elif spell.get("damage") and not attack_type:
            damage = _roll_spell_damage(spell, cast_level_int, rng)
            if damage:
                modified = combat_profile.apply_damage_modifiers(
                    damage["total"], spell_dtype, _combat_profile(target)
                )
                damage = dict(damage)
                damage["total"] = modified["total"]
                damage["damage_modifiers"] = modified
            result["damage_roll"] = damage
            if damage and settings["auto_apply_damage"]:
                result["outcome"] = _apply_outcome_to_target(
                    encounter,
                    target,
                    damage["total"],
                    settings,
                    rng,
                    concentration_check_override=concentration_check_override,
                    damage_type=spell_dtype,
                )
        elif spell.get("healing"):
            healing = _roll_spell_healing(spell, cast_level_int, rng)
            result["healing_roll"] = healing
            if healing and settings["auto_apply_damage"] and target.status == "active":
                target.hp_current = min(
                    target.hp_max, target.hp_current + healing["total"]
                )
                result["healing_applied"] = healing["total"]

    if spell.get("concentration"):
        conc_state = _start_concentration(encounter, attacker, spell, target, settings)
        if conc_state is not None:
            result["concentration"] = conc_state

    if settings["track_action_economy"]:
        resources = dict(attacker.resources_json or _fresh_resources())
        if uses_bonus:
            resources["bonus_action"] = False
        else:
            resources["action"] = False
        attacker.resources_json = resources

    encounter.turn_version += 1
    _log(encounter, attacker, "cast_spell", result)
    db.session.flush()
    return result


def disengage_action(encounter: BattleEncounter, combatant: BattleCombatant) -> dict:
    """Use an action to disengage — movement will not provoke opportunity attacks."""
    _require_active(encounter)
    _require_turn(encounter, combatant)
    settings = settings_for(encounter)
    resources = dict(combatant.resources_json or _fresh_resources())
    if settings["track_action_economy"] and not resources.get("action", True):
        raise CombatValidationError(f"{combatant.name} has already used their action.")
    resources["disengage"] = True
    if settings["track_action_economy"]:
        resources["action"] = False
    combatant.resources_json = resources
    encounter.turn_version += 1
    payload = {"disengage": True}
    _log(encounter, combatant, "disengage", payload)
    db.session.flush()
    return payload


def _legendary_action_definition(combatant: BattleCombatant, action_key: str) -> dict:
    actions = (combatant.action_data_json or {}).get("legendary_actions") or []
    needle = str(action_key or "").strip().lower()
    for action in actions:
        if str(action.get("key") or "").lower() == needle:
            return action
    raise CombatValidationError("Unknown legendary action for this combatant.")


def legendary_action(
    encounter: BattleEncounter,
    actor: BattleCombatant,
    action_key: str,
    target_id,
    rng: Random,
    *,
    roll_mode: str = "normal",
) -> dict:
    """Resolve a legendary action at the end of another creature's turn (SRD)."""
    _require_active(encounter)
    current = current_combatant(encounter)
    if current is not None and current.id == actor.id:
        raise CombatValidationError(
            "Legendary actions are taken at the end of another creature's turn."
        )
    legendary_defs = (actor.action_data_json or {}).get("legendary_actions") or []
    if not legendary_defs:
        raise CombatValidationError(f"{actor.name} has no legendary actions.")
    if actor.status != "active":
        raise CombatValidationError(f"{actor.name} cannot take legendary actions.")

    action = _legendary_action_definition(actor, action_key)
    try:
        cost = max(1, int(action.get("cost") or 1))
    except (TypeError, ValueError):
        cost = 1

    profile = _combat_profile(actor)
    legendary_max = int(profile.get("legendary_points_max") or 3)
    resources = dict(actor.resources_json or _fresh_resources())
    remaining = int(resources.get("legendary_points_remaining", legendary_max))
    if remaining < cost:
        raise CombatValidationError(
            f"Not enough legendary action points ({remaining} remaining, {cost} required)."
        )

    target = combatant_in_encounter(encounter, target_id)
    if target is None or target.status in ("dead", "removed"):
        raise CombatValidationError("Target not found in this encounter.")

    settings = settings_for(encounter)
    distance = rules.grid_distance_ft(
        actor.x, actor.y, target.x, target.y, settings["diagonal_mode"]
    )
    range_ft = int(action.get("range_ft") or 5)
    if distance > range_ft:
        raise CombatValidationError(
            f"Target is out of range ({distance} ft > {range_ft} ft)."
        )

    result: dict = {
        "actor_id": actor.id,
        "target_id": target.id,
        "legendary_action": {"key": action.get("key"), "name": action.get("name"), "cost": cost},
        "distance_ft": distance,
        "legendary_points_before": remaining,
    }

    attack_mod = action.get("attack_mod")
    if attack_mod is not None:
        if roll_mode not in rules.ROLL_MODES:
            raise CombatValidationError("Invalid roll mode.")
        effective_ac, ac_detail = _effective_target_ac(
            encounter,
            actor,
            target,
            settings,
            attack_kind="melee" if range_ft <= 5 else "ranged",
        )
        pseudo_attack = {
            "kind": "melee" if range_ft <= 5 else "ranged",
            "range_ft": range_ft,
        }
        resolved_mode, roll_detail = _attack_roll_mode(
            encounter, actor, target, pseudo_attack, settings, roll_mode
        )
        to_hit = _resolve_attack_to_hit(
            actor, effective_ac, int(attack_mod), rng, resolved_mode
        )
        result.update(
            {
                "to_hit": to_hit,
                "ac_detail": ac_detail,
                "roll_detail": roll_detail,
                "hit": to_hit["hit"],
                "crit": to_hit["crit"],
            }
        )
        if to_hit["hit"] and action.get("damage"):
            crit = to_hit["crit"] and settings["crit_mode"] == "double_dice"
            damage = rules.roll_damage(str(action.get("damage")), rng, crit=crit)
            modified = combat_profile.apply_damage_modifiers(
                damage["total"], action.get("damage_type"), _combat_profile(target)
            )
            damage = dict(damage)
            damage["total"] = modified["total"]
            damage["damage_modifiers"] = modified
            result["damage_roll"] = damage
            if settings["auto_apply_damage"]:
                result["outcome"] = _apply_outcome_to_target(
                    encounter,
                    target,
                    damage["total"],
                    settings,
                    rng,
                    damage_type=action.get("damage_type"),
                )

    resources["legendary_points_remaining"] = remaining - cost
    actor.resources_json = resources
    result["legendary_points_remaining"] = resources["legendary_points_remaining"]
    encounter.turn_version += 1
    _log(encounter, actor, "legendary_action", result)
    db.session.flush()
    return result


def end_concentration_action(
    encounter: BattleEncounter,
    combatant: BattleCombatant,
    *,
    role: str = "gm",
) -> dict:
    """Manually end combat-local concentration for an authorized actor."""
    _require_active(encounter)
    settings = settings_for(encounter)
    if not settings.get("concentration_tracking", True):
        raise CombatValidationError("Concentration tracking is disabled.")
    if role != "gm" and not settings.get("player_concentration_end", False):
        raise CombatValidationError("Players cannot end concentration in this encounter.")
    resources = dict(combatant.resources_json or _fresh_resources())
    if _get_concentration(resources) is None:
        raise CombatValidationError(f"{combatant.name} is not concentrating.")
    payload = _end_concentration(encounter, combatant, settings, reason="manual")
    encounter.turn_version += 1
    db.session.flush()
    return payload or {}


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
    profile = _combat_profile(combatant)
    if profile.get("lucky") and roll.get("natural") == 1:
        reroll = rules.roll_death_save(rng)
        reroll["lucky_reroll"] = True
        reroll["discarded_natural"] = 1
        roll = reroll
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
