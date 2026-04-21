"""GM-side player / character (Player model) management."""

from types import SimpleNamespace

from flask import flash, redirect, render_template, request, url_for

from app.extensions import db
from app.models import Item, Player, PlayerEquipment, PlayerInventory, CampaignPlayer
from app.routes.handlers.gm_helpers import get_campaign_for_gm_session
from app.services import character_sheet_service

EQUIPMENT_SLOTS = ("weapon", "armor", "accessory")


def _player_for_gm(character_id: int, gm_profile_id: int):
    return (
        Player.query.filter_by(id=character_id, gm_profile_id=gm_profile_id).first()
    )


def list_players():
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir

    memberships = (
        CampaignPlayer.query.filter_by(campaign_id=campaign.id, is_active=True)
        .order_by(CampaignPlayer.created_at.asc())
        .all()
    )

    player_entries = []
    for membership in memberships:
        player = membership.player
        if not player or player.gm_profile_id != gm_profile.id:
            continue
        characters = [
            SimpleNamespace(
                id=player.id,
                name=player.user.username if player.user else "Player",
                class_name=None,
                level=None,
            )
        ]
        player_entries.append({"player": player, "characters": characters})

    return render_template(
        "GM_view_players.html",
        campaign=campaign,
        player_entries=player_entries,
    )


def view_character(character_id: int):
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_gm(character_id, gm_profile.id)
    if not player:
        flash("Player not found in this campaign.", "danger")
        return redirect(url_for("gm.gm_view_players"))
    items = Item.query.filter_by(gm_profile_id=gm_profile.id).order_by(Item.name).all()
    equipment = {e.slot: e for e in player.equipment_slots}
    for slot in EQUIPMENT_SLOTS:
        equipment.setdefault(slot, None)

    equipment_slot_views = [
        SimpleNamespace(slot_name=slot, item=(equipment[slot].item if equipment[slot] else None))
        for slot in EQUIPMENT_SLOTS
    ]
    character = character_sheet_service.build_character_view(
        player,
        campaign,
        equipment_slots=equipment_slot_views,
    )

    return render_template(
        "GM_view_character.html",
        player=player,
        gm_profile=gm_profile,
        inventory_rows=player.inventory,
        equipment=equipment,
        equipment_slots=EQUIPMENT_SLOTS,
        campaign_items=items,
        character=character,
    )


def update_character(character_id: int):
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_gm(character_id, gm_profile.id)
    if not player:
        flash("Player not found.", "danger")
        return redirect(url_for("gm.gm_view_players"))

    # This route serves both the narrow "currency only" legacy form and the
    # full character sheet form. We dispatch on which fields are present to
    # keep the existing currency-save button working without changes.
    form_section = (request.form.get("form_section") or "").strip()

    try:
        if form_section == "sheet":
            ok, errors = character_sheet_service.apply_sheet_update(
                player, campaign, request.form
            )
            if ok:
                flash("Character sheet saved.", "success")
            else:
                for msg in errors or ["Failed to save character sheet."]:
                    flash(msg, "danger")
        else:
            currency = request.form.get("currency", type=int)
            if currency is not None:
                if currency < 0:
                    flash("Currency cannot be negative.", "danger")
                else:
                    player.currency = currency
                    db.session.commit()
                    flash("Character updated.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")
    return redirect(url_for("gm.gm_view_character", character_id=character_id))


def update_inventory(character_id: int):
    gm_profile, _, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_gm(character_id, gm_profile.id)
    if not player:
        flash("Player not found.", "danger")
        return redirect(url_for("gm.gm_view_players"))

    action = request.form.get("action", "set")
    item_id = request.form.get("item_id", type=int)
    quantity = request.form.get("quantity", type=int)

    if item_id is None:
        flash("Item is required.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))

    item = Item.query.filter_by(item_id=item_id, gm_profile_id=gm_profile.id).first()
    if not item:
        flash("Invalid item for this campaign.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))

    try:
        row = PlayerInventory.query.filter_by(player_id=player.id, item_id=item_id).first()
        if action == "remove":
            if row:
                db.session.delete(row)
            db.session.commit()
            flash("Inventory row removed.", "success")
            return redirect(url_for("gm.gm_view_character", character_id=character_id))

        if quantity is None or quantity < 0:
            flash("Valid quantity required.", "danger")
            return redirect(url_for("gm.gm_view_character", character_id=character_id))

        if action == "add":
            if row:
                row.quantity = int(row.quantity) + quantity
            else:
                db.session.add(
                    PlayerInventory(player_id=player.id, item_id=item_id, quantity=quantity)
                )
        else:
            if not row:
                db.session.add(
                    PlayerInventory(player_id=player.id, item_id=item_id, quantity=quantity)
                )
            else:
                row.quantity = quantity
                if row.quantity <= 0:
                    db.session.delete(row)
        db.session.commit()
        flash("Inventory updated.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")
    return redirect(url_for("gm.gm_view_character", character_id=character_id))


def equip_item(character_id: int):
    gm_profile, _, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_gm(character_id, gm_profile.id)
    if not player:
        flash("Player not found.", "danger")
        return redirect(url_for("gm.gm_view_players"))

    slot = (request.form.get("slot") or "").strip().lower()
    item_id = request.form.get("item_id", type=int)
    if slot not in EQUIPMENT_SLOTS:
        flash("Invalid equipment slot.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))
    if item_id is None:
        flash("Item is required.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))

    item = Item.query.filter_by(item_id=item_id, gm_profile_id=gm_profile.id).first()
    if not item:
        flash("Invalid item.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))

    try:
        # Every GM equip also grants one of the item to the player's inventory:
        # new row -> quantity 1 tagged "GM"; existing row -> quantity += 1 and
        # we do NOT overwrite an existing source (so player-earned rows keep
        # their provenance; GM-granted rows stay "GM").
        inv_row = PlayerInventory.query.filter_by(
            player_id=player.id, item_id=item_id
        ).first()
        if inv_row is None:
            db.session.add(
                PlayerInventory(
                    player_id=player.id,
                    item_id=item_id,
                    quantity=1,
                    source="GM",
                )
            )
        else:
            inv_row.quantity = int(inv_row.quantity or 0) + 1

        eq = PlayerEquipment.query.filter_by(player_id=player.id, slot=slot).first()
        if eq:
            eq.item_id = item_id
            eq.source = "GM"
        else:
            db.session.add(
                PlayerEquipment(
                    player_id=player.id,
                    slot=slot,
                    item_id=item_id,
                    source="GM",
                )
            )
        db.session.commit()
        flash(f"Equipped to {slot} (+1 to inventory, tagged GM).", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")
    return redirect(url_for("gm.gm_view_character", character_id=character_id))


def unequip_item(character_id: int):
    gm_profile, _, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_gm(character_id, gm_profile.id)
    if not player:
        flash("Player not found.", "danger")
        return redirect(url_for("gm.gm_view_players"))

    slot = (request.form.get("slot") or "").strip().lower()
    if slot not in EQUIPMENT_SLOTS:
        flash("Invalid slot.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))

    try:
        eq = PlayerEquipment.query.filter_by(player_id=player.id, slot=slot).first()
        if eq:
            eq.item_id = None
            db.session.commit()
        flash("Slot cleared.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")
    return redirect(url_for("gm.gm_view_character", character_id=character_id))
