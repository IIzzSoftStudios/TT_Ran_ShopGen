"""GM handlers for campaign spell compendium editing."""

from __future__ import annotations

from flask import jsonify, redirect, request, url_for
from flask_login import current_user

from app.extensions import db
from app.routes.handlers.gm_helpers import require_active_campaign
from app.services import spells_compendium_service
from app.services.spells_compendium_service import SpellsValidationError


def _active_campaign():
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        return None, redirect(url_for("main.campaigns"))
    return require_active_campaign(profile)


def _dnd5e_campaign_or_error(campaign):
    if campaign is None:
        return jsonify({"error": "Select a campaign first."}), 400
    if (getattr(campaign, "system_type", None) or "").lower() != "dnd5e":
        return jsonify({"error": "Spell compendium is available for D&D 5e campaigns only."}), 400
    return None


def get_spells_compendium():
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return jsonify({"error": "Select a campaign first."}), 400
    gate = _dnd5e_campaign_or_error(campaign)
    if gate is not None:
        return gate

    return jsonify({"spells": spells_compendium_service.list_spells(campaign.id)})


def create_spells_compendium():
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return jsonify({"error": "Select a campaign first."}), 400
    gate = _dnd5e_campaign_or_error(campaign)
    if gate is not None:
        return gate

    payload = request.get_json(silent=True) or {}
    try:
        entry = spells_compendium_service.create_spell(campaign.id, payload)
        db.session.commit()
    except SpellsValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({"spell": entry}), 201


def update_spells_compendium(key: str):
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return jsonify({"error": "Select a campaign first."}), 400
    gate = _dnd5e_campaign_or_error(campaign)
    if gate is not None:
        return gate

    payload = request.get_json(silent=True) or {}
    try:
        entry = spells_compendium_service.update_spell(campaign.id, key, payload)
        db.session.commit()
    except SpellsValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({"spell": entry})
