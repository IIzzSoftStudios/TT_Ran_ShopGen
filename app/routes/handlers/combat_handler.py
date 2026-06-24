"""JSON handlers for the D&D 5e tactical combat API (/api/combat/*).

Authority rules (mirrors gm_maps_handler):

- Campaign authority for GM endpoints comes from the GM session only;
  client payloads are never trusted for ``campaign_id``.
- Player access is derived from the encounter row: the user must own a
  non-NPC Player in the encounter's campaign, and may only act through
  combatants bound to their own ``player_id``.
- Every combat surface is gated to campaigns whose ``system_type``
  resolves to the ``dnd5e`` ruleset; everything else gets a 403.
- Mutations lock the encounter row and verify ``turn_version`` under the
  lock; stale clients receive 409.
"""

import logging
from random import Random

from flask import jsonify, request, send_file, session
from flask_login import current_user, login_required

from app.extensions import db
from app.models import BattleCombatant, Campaign, Player
from app.services.combat import (
    CombatValidationError,
    StaleTurnError,
    encounter_service,
    monster_compendium_service,
    serializers,
    settings_service,
)
from app.services.combat.battle_map_service import BattleMapValidationError
from app.services.combat import battle_map_service
from app.services.combat.monster_catalog_service import (
    MonsterCatalogError,
    ensure_srd_monsters_for_campaign,
    seed_srd_monsters_if_dnd5e,
)
from app.services.player_resolution import all_player_ids_for_user
from app.services.rulesets import get_ruleset

log = logging.getLogger(__name__)

DND5E_ONLY_ERROR = "Combat is only available for D&D 5e campaigns."


# ---------------------------------------------------------------------------
# Auth / gating helpers
# ---------------------------------------------------------------------------

def _require_dnd5e(campaign):
    """Return a (response, status) error tuple unless the campaign is D&D 5e."""
    if get_ruleset(campaign.system_type).system_type != "dnd5e":
        return jsonify({"error": DND5E_ONLY_ERROR}), 403
    return None


def _gm_campaign_for_json():
    """Resolve the active GM campaign for JSON endpoints (session-derived).

    Returns ``(campaign, None)`` or ``(None, (json_response, status))``.
    """
    if session.get("session_mode") == "player":
        return None, (jsonify({"error": "GM session required."}), 403)
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        return None, (jsonify({"error": "A Game Master profile is required."}), 403)
    cid = session.get("campaign_id")
    if not cid:
        return None, (jsonify({"error": "Select a campaign first."}), 400)
    campaign = Campaign.query.filter_by(id=cid, gm_profile_id=profile.id).first()
    if campaign is None:
        return None, (jsonify({"error": "Active campaign not found."}), 404)
    return campaign, None


def _gm_dnd5e_campaign_for_json():
    campaign, err = _gm_campaign_for_json()
    if err:
        return None, err
    gate = _require_dnd5e(campaign)
    if gate:
        return None, gate
    return campaign, None


def _is_gm_of(campaign) -> bool:
    profile = getattr(current_user, "gm_profile", None)
    return (
        profile is not None
        and campaign.gm_profile_id == profile.id
        and session.get("session_mode") != "player"
        and session.get("campaign_id") == campaign.id
    )


def _viewer_context(encounter):
    """Resolve viewer role for an encounter: ('gm'|'player', player_ids) or error.

    Players must own at least one non-NPC character inside the encounter's
    campaign; everyone else gets a 403.
    """
    campaign = encounter.campaign
    gate = _require_dnd5e(campaign)
    if gate:
        return None, None, gate
    if _is_gm_of(campaign):
        return "gm", [], None
    player_ids = [
        pid
        for pid in all_player_ids_for_user(current_user)
        if Player.query.filter_by(id=pid, campaign_id=campaign.id).first() is not None
    ]
    if not player_ids:
        return None, None, (jsonify({"error": "You are not part of this campaign."}), 403)
    if not bool(encounter.visible_to_players):
        return None, None, (jsonify({"error": "Encounter not found."}), 404)
    return "player", player_ids, None


