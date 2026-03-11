"""
GM Players / Characters Handler
GM-facing management of players, characters, stats, equipment, and inventory.
"""

from flask import render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user

from app.extensions import db
from app.models.users import (
    Player,
    PlayerCharacter,
    PlayerInventory,
)
from app.models.backend import Item
from app.models.campaigns import Campaign, CampaignPlayer
from app.routes.handlers.gm_helpers import get_current_gm_profile
from app.routes.handlers.player_character_handler import (
    _serialize_character,
    _find_slot_for_item_type,
)


def _get_campaign_for_session():
    """Resolve the current campaign from the session, or return (None, redirect)."""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return None, None, redirect_response

    campaign_id = session.get("campaign_id")
    if not campaign_id:
        flash("Please select a campaign first.", "info")
        return None, None, redirect(url_for("main.campaigns"))

    campaign = Campaign.query.filter_by(id=campaign_id).first()
    if not campaign:
        session.pop("campaign_id", None)
        flash("Campaign not found.", "error")
        return None, None, redirect(url_for("main.campaigns"))

    if campaign.gm_profile_id != gm_profile.id:
        flash("You do not have access to this campaign.", "error")
        session.pop("campaign_id", None)
        return None, None, redirect(url_for("main.campaigns"))

    return gm_profile, campaign, None


def list_players():
    """
    List players and their characters for the current GM and active campaign.
    """
    gm_profile, campaign, redirect_response = _get_campaign_for_session()
    if redirect_response:
        return redirect_response

    # All active player memberships for this campaign
    memberships = (
        CampaignPlayer.query.filter_by(campaign_id=campaign.id, is_active=True)
        .order_by(CampaignPlayer.created_at.asc())
        .all()
    )

    player_entries = []
    for membership in memberships:
        player = membership.player
        if not player:
            continue
        # Safety check: ensure this player belongs to this GM
        if player.gm_profile_id != gm_profile.id:
            continue

        characters = (
            PlayerCharacter.query.filter_by(
                player_id=player.id, campaign_id=campaign.id
            )
            .order_by(PlayerCharacter.id.asc())
            .all()
        )
        player_entries.append(
            {
                "player": player,
                "characters": characters,
            }
        )

    return render_template(
        "GM_view_players.html",
        campaign=campaign,
        player_entries=player_entries,
    )


def _load_character_for_gm(character_id: int):
    """
    Load a PlayerCharacter by id and ensure it belongs to the current GM
    and the active campaign.
    Returns (gm_profile, campaign, character, redirect_response).
    """
    gm_profile, campaign, redirect_response = _get_campaign_for_session()
    if redirect_response:
        return None, None, None, redirect_response

    character = PlayerCharacter.query.get_or_404(character_id)

    if not character.campaign_id or character.campaign_id != campaign.id:
        flash("Character does not belong to the current campaign.", "error")
        return None, None, None, redirect(url_for("gm.gm_view_players"))

    if not character.campaign or character.campaign.gm_profile_id != gm_profile.id:
        flash("You do not have permission to access this character.", "error")
        return None, None, None, redirect(url_for("gm.gm_view_players"))

    return gm_profile, campaign, character, None


def view_character(character_id: int):
    """
    GM view of a specific character sheet with full editing controls.
    """
    gm_profile, campaign, character, redirect_response = _load_character_for_gm(
        character_id
    )
    if redirect_response:
        return redirect_response

    character_data = _serialize_character(character)
    player = character.player

    # Player inventory with item details
    inventory_entries = (
        PlayerInventory.query.filter_by(player_id=player.id)
        .join(Item, PlayerInventory.item_id == Item.item_id)
        .order_by(Item.name.asc())
        .all()
    )

    # All items for this GM (for granting new items)
    gm_items = (
        Item.query.filter_by(gm_profile_id=gm_profile.id)
        .order_by(Item.name.asc())
        .all()
    )

    return render_template(
        "GM_edit_character.html",
        campaign=campaign,
        character=character_data,
        raw_character=character,
        player=player,
        inventory_entries=inventory_entries,
        gm_items=gm_items,
    )


def update_character(character_id: int):
    """
    GM-side character update. Mirrors player_character_handler.update_character
    but operates on an arbitrary character within the GM's campaign.
    """
    gm_profile, campaign, character, redirect_response = _load_character_for_gm(
        character_id
    )
    if redirect_response:
        return redirect_response

    # Basic fields
    name = request.form.get("name", "").strip()
    level_raw = request.form.get("level", "").strip()
    notes = request.form.get("notes", "").strip()
    class_name = request.form.get("class_name", "").strip()
    species = request.form.get("species", "").strip()

    if name:
        character.name = name

    if level_raw:
        try:
            character.level = int(level_raw)
        except ValueError:
            flash("Level must be a number.", "error")

    character.notes = notes or None
    if hasattr(character, "class_name"):
        character.class_name = class_name or None
    if hasattr(character, "species"):
        character.species = species or None

    # Stats: iterate through existing stats and update from form inputs
    for stat in character.stats:
        field_name = f"stat_{stat.id}"
        raw_value = request.form.get(field_name, "").strip()
        if raw_value == "":
            # Allow clearing a value
            stat.value = None
        else:
            try:
                stat.value = float(raw_value)
            except ValueError:
                flash(f"Invalid value for {stat.stat_key}; expected a number.", "error")

    db.session.commit()
    flash("Character updated.", "success")

    return redirect(url_for("gm.gm_view_character", character_id=character.id))


