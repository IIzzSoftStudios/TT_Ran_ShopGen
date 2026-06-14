"""GM handlers for campaign classes compendium editing."""

from __future__ import annotations

from flask import jsonify, redirect, request, url_for
from flask_login import current_user

from app.extensions import db
from app.routes.handlers.gm_helpers import require_active_campaign
from app.services import classes_compendium_service
from app.services.classes_compendium_service import ClassesValidationError


def _active_campaign():
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        return None, redirect(url_for("main.campaigns"))
    return require_active_campaign(profile)


def _dnd5e_campaign_or_error(campaign):
    if campaign is None:
        return jsonify({"error": "Select a campaign first."}), 400
    if (getattr(campaign, "system_type", None) or "").lower() != "dnd5e":
        return jsonify({"error": "Classes compendium is available for D&D 5e campaigns only."}), 400
    return None


def get_classes_compendium():
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return jsonify({"error": "Select a campaign first."}), 400
    gate = _dnd5e_campaign_or_error(campaign)
    if gate is not None:
        return gate

    return jsonify({"classes": classes_compendium_service.list_classes(campaign.id)})


def create_classes_compendium():
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return jsonify({"error": "Select a campaign first."}), 400
    gate = _dnd5e_campaign_or_error(campaign)
    if gate is not None:
        return gate

    payload = request.get_json(silent=True) or {}
    try:
        entry = classes_compendium_service.create_class(campaign.id, payload)
        db.session.commit()
    except ClassesValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({"class": entry}), 201


def update_classes_compendium(key: str):
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return jsonify({"error": "Select a campaign first."}), 400
    gate = _dnd5e_campaign_or_error(campaign)
    if gate is not None:
        return gate

    payload = request.get_json(silent=True) or {}
    try:
        entry = classes_compendium_service.update_class(campaign.id, key, payload)
        db.session.commit()
    except ClassesValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({"class": entry})