def _encounter_or_404(encounter_id):
    from app.models import BattleEncounter

    encounter = BattleEncounter.query.filter_by(id=encounter_id).first()
    if encounter is None:
        return None, (jsonify({"error": "Encounter not found."}), 404)
    return encounter, None


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _error_response(exc):
    """Map service exceptions to JSON errors; rolls back the session."""
    db.session.rollback()
    if isinstance(exc, StaleTurnError):
        return jsonify({"error": str(exc)}), 409
    if isinstance(exc, (CombatValidationError, BattleMapValidationError)):
        return jsonify({"error": str(exc)}), 400
    if isinstance(exc, LookupError):
        return jsonify({"error": str(exc)}), 404
    log.exception("combat_request_failed")
    return jsonify({"error": "Combat request failed."}), 500


def _locked_encounter_for_mutation(encounter, data):
    """Re-fetch the encounter FOR UPDATE, verifying turn_version under lock."""
    return encounter_service.locked_encounter(
        encounter.id, encounter.campaign_id, data.get("turn_version")
    )


def _actor_combatant(encounter, data, role, player_ids):
    combatant = encounter_service.combatant_in_encounter(
        encounter, data.get("combatant_id")
    )
    if combatant is None:
        raise LookupError("Combatant not found in this encounter.")
    if role != "gm" and combatant.player_id not in player_ids:
        raise CombatValidationError("You can only act through your own character.")
    return combatant


# ---------------------------------------------------------------------------
# Encounters (GM)
# ---------------------------------------------------------------------------

@login_required
def list_encounters():
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    return jsonify(
        {
            "encounters": [
                serializers.serialize_encounter_summary(e)
                for e in encounter_service.list_encounters(campaign.id)
            ]
        }
    )


@login_required
def create_encounter():
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        encounter = encounter_service.create_encounter(
            campaign.id,
            name=data.get("name"),
            grid_width=data.get("grid_width", 20),
            grid_height=data.get("grid_height", 20),
            map_canvas_id=data.get("map_canvas_id"),
            map_x=data.get("x"),
            map_y=data.get("y"),
            terrain_preset=data.get("terrain_preset"),
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {"success": True, "encounter": serializers.serialize_encounter(encounter, for_gm=True)}
    ), 201


@login_required
def get_encounter(encounter_id):
    encounter, err = _encounter_or_404(encounter_id)
    if err:
        return err
    role, player_ids, err = _viewer_context(encounter)
    if err:
        return err
    viewer_player_id = player_ids[0] if player_ids else None
    payload = serializers.serialize_encounter(
        encounter,
        for_gm=(role == "gm"),
        viewer_player_id=viewer_player_id,
    )
    if role == "player":
        payload["own_player_ids"] = player_ids
    return jsonify(payload)


@login_required
def end_encounter(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        encounter = encounter_service.locked_encounter(
            encounter_id, campaign.id, data.get("turn_version")
        )
        encounter_service.end_encounter(encounter)
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify({"success": True, "status": "ended"})


@login_required
def rename_encounter(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "name is required."}), 400
    try:
        encounter = encounter_service.locked_encounter(encounter_id, campaign.id)
        encounter_service.rename_encounter(encounter, name)
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "encounter": serializers.serialize_encounter_summary(encounter),
        }
    )