def equip_item(character_id: int):
    """
    GM-side equipment change. Equip an item from the player's inventory into a slot.
    """
    gm_profile, campaign, character, redirect_response = _load_character_for_gm(
        character_id
    )
    if redirect_response:
        return redirect_response

    player = character.player

    item_id_raw = request.form.get("item_id")
    slot_name = request.form.get("slot_name", "").strip() or None

    try:
        item_id = int(item_id_raw)
    except (TypeError, ValueError):
        flash("Invalid item selection.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    item = Item.query.get(item_id)
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    if item.gm_profile_id != gm_profile.id:
        flash("You do not have access to this item.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    # Verify the player actually owns this item
    player_inventory = PlayerInventory.query.filter_by(
        player_id=player.id,
        item_id=item.item_id,
    ).first()
    if not player_inventory or player_inventory.quantity <= 0:
        flash("Player does not currently own this item.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    # Determine target slot if not explicitly provided
    if not slot_name:
        slot_name = _find_slot_for_item_type(item.type)
    if not slot_name:
        flash("This item cannot be equipped.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    # Get or create the equipment slot
    slot = (
        character.equipment_slots
        and next(
            (s for s in character.equipment_slots if s.slot_name == slot_name),
            None,
        )
    )
    if not slot:
        from app.models.users import CharacterEquipmentSlot

        slot = CharacterEquipmentSlot(
            character_id=character.id,
            slot_name=slot_name,
            item_id=None,
        )
        db.session.add(slot)
        db.session.flush()

    slot.item_id = item.item_id
    db.session.commit()

    flash(
        f"Equipped {item.name} to {slot_name.replace('_', ' ').title()} for {player.player_user.username}.",
        "success",
    )
    return redirect(url_for("gm.gm_view_character", character_id=character.id))


def unequip_item(character_id: int):
    """
    GM-side unequip of a specific slot.
    """
    gm_profile, campaign, character, redirect_response = _load_character_for_gm(
        character_id
    )
    if redirect_response:
        return redirect_response

    slot_name = request.form.get("slot_name", "").strip()
    if not slot_name:
        flash("No slot specified.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    from app.models.users import CharacterEquipmentSlot

    slot = CharacterEquipmentSlot.query.filter_by(
        character_id=character.id,
        slot_name=slot_name,
    ).first()
    if not slot or not slot.item_id:
        flash("Nothing is equipped in that slot.", "info")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    slot.item_id = None
    db.session.commit()

    flash(
        f"Unequipped item from {slot_name.replace('_', ' ').title()} for {character.name}.",
        "success",
    )
    return redirect(url_for("gm.gm_view_character", character_id=character.id))


def update_inventory(character_id: int):
    """
    GM-side inventory adjustment for a player's character.
    Positive delta_quantity grants items; negative removes them.
    Currency adjustments are not handled here (GM can manage separately).
    """
    gm_profile, campaign, character, redirect_response = _load_character_for_gm(
        character_id
    )
    if redirect_response:
        return redirect_response

    player = character.player

    item_id_raw = request.form.get("item_id")
    delta_raw = request.form.get("delta_quantity", "").strip()

    try:
        item_id = int(item_id_raw)
    except (TypeError, ValueError):
        flash("Invalid item selection.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    try:
        delta_quantity = int(delta_raw)
    except (TypeError, ValueError):
        flash("Invalid quantity change.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    if delta_quantity == 0:
        flash("No inventory change requested.", "info")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    item = Item.query.get(item_id)
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    if item.gm_profile_id != gm_profile.id:
        flash("You do not have access to this item.", "error")
        return redirect(url_for("gm.gm_view_character", character_id=character.id))

    inventory_entry = PlayerInventory.query.filter_by(
        player_id=player.id,
        item_id=item.item_id,
    ).first()

    if delta_quantity > 0:
        if inventory_entry:
            inventory_entry.quantity += delta_quantity
        else:
            inventory_entry = PlayerInventory(
                player_id=player.id,
                item_id=item.item_id,
                quantity=delta_quantity,
            )
            db.session.add(inventory_entry)
        db.session.commit()
        flash(
            f"Granted {delta_quantity}x {item.name} to {player.player_user.username}.",
            "success",
        )
    else:
        if not inventory_entry or inventory_entry.quantity <= 0:
            flash("Player does not have this item to remove.", "error")
            return redirect(url_for("gm.gm_view_character", character_id=character.id))

        remove_amount = min(inventory_entry.quantity, abs(delta_quantity))
        inventory_entry.quantity -= remove_amount
        if inventory_entry.quantity <= 0:
            db.session.delete(inventory_entry)
        db.session.commit()
        flash(
            f"Removed {remove_amount}x {item.name} from {player.player_user.username}.",
            "success",
        )

    return redirect(url_for("gm.gm_view_character", character_id=character.id))

