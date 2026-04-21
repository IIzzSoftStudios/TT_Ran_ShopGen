# app/routes/modifier_routes.py

from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.models import DemandModifier, ModifierTarget, db

modifier_routes = Blueprint("modifier_routes", __name__)


def _gm_profile_or_403():
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        return None, (jsonify({"error": "GM profile required"}), 403)
    return profile, None


def _modifier_for_gm_or_404(modifier_id: int, gm_profile_id: int):
    return DemandModifier.query.filter_by(
        id=modifier_id, gm_profile_id=gm_profile_id
    ).first()


@modifier_routes.route("/api/modifier/add", methods=["POST"])
@login_required
def add_modifier():
    """
    Adds a new demand modifier.
    Example Payload:
    {
        "name": "Plague",
        "description": "City-wide illness reducing demand",
        "scope": "city",
        "effect_value": -0.3,
        "start_date": "2025-03-01",
        "end_date": "2025-03-10",
        "is_active": true,
        "targets": [{"entity_type": "city", "entity_id": 2}]
    }
    """
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err

    data = request.json or {}
    if "name" not in data or "scope" not in data or "effect_value" not in data:
        return jsonify({"error": "name, scope, and effect_value are required"}), 400

    new_modifier = DemandModifier(
        name=data["name"],
        description=data.get("description", ""),
        scope=data["scope"],
        effect_value=data["effect_value"],
        start_date=(
            datetime.strptime(data["start_date"], "%Y-%m-%d")
            if "start_date" in data
            else None
        ),
        end_date=(
            datetime.strptime(data["end_date"], "%Y-%m-%d") if "end_date" in data else None
        ),
        is_active=data.get("is_active", True),
        gm_profile_id=gm_profile.id,
    )

    db.session.add(new_modifier)
    db.session.flush()

    for target in data.get("targets", []):
        db.session.add(
            ModifierTarget(
                modifier_id=new_modifier.id,
                entity_type=target["entity_type"],
                entity_id=target["entity_id"],
                gm_profile_id=gm_profile.id,
            )
        )

    db.session.commit()
    return jsonify(
        {"message": "Modifier added successfully", "modifier_id": new_modifier.id}
    ), 201


@modifier_routes.route("/api/modifier/update/<int:modifier_id>", methods=["PUT"])
@login_required
def update_modifier(modifier_id):
    """
    Updates an existing demand modifier.
    """
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err

    modifier = _modifier_for_gm_or_404(modifier_id, gm_profile.id)
    if not modifier:
        return jsonify({"error": "Modifier not found"}), 404

    data = request.json or {}
    if "effect_value" in data:
        modifier.effect_value = data["effect_value"]
    if "is_active" in data:
        modifier.is_active = data["is_active"]
    if "start_date" in data:
        modifier.start_date = datetime.strptime(data["start_date"], "%Y-%m-%d")
    if "end_date" in data:
        modifier.end_date = datetime.strptime(data["end_date"], "%Y-%m-%d")

    db.session.commit()
    return jsonify({"message": "Modifier updated successfully"}), 200


@modifier_routes.route("/api/modifier/delete/<int:modifier_id>", methods=["DELETE"])
@login_required
def delete_modifier(modifier_id):
    """Deletes a demand modifier."""
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err

    modifier = _modifier_for_gm_or_404(modifier_id, gm_profile.id)
    if not modifier:
        return jsonify({"error": "Modifier not found"}), 404

    db.session.delete(modifier)
    db.session.commit()
    return jsonify({"message": "Modifier deleted successfully"}), 200


@modifier_routes.route("/api/modifier/list", methods=["GET"])
@login_required
def list_modifiers():
    """Retrieves active demand modifiers for the current GM campaign."""
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err

    modifiers = DemandModifier.query.filter(
        DemandModifier.is_active == True,
        DemandModifier.gm_profile_id == gm_profile.id,
    ).all()
    return (
        jsonify(
            [
                {
                    "id": mod.id,
                    "name": mod.name,
                    "description": mod.description,
                    "scope": mod.scope,
                    "effect_value": mod.effect_value,
                    "start_date": mod.start_date.strftime("%Y-%m-%d")
                    if mod.start_date
                    else None,
                    "end_date": mod.end_date.strftime("%Y-%m-%d") if mod.end_date else None,
                    "is_active": mod.is_active,
                }
                for mod in modifiers
            ]
        ),
        200,
    )
