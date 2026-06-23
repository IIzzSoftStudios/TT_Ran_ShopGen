"""GM handlers for the mechanical traits compendium."""

from __future__ import annotations

from flask import jsonify, request
from flask_login import current_user

from app.extensions import db
from app.routes.handlers.gm_helpers import require_active_campaign
from app.services import traits_compendium_service
from app.services.traits_compendium_service import TraitsValidationError


def _active_campaign():
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        return None, (jsonify({"error": "GM profile required."}), 403)
    return require_active_campaign(profile)


def get_traits_compendium():
    campaign, err = _active_campaign()
    if err:
        return err
    return jsonify({"traits": traits_compendium_service.list_traits(campaign.id)})


def create_traits_compendium():
    campaign, err = _active_campaign()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    try:
        entry = traits_compendium_service.create_trait(campaign.id, payload)
        db.session.commit()
    except TraitsValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    return jsonify({"success": True, "trait": entry})


def update_traits_compendium(key: str):
    campaign, err = _active_campaign()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    try:
        entry = traits_compendium_service.update_trait(campaign.id, key, payload)
        db.session.commit()
    except TraitsValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    return jsonify({"success": True, "trait": entry})
