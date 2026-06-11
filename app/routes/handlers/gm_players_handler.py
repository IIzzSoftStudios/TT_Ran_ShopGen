"""GM-side player / character (Player model) management."""

from datetime import datetime
from types import SimpleNamespace

from flask import flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Item,
    Player,
    PlayerEquipment,
    PlayerInventory,
    PlayerCharacterSheet,
)
from app.routes.handlers.gm_helpers import get_campaign_for_gm_session
from app.services import character_sheet_service

EQUIPMENT_SLOTS = ("weapon", "armor", "accessory")


def _next_default_npc_label(campaign_id: int) -> str:
    """Return NPC1, NPC2, ... for the next NPC in this campaign (no custom name)."""
    n = (
        db.session.query(Player)
        .filter(
            Player.campaign_id == campaign_id,
            Player.is_npc.is_(True),
        )
        .count()
    )
    return f"NPC{n + 1}"


def _player_for_campaign(character_id: int, campaign_id: int):
    return Player.query.filter_by(id=character_id, campaign_id=campaign_id).first()


def build_player_entries(campaign):
    """Return player/NPC rows for GM views."""
    players = (
        Player.query.filter_by(campaign_id=campaign.id)
        .order_by(Player.id.asc())
        .all()
    )

    player_entries = []
    for player in players:
        characters = [
            SimpleNamespace(
                id=player.id,
                name=player.user.username if player.user else "NPC",
                class_name=None,
                level=None,
            )
        ]
        player_entries.append({"player": player, "characters": characters})
    return player_entries


def list_players():
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir

    player_entries = build_player_entries(campaign)

    return render_template(
        "GM_view_players.html",
        campaign=campaign,
        player_entries=player_entries,
    )


def create_npc():
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir

    if request.method == "GET":
        return render_template(
            "GM_Create_NPC.html",
            campaign=campaign,
            system_type=campaign.system_type or "generic",
        )

    name = (request.form.get("name") or "").strip() or None
    class_name = (request.form.get("class_name") or "").strip() or None
    species = (request.form.get("species") or "").strip() or None
    try:
        resolved_sheet_name = name or _next_default_npc_label(campaign.id)

        player = Player(
            is_npc=True,
            user_id=None,
            campaign_id=campaign.id,
            currency=0,
        )
        db.session.add(player)
        db.session.flush()

        sheet_dict = character_sheet_service.get_or_default_sheet(player, campaign)
        sheet_dict["name"] = resolved_sheet_name
        if class_name:
            sheet_dict["class_name"] = class_name
        if species:
            sheet_dict["species"] = species

        db.session.add(
            PlayerCharacterSheet(
                player_id=player.id,
                campaign_id=campaign.id,
                sheet_json=sheet_dict,
            )
        )
        db.session.commit()
        flash("NPC added to this campaign.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")
    return redirect(url_for("gm.gm_view_players"))


def view_character(character_id: int):
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_campaign(character_id, campaign.id)
    if not player:
        flash("Player not found in this campaign.", "danger")
        return redirect(url_for("gm.gm_view_players"))
    items = Item.query.filter_by(campaign_id=campaign.id).order_by(Item.name).all()
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
    player = _player_for_campaign(character_id, campaign.id)
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
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_campaign(character_id, campaign.id)
    if not player:
        flash("Player not found.", "danger")
        return redirect(url_for("gm.gm_view_players"))

    action = request.form.get("action", "set")
    item_id = request.form.get("item_id", type=int)
    quantity = request.form.get("quantity", type=int)

    if item_id is None:
        flash("Item is required.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))

    item = Item.query.filter_by(item_id=item_id, campaign_id=campaign.id).first()
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
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_campaign(character_id, campaign.id)
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

    item = Item.query.filter_by(item_id=item_id, campaign_id=campaign.id).first()
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
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_campaign(character_id, campaign.id)
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


def remove_player_from_campaign(player_id: int):
    """Drop a PC from the active campaign (clears Player.campaign_id, keeps Player row)."""
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = Player.query.filter_by(id=player_id, campaign_id=campaign.id).first()
    if not player or player.is_npc:
        flash("Player not found.", "danger")
        return redirect(url_for("gm.gm_view_players"))
    try:
        camp_sheet = PlayerCharacterSheet.query.filter_by(
            player_id=player.id, campaign_id=campaign.id
        ).first()
        vault = PlayerCharacterSheet.query.filter(
            PlayerCharacterSheet.player_id == player.id,
            PlayerCharacterSheet.campaign_id.is_(None),
        ).first()
        vj = vault.sheet_json if vault and isinstance(vault.sheet_json, dict) else {}
        vault_empty = vault is None or not vj or (
            not vj.get("name")
            and not vj.get("class_name")
            and not (vj.get("abilities") or {})
        )
        if (
            camp_sheet
            and isinstance(camp_sheet.sheet_json, dict)
            and vault_empty
        ):
            payload = dict(camp_sheet.sheet_json)
            if vault is None:
                db.session.add(
                    PlayerCharacterSheet(
                        player_id=player.id,
                        campaign_id=None,
                        sheet_json=payload,
                    )
                )
            else:
                vault.sheet_json = payload
                vault.updated_at = datetime.utcnow()

        player.campaign_id = None
        db.session.commit()
        flash("Removed player from this campaign.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Could not remove player from this campaign.", "danger")
    return redirect(url_for("gm.gm_view_players"))


def delete_npc_player(player_id: int):
    """Permanently delete an NPC and all dependent rows."""
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = Player.query.filter_by(id=player_id, campaign_id=campaign.id).first()
    if not player or not player.is_npc:
        flash("NPC not found.", "danger")
        return redirect(url_for("gm.gm_view_players"))
    try:
        PlayerCharacterSheet.query.filter_by(player_id=player.id).delete(
            synchronize_session=False
        )
        PlayerInventory.query.filter_by(player_id=player.id).delete(
            synchronize_session=False
        )
        PlayerEquipment.query.filter_by(player_id=player.id).delete(
            synchronize_session=False
        )
        db.session.delete(player)
        db.session.commit()
        flash("NPC deleted.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Could not delete NPC (data conflict).", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")
    return redirect(url_for("gm.gm_view_players"))
