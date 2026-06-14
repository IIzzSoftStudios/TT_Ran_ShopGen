"""Blueprint for the D&D 5e tactical combat API.

Thin routing layer only -- auth, the D&D 5e gate, locking, and commit /
rollback discipline all live in app/routes/handlers/combat_handler.py.
Registered in app/__init__.py under the /api/combat prefix.
"""

from flask import Blueprint
from flask_login import login_required

from app.routes.handlers import combat_handler

combat_bp = Blueprint("combat", __name__)


# --- Encounters -------------------------------------------------------------
@combat_bp.route("/encounters", methods=["GET"])
@login_required
def combat_encounters_list():
    return combat_handler.list_encounters()


@combat_bp.route("/encounters", methods=["POST"])
@login_required
def combat_encounters_create():
    return combat_handler.create_encounter()


@combat_bp.route("/encounters/<int:encounter_id>", methods=["GET"])
@login_required
def combat_encounter_get(encounter_id):
    return combat_handler.get_encounter(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>", methods=["DELETE"])
@login_required
def combat_encounter_delete(encounter_id):
    return combat_handler.delete_encounter(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/end", methods=["POST"])
@login_required
def combat_encounter_end(encounter_id):
    return combat_handler.end_encounter(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/rename", methods=["POST"])
@login_required
def combat_encounter_rename(encounter_id):
    return combat_handler.rename_encounter(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/visibility", methods=["POST"])
@login_required
def combat_encounter_visibility(encounter_id):
    return combat_handler.set_encounter_visibility(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/place", methods=["POST"])
@login_required
def combat_encounter_place(encounter_id):
    return combat_handler.place_encounter(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/grid", methods=["POST"])
@login_required
def combat_encounter_grid(encounter_id):
    return combat_handler.resize_encounter_grid(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/map", methods=["GET"])
@login_required
def combat_encounter_map_get(encounter_id):
    return combat_handler.get_encounter_map(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/map/chunk", methods=["GET"])
@login_required
def combat_encounter_map_chunk(encounter_id):
    return combat_handler.get_encounter_map_chunk(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/map/upload", methods=["POST"])
@login_required
def combat_encounter_map_upload(encounter_id):
    return combat_handler.upload_encounter_map(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/map/generate", methods=["POST"])
@login_required
def combat_encounter_map_generate(encounter_id):
    return combat_handler.generate_encounter_map(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/map/image", methods=["GET"])
@login_required
def combat_encounter_map_image(encounter_id):
    return combat_handler.get_encounter_map_image(encounter_id)


@combat_bp.route("/encounters/for-canvas/<int:canvas_id>", methods=["GET"])
@login_required
def combat_encounter_for_canvas(canvas_id):
    return combat_handler.lookup_encounter_for_canvas(canvas_id)


@combat_bp.route("/encounters/for-canvas/<int:canvas_id>", methods=["POST"])
@login_required
def combat_encounter_for_canvas_create(canvas_id):
    return combat_handler.get_or_create_encounter_for_canvas(canvas_id)


# --- Combatants -------------------------------------------------------------
@combat_bp.route("/encounters/<int:encounter_id>/combatants", methods=["POST"])
@login_required
def combat_combatant_add(encounter_id):
    return combat_handler.add_combatant(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/own-combatant", methods=["POST"])
@login_required
def combat_own_combatant_add(encounter_id):
    return combat_handler.add_own_combatant(encounter_id)


@combat_bp.route(
    "/encounters/<int:encounter_id>/monsters/<int:entry_id>/add", methods=["POST"]
)
@login_required
def combat_monster_add(encounter_id, entry_id):
    return combat_handler.add_monster_to_encounter(encounter_id, entry_id)


# --- Turn flow --------------------------------------------------------------
@combat_bp.route("/encounters/<int:encounter_id>/initiative", methods=["POST"])
@login_required
def combat_initiative(encounter_id):
    return combat_handler.roll_initiative(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/move", methods=["POST"])
@login_required
def combat_move(encounter_id):
    return combat_handler.move(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/action", methods=["POST"])
@login_required
def combat_action(encounter_id):
    return combat_handler.action(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/wait", methods=["POST"])
@login_required
def combat_wait(encounter_id):
    return combat_handler.wait(encounter_id)


@combat_bp.route("/encounters/<int:encounter_id>/end-turn", methods=["POST"])
@login_required
def combat_end_turn(encounter_id):
    return combat_handler.end_turn(encounter_id)


# --- Settings ---------------------------------------------------------------
@combat_bp.route("/settings", methods=["GET"])
@login_required
def combat_settings_get():
    return combat_handler.get_settings()


@combat_bp.route("/settings", methods=["POST"])
@login_required
def combat_settings_save():
    return combat_handler.save_settings()


# --- Monster compendium -----------------------------------------------------
@combat_bp.route("/monsters", methods=["GET"])
@login_required
def combat_monsters_list():
    return combat_handler.list_monsters()


@combat_bp.route("/monsters", methods=["POST"])
@login_required
def combat_monsters_create():
    return combat_handler.create_monster()


@combat_bp.route("/monsters/<int:entry_id>", methods=["POST"])
@login_required
def combat_monsters_update(entry_id):
    return combat_handler.update_monster(entry_id)


@combat_bp.route("/monsters/<int:entry_id>/delete", methods=["POST"])
@login_required
def combat_monsters_delete(entry_id):
    return combat_handler.delete_monster(entry_id)


@combat_bp.route("/monsters/generate", methods=["POST"])
@login_required
def combat_monsters_generate():
    return combat_handler.generate_monster()
