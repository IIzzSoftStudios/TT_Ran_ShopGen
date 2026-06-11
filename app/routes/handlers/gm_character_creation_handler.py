"""GM campaign character creation settings (stat modes)."""

from __future__ import annotations

from flask import jsonify, request, session

from app.extensions import db
from app.routes.handlers.gm_helpers import get_current_gm_profile, require_active_campaign
from app.services.character_creation.campaign_settings import (
    CharacterCreationSettingsError,
    get_creation_settings,
    get_character_options,
    update_creation_settings,
)
from app.services.species_compendium_service import ensure_species_compendium


def get_character_creation_settings():
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    campaign, redirect_response = require_active_campaign(gm_profile)
    if redirect_response is not None:
        return redirect_response
    settings = get_creation_settings(campaign.id)
    options = get_character_options(campaign.id)
    species = ensure_species_compendium(campaign.id)
    return jsonify(
        {
            "ok": True,
            "settings": settings,
            "character_options": options,
            "species_compendium": species,
            "campaign_id": campaign.id,
            "system_type": campaign.system_type,
        }
    )


def post_character_creation_settings():
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    campaign, redirect_response = require_active_campaign(gm_profile)
    if redirect_response is not None:
        return redirect_response
    if (campaign.system_type or "").strip().lower() != "dnd5e":
        return jsonify({"ok": False, "errors": ["Character creation settings apply to D&D 5e campaigns only."]}), 400
    payload = request.get_json(silent=True) or {}
    try:
        updated = update_creation_settings(campaign.id, payload)
        db.session.commit()
        session.pop("dnd5e_creation_roll_draft", None)
        session.modified = True
        return jsonify({"ok": True, "settings": updated})
    except CharacterCreationSettingsError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "errors": [str(exc)]}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "errors": ["Could not save character creation settings."]}), 500