@login_required
def delete_encounter(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    try:
        encounter = encounter_service.locked_encounter(encounter_id, campaign.id)
        encounter_service.delete_encounter(encounter)
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify({"success": True})


@login_required
def set_encounter_visibility(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        encounter = encounter_service.locked_encounter(encounter_id, campaign.id)
        encounter_service.set_player_visibility(
            encounter,
            data.get("visible_to_players"),
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "encounter": serializers.serialize_encounter_summary(encounter),
        }
    )


@login_required
def place_encounter(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        encounter = encounter_service.locked_encounter(encounter_id, campaign.id)
        encounter_service.place_encounter_on_canvas(
            encounter,
            campaign.id,
            data.get("map_canvas_id"),
            data.get("x"),
            data.get("y"),
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "encounter": serializers.serialize_encounter_summary(encounter),
        }
    )


@login_required
def lookup_encounter_for_canvas(canvas_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    from app.models import MapCanvas

    canvas = MapCanvas.query.filter_by(id=canvas_id, campaign_id=campaign.id).first()
    if canvas is None:
        return jsonify({"error": "Map canvas not found in this campaign."}), 404
    encounter = encounter_service.encounter_for_canvas(campaign.id, canvas.id)
    return jsonify(
        {
            "encounter": (
                serializers.serialize_encounter_summary(encounter)
                if encounter is not None
                else None
            )
        }
    )


@login_required
def get_or_create_encounter_for_canvas(canvas_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        encounter, created = encounter_service.get_or_create_encounter_for_canvas(
            campaign.id,
            canvas_id,
            name=data.get("name"),
            x=data.get("x"),
            y=data.get("y"),
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    status = 201 if created else 200
    return jsonify(
        {
            "success": True,
            "created": created,
            "encounter": serializers.serialize_encounter_summary(encounter),
        }
    ), status


# ---------------------------------------------------------------------------
# Combatants (GM)
# ---------------------------------------------------------------------------

@login_required
def add_combatant(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    player_id = data.get("player_id")
    if not isinstance(player_id, int):
        return jsonify({"error": "player_id must be an integer."}), 400
    player = Player.query.filter_by(id=player_id, campaign_id=campaign.id).first()
    if player is None:
        return jsonify({"error": "Player not found in this campaign."}), 404
    try:
        encounter = encounter_service.locked_encounter(encounter_id, campaign.id)
        combatant = encounter_service.add_player_combatant(
            encounter,
            player,
            campaign,
            x=data.get("x", 0),
            y=data.get("y", 0),
            name=data.get("name"),
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "combatant": serializers.serialize_combatant(combatant, for_gm=True),
            "turn_version": encounter.turn_version,
        }
    ), 201


@login_required
def add_own_combatant(encounter_id):
    encounter, err = _encounter_or_404(encounter_id)
    if err:
        return err
    role, player_ids, err = _viewer_context(encounter)
    if err:
        return err
    if role != "player":
        return jsonify({"error": "Player session required."}), 403
    data = _json_body()
    requested_player_id = data.get("player_id")
    if requested_player_id is not None and requested_player_id not in player_ids:
        return jsonify({"error": "You can only place your own character."}), 400
    player_id = requested_player_id if requested_player_id is not None else player_ids[0]
    player = Player.query.filter_by(id=player_id, campaign_id=encounter.campaign_id).first()
    if player is None:
        return jsonify({"error": "Player not found in this campaign."}), 404
    try:
        locked = encounter_service.locked_encounter(
            encounter.id,
            encounter.campaign_id,
            data.get("turn_version"),
        )
        existing = BattleCombatant.query.filter(
            BattleCombatant.encounter_id == locked.id,
            BattleCombatant.player_id == player.id,
            BattleCombatant.status != "removed",
        ).first()
        if existing is not None:
            return jsonify({"error": "Your character is already placed."}), 400
        combatant = encounter_service.add_player_combatant(
            locked,
            player,
            locked.campaign,
            x=data.get("x", 0),
            y=data.get("y", 0),
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "combatant": serializers.serialize_combatant(
                combatant,
                for_gm=False,
                viewer_player_id=player.id,
            ),
            "turn_version": locked.turn_version,
        }
    ), 201


@login_required
def add_monster_to_encounter(encounter_id, entry_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    entry = monster_compendium_service.entry_for_campaign(entry_id, campaign.id)
    if entry is None:
        return jsonify({"error": "Monster not found in this campaign."}), 404
    try:
        count = int(data.get("count", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "count must be an integer."}), 400
    if not (1 <= count <= 10):
        return jsonify({"error": "count must be between 1 and 10."}), 400
    try:
        encounter = encounter_service.locked_encounter(encounter_id, campaign.id)
        combatants = []
        for index in range(count):
            name = entry.name if count == 1 else f"{entry.name} {index + 1}"
            combatants.append(
                encounter_service.add_monster_combatant(
                    encounter,
                    entry,
                    x=data.get("x", 0),
                    y=data.get("y", 0),
                    name=name,
                )
            )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "combatants": [
                serializers.serialize_combatant(c, for_gm=True) for c in combatants
            ],
            "turn_version": encounter.turn_version,
        }
    ), 201


# ---------------------------------------------------------------------------
# Turn flow (GM + players)
# ---------------------------------------------------------------------------

@login_required
def roll_initiative(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        encounter = encounter_service.locked_encounter(
            encounter_id, campaign.id, data.get("turn_version")
        )
        order = encounter_service.roll_initiative(encounter, Random())
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "order": [c.id for c in order],
            "encounter": serializers.serialize_encounter(encounter, for_gm=True),
        }
    )


@login_required
def move(encounter_id):
    encounter, err = _encounter_or_404(encounter_id)
    if err:
        return err
    role, player_ids, err = _viewer_context(encounter)
    if err:
        return err
    data = _json_body()
    try:
        encounter = _locked_encounter_for_mutation(encounter, data)
        combatant = _actor_combatant(encounter, data, role, player_ids)
        result = encounter_service.move_action(
            encounter, combatant, data.get("x"), data.get("y")
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {"success": True, "move": result, "turn_version": encounter.turn_version}
    )


@login_required
def action(encounter_id):
    """Resolve an attack / batch attack / death save for the current turn."""
    encounter, err = _encounter_or_404(encounter_id)
    if err:
        return err
    role, player_ids, err = _viewer_context(encounter)
    if err:
        return err
    data = _json_body()
    action_type = data.get("type", "attack")
    rng = Random()
    try:
        encounter = _locked_encounter_for_mutation(encounter, data)
        if action_type == "attack":
            combatant = _actor_combatant(encounter, data, role, player_ids)
            result = encounter_service.attack_action(
                encounter,
                combatant,
                data.get("target_id"),
                data.get("attack_key"),
                rng,
                roll_mode=data.get("roll_mode", "normal"),
            )
        elif action_type == "multiattack":
            combatant = _actor_combatant(encounter, data, role, player_ids)
            result = encounter_service.multiattack_action(
                encounter,
                combatant,
                data.get("target_id"),
                data.get("multiattack_key"),
                rng,
                roll_mode=data.get("roll_mode", "normal"),
                primary_attack_key=data.get("primary_attack_key"),
            )
        elif action_type == "batch_attack":
            if role != "gm":
                raise CombatValidationError("Batch rolls are GM-only.")
            result = encounter_service.batch_attack_action(
                encounter,
                data.get("attacker_ids"),
                data.get("target_id"),
                data.get("attack_key"),
                rng,
                roll_mode=data.get("roll_mode", "normal"),
            )
        elif action_type == "death_save":
            combatant = _actor_combatant(encounter, data, role, player_ids)
            result = encounter_service.death_save_action(encounter, combatant, rng)
        elif action_type == "cast_spell":
            combatant = _actor_combatant(encounter, data, role, player_ids)
            result = encounter_service.cast_spell_action(
                encounter,
                combatant,
                data.get("target_id"),
                data.get("spell_key"),
                data.get("cast_level"),
                rng,
                roll_mode=data.get("roll_mode", "normal"),
                concentration_check_override=data.get("concentration_check_override"),
            )
        elif action_type == "end_concentration":
            combatant = _actor_combatant(encounter, data, role, player_ids)
            result = encounter_service.end_concentration_action(
                encounter,
                combatant,
                role=role,
            )
        elif action_type == "disengage":
            combatant = _actor_combatant(encounter, data, role, player_ids)
            result = encounter_service.disengage_action(encounter, combatant)
        elif action_type == "legendary_action":
            if role != "gm":
                raise CombatValidationError("Legendary actions are GM-only.")
            actor = encounter_service.combatant_in_encounter(
                encounter, data.get("actor_id")
            )
            if actor is None:
                raise CombatValidationError("Combatant not found in this encounter.")
            result = encounter_service.legendary_action(
                encounter,
                actor,
                data.get("action_key"),
                data.get("target_id"),
                rng,
                roll_mode=data.get("roll_mode", "normal"),
            )
        else:
            raise CombatValidationError("Unknown action type.")
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {"success": True, "result": result, "turn_version": encounter.turn_version}
    )


