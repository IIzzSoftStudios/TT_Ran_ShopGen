"""GM vs player JSON payloads for battle encounters.

GMs see full state. Players see the board and turn order, but foe HP is
reduced to a coarse health state (healthy/bloodied/down) and foe resource
internals are hidden.
"""

from __future__ import annotations

from app.models import BattleActionLog, BattleCombatant, BattleEncounter
from app.services.combat import encounter_service


def _health_state(combatant: BattleCombatant) -> str:
    if combatant.status in ("dead", "removed"):
        return "down"
    if combatant.status in ("down", "stable"):
        return "down"
    if combatant.hp_max > 0 and combatant.hp_current * 2 <= combatant.hp_max:
        return "bloodied"
    return "healthy"


def serialize_combatant(combatant: BattleCombatant, *, for_gm: bool,
                        viewer_player_id=None) -> dict:
    is_own = (
        viewer_player_id is not None and combatant.player_id == viewer_player_id
    )
    base = {
        "id": combatant.id,
        "name": combatant.name,
        "side": combatant.side,
        "status": combatant.status,
        "x": combatant.x,
        "y": combatant.y,
        "speed_ft": combatant.speed_ft,
        "initiative": combatant.initiative,
        "initiative_order": combatant.initiative_order,
        "has_waited": combatant.has_waited,
        "conditions": list(combatant.conditions_json or []),
        "player_id": combatant.player_id,
        "health_state": _health_state(combatant),
    }
    if for_gm or is_own or combatant.side == "party":
        base.update(
            {
                "hp_max": combatant.hp_max,
                "hp_current": combatant.hp_current,
                "temp_hp": combatant.temp_hp,
                "ac": combatant.ac,
                "movement_used_ft": combatant.movement_used_ft,
                "resources": dict(combatant.resources_json or {}),
                "attacks": list(
                    (combatant.action_data_json or {}).get("attacks") or []
                ),
                "legendary_actions": list(
                    (combatant.action_data_json or {}).get("legendary_actions") or []
                ),
            }
        )
    if for_gm:
        base.update(
            {
                "dex_mod": combatant.dex_mod,
                "abilities": dict(combatant.ability_json or {}),
                "spell_slots": dict(combatant.spell_slots_json or {}),
                "compendium_entry_id": combatant.compendium_entry_id,
            }
        )
    return base


def serialize_encounter(encounter: BattleEncounter, *, for_gm: bool,
                        viewer_player_id=None, log_limit: int = 25) -> dict:
    combatants = (
        BattleCombatant.query.filter(
            BattleCombatant.encounter_id == encounter.id,
            BattleCombatant.status != "removed",
        )
        .order_by(BattleCombatant.id.asc())
        .all()
    )
    current = encounter_service.current_combatant(encounter)
    logs = (
        BattleActionLog.query.filter_by(encounter_id=encounter.id)
        .order_by(BattleActionLog.id.desc())
        .limit(log_limit)
        .all()
    )
    return {
        "id": encounter.id,
        "name": encounter.name,
        "status": encounter.status,
        "visible_to_players": bool(encounter.visible_to_players),
        "map_canvas_id": encounter.map_canvas_id,
        "map_x": encounter.map_x,
        "map_y": encounter.map_y,
        "grid_width": encounter.grid_width,
        "grid_height": encounter.grid_height,
        "round_number": encounter.round_number,
        "turn_index": encounter.turn_index,
        "turn_version": encounter.turn_version,
        "current_combatant_id": current.id if current else None,
        "settings": encounter_service.settings_for(encounter),
        "combatants": [
            serialize_combatant(
                c, for_gm=for_gm, viewer_player_id=viewer_player_id
            )
            for c in combatants
        ],
        "log": [
            {
                "id": entry.id,
                "round": entry.round_number,
                "type": entry.action_type,
                "combatant_id": entry.combatant_id,
                "payload": entry.payload_json or {},
            }
            for entry in logs
        ],
    }


def serialize_encounter_summary(encounter: BattleEncounter) -> dict:
    return {
        "id": encounter.id,
        "name": encounter.name,
        "status": encounter.status,
        "visible_to_players": bool(encounter.visible_to_players),
        "map_canvas_id": encounter.map_canvas_id,
        "map_x": encounter.map_x,
        "map_y": encounter.map_y,
        "round_number": encounter.round_number,
        "turn_version": encounter.turn_version,
        "grid_width": encounter.grid_width,
        "grid_height": encounter.grid_height,
    }
