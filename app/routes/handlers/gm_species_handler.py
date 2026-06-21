"""GM handlers for campaign species builder and compendium editing."""

from __future__ import annotations

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.routes.handlers.gm_helpers import require_active_campaign
from app.services import species_compendium_service
from app.services.species_compendium_service import SpeciesValidationError


def _active_campaign():
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        return None, redirect(url_for("main.campaigns"))
    return require_active_campaign(profile)


def species_builder():
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return redirect_response

    species = species_compendium_service.custom_species_needing_builder(campaign.id)
    if not species:
        return redirect(url_for("gm.home"))

    return render_template(
        "GM_species_builder.html",
        campaign=campaign,
        species_entries=species,
    )


def save_species_builder():
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return redirect_response

    if request.form.get("builder_action") == "skip":
        flash("Species setup skipped. You can edit species later from Species Compendium.", "success")
        return redirect(url_for("gm.home"))

    keys = request.form.getlist("species_key")
    try:
        for key in keys:
            prefix = f"species_{key}_"
            raw = {
                "name": request.form.get(prefix + "name"),
                "population_percent": request.form.get(prefix + "population_percent"),
                "ability_modifiers": {
                    ability: request.form.get(prefix + ability)
                    for ability in ("str", "dex", "con", "int", "wis", "cha")
                },
                "stat_modifiers": request.form.get(prefix + "stat_modifiers"),
                "traits": request.form.get(prefix + "traits"),
                "notes": request.form.get(prefix + "notes"),
            }
            species_compendium_service.update_species(campaign.id, key, raw)
        db.session.commit()
    except SpeciesValidationError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return species_builder(), 400

    flash("Custom species saved. You can keep editing them in Species Compendium.", "success")
    return redirect(url_for("gm.home"))


def get_species_compendium():
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return jsonify({"error": "Select a campaign first."}), 400

    return jsonify({"species": species_compendium_service.list_species(campaign.id)})


def create_species_compendium():
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return jsonify({"error": "Select a campaign first."}), 400

    payload = request.get_json(silent=True) or {}
    try:
        entry = species_compendium_service.create_species(campaign.id, payload)
        db.session.commit()
    except SpeciesValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({"species": entry}), 201


def update_species_compendium(key: str):
    campaign, redirect_response = _active_campaign()
    if redirect_response is not None:
        return jsonify({"error": "Select a campaign first."}), 400

    payload = request.get_json(silent=True) or {}
    try:
        entry = species_compendium_service.update_species(campaign.id, key, payload)
        db.session.commit()
    except SpeciesValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify({"species": entry})