@login_required
def wait(encounter_id):
    encounter, err = _encounter_or_404(encounter_id)
    if err:
        return err
    role, player_ids, err = _viewer_context(encounter)
    if err:
        return err
    data = _json_body()
    try:
        encounter = _locked_encounter_for_mutation(encounter, data)
        combatant = _actor_combatant(encounter, data, role, player_ids)
        next_up = encounter_service.wait_action(encounter, combatant)
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "next_combatant_id": next_up.id if next_up else None,
            "turn_version": encounter.turn_version,
        }
    )


@login_required
def end_turn(encounter_id):
    encounter, err = _encounter_or_404(encounter_id)
    if err:
        return err
    role, player_ids, err = _viewer_context(encounter)
    if err:
        return err
    data = _json_body()
    try:
        encounter = _locked_encounter_for_mutation(encounter, data)
        if role != "gm":
            current = encounter_service.current_combatant(encounter)
            if current is None or current.player_id not in player_ids:
                raise CombatValidationError("You can only end your own turn.")
        next_up = encounter_service.end_turn(encounter)
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "next_combatant_id": next_up.id if next_up else None,
            "round_number": encounter.round_number,
            "turn_version": encounter.turn_version,
        }
    )


# ---------------------------------------------------------------------------
# Settings (GM)
# ---------------------------------------------------------------------------

