# app/routes/modifier_routes.py

from flask import Blueprint, request, jsonify
from flask_login import login_required
from app.models import DemandModifier, ModifierTarget, db
from datetime import datetime

modifier_routes = Blueprint("modifier_routes", __name__)

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
    data = request.json
    new_modifier = DemandModifier(
        name=data["name"],
        description=data.get("description", ""),
        scope=data["scope"],
        effect_value=data["effect_value"],
        start_date=datetime.strptime(data["start_date"], "%Y-%m-%d") if "start_date" in data else None,
        end_date=datetime.strptime(data["end_date"], "%Y-%m-%d") if "end_date" in data else None,
        is_active=data.get("is_active", True)
    )

    db.session.add(new_modifier)
    db.session.flush()  # Get new modifier ID before committing

    # Assign modifier targets (city, shop, or item)
    for target in data.get("targets", []):
        db.session.add(ModifierTarget(modifier_id=new_modifier.id, entity_type=target["entity_type"], entity_id=target["entity_id"]))

    db.session.commit()
    return jsonify({"message": "Modifier added successfully", "modifier_id": new_modifier.id}), 201


@modifier_routes.route("/api/modifier/update/<int:modifier_id>", methods=["PUT"])
@login_required
def update_modifier(modifier_id):
    """
    Updates an existing demand modifier.
    Example Payload:
    {
        "effect_value": -0.2,
        "is_active": false
    }
    """
    modifier = DemandModifier.query.get(modifier_id)
    if not modifier:
        return jsonify({"error": "Modifier not found"}), 404

    data = request.json
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
    """
    Deletes a demand modifier.
    """
    modifier = DemandModifier.query.get(modifier_id)
    if not modifier:
        return jsonify({"error": "Modifier not found"}), 404

    db.session.delete(modifier)
    db.session.commit()
    return jsonify({"message": "Modifier deleted successfully"}), 200


@modifier_routes.route("/api/modifier/list", methods=["GET"])
@login_required
def list_modifiers():
    """
    Retrieves all active demand modifiers.
    """
    modifiers = DemandModifier.query.filter(DemandModifier.is_active == True).all()
    return jsonify([
        {
            "id": mod.id,
            "name": mod.name,
            "description": mod.description,
            "scope": mod.scope,
            "effect_value": mod.effect_value,
            "start_date": mod.start_date.strftime("%Y-%m-%d") if mod.start_date else None,
            "end_date": mod.end_date.strftime("%Y-%m-%d") if mod.end_date else None,
            "is_active": mod.is_active
        } for mod in modifiers
    ]), 200