@login_required
def get_settings():
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    return jsonify({"settings": settings_service.get_settings(campaign.id)})


@login_required
def save_settings():
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        clean = settings_service.save_settings(campaign.id, data.get("settings"))
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify({"success": True, "settings": clean})


# ---------------------------------------------------------------------------
# Monster compendium (GM)
# ---------------------------------------------------------------------------

@login_required
def list_monsters():
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    try:
        seed_srd_monsters_if_dnd5e(campaign.id, campaign.system_type)
        db.session.commit()
    except MonsterCatalogError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return _error_response(exc)
    return jsonify(
        {
            "monsters": [
                monster_compendium_service.serialize_entry(entry)
                for entry in monster_compendium_service.list_entries(campaign.id)
            ]
        }
    )


@login_required
def create_monster():
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        entry = monster_compendium_service.create_entry(
            campaign.id,
            data.get("name"),
            data.get("stats") or {},
            challenge_rating=data.get("challenge_rating"),
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {"success": True, "monster": monster_compendium_service.serialize_entry(entry)}
    ), 201


@login_required
def update_monster(entry_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    entry = monster_compendium_service.entry_for_campaign(entry_id, campaign.id)
    if entry is None:
        return jsonify({"error": "Monster not found in this campaign."}), 404
    data = _json_body()
    try:
        if "known_to_players" in data:
            known_to_players = bool(data.get("known_to_players"))
        else:
            known_to_players = None
        entry = monster_compendium_service.update_entry(
            entry,
            name=data.get("name"),
            stat_json=data.get("stats"),
            challenge_rating=data.get("challenge_rating"),
            known_to_players=known_to_players,
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {"success": True, "monster": monster_compendium_service.serialize_entry(entry)}
    )


@login_required
def delete_monster(entry_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    entry = monster_compendium_service.entry_for_campaign(entry_id, campaign.id)
    if entry is None:
        return jsonify({"error": "Monster not found in this campaign."}), 404
    try:
        monster_compendium_service.delete_entry(entry)
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify({"success": True})


@login_required
def generate_monster():
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        entry = monster_compendium_service.generate_entry(
            campaign.id,
            raw_seed=data.get("seed"),
            challenge=data.get("challenge", 1.0),
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {"success": True, "monster": monster_compendium_service.serialize_entry(entry)}
    ), 201


@login_required
def seed_srd_monsters():
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    try:
        counts = ensure_srd_monsters_for_campaign(campaign.id)
        db.session.commit()
    except MonsterCatalogError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "counts": counts,
            "message": (
                f"Imported SRD monsters: {counts['inserted']} new, "
                f"{counts['updated']} updated, {counts['skipped']} skipped "
                "(GM edits preserved)."
            ),
        }
    )


# --- Battle maps -------------------------------------------------------------


@login_required
def resize_encounter_grid(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    try:
        encounter = encounter_service.locked_encounter(encounter_id, campaign.id)
        battle_map_service.resize_grid(
            encounter, data.get("grid_width"), data.get("grid_height")
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    return jsonify(
        {
            "success": True,
            "encounter": serializers.serialize_encounter(encounter, for_gm=True),
        }
    )


@login_required
def upload_encounter_map(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    file_storage = request.files.get("map_image")
    if file_storage is None or not file_storage.filename:
        return jsonify({"error": "map_image file is required."}), 400
    previous_key = new_key = None
    try:
        encounter = encounter_service.locked_encounter(encounter_id, campaign.id)
        previous_key, new_key = battle_map_service.save_upload(encounter, file_storage)
        db.session.commit()
    except Exception as exc:
        if new_key:
            battle_map_service.delete_asset_key(new_key)
        return _error_response(exc)
    if previous_key and previous_key != new_key:
        battle_map_service.delete_asset_key(previous_key)
    return jsonify(
        {
            "success": True,
            "encounter": serializers.serialize_encounter(encounter, for_gm=True),
        }
    )


@login_required
def generate_encounter_map(encounter_id):
    campaign, err = _gm_dnd5e_campaign_for_json()
    if err:
        return err
    data = _json_body()
    previous_key = None
    try:
        encounter = encounter_service.locked_encounter(encounter_id, campaign.id)
        previous_key = battle_map_service.regenerate_map(
            encounter, preset=data.get("terrain_preset")
        )
        db.session.commit()
    except Exception as exc:
        return _error_response(exc)
    if previous_key:
        battle_map_service.delete_asset_key(previous_key)
    return jsonify(
        {
            "success": True,
            "encounter": serializers.serialize_encounter(encounter, for_gm=True),
        }
    )


@login_required
def get_encounter_map(encounter_id):
    encounter, err = _encounter_or_404(encounter_id)
    if err:
        return err
    _role, _player_ids, err = _viewer_context(encounter)
    if err:
        return err
    return jsonify({"map": battle_map_service.map_payload(encounter)})


@login_required
def get_encounter_map_chunk(encounter_id):
    encounter, err = _encounter_or_404(encounter_id)
    if err:
        return err
    _role, _player_ids, err = _viewer_context(encounter)
    if err:
        return err
    if not battle_map_service.is_chunked_map(encounter):
        return jsonify({"error": "Encounter map is not chunked."}), 400
    chunk_x = request.args.get("chunk_x", type=int)
    chunk_y = request.args.get("chunk_y", type=int)
    if chunk_x is None or chunk_y is None:
        return jsonify({"error": "chunk_x and chunk_y are required."}), 400
    try:
        chunk = battle_map_service.terrain_chunk_payload(encounter, chunk_x, chunk_y)
    except Exception as exc:
        return _error_response(exc)
    return jsonify({"map_chunk": chunk})


@login_required
def get_encounter_map_image(encounter_id):
    import io

    encounter, err = _encounter_or_404(encounter_id)
    if err:
        return err
    _role, _player_ids, err = _viewer_context(encounter)
    if err:
        return err
    if not encounter.map_asset_key:
        return jsonify({"error": "Encounter map image not found."}), 404
    data = battle_map_service.read_upload_bytes(encounter)
    if not data:
        return jsonify({"error": "Encounter map image not found."}), 404
    resp = send_file(io.BytesIO(data), mimetype="image/webp", max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp
