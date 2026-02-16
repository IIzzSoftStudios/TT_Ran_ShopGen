"""
Player Character Handler
Handles character model, stats, and equipment for the player.
"""

from flask import jsonify, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required

from app.extensions import db
from app.models.users import Player, PlayerCharacter, CharacterEquipmentSlot, CharacterStat, PlayerInventory
from app.config.system_config import seed_default_stats_for_character
from app.models.backend import Item
from app.models.campaigns import Campaign, CampaignPlayer
from app.routes.handlers.player_helpers import get_current_player
from flask import session


# --- Helpers -----------------------------------------------------------------

DEFAULT_SYSTEM_TYPE = "generic"


def _get_or_create_active_character(player: Player) -> PlayerCharacter:
    """
    For now, each Player has a single active character per campaign.
    Create a default one if none exists.
    """
    from flask import session

    campaign_id = session.get("campaign_id")

    query_kwargs = {"player_id": player.id}
    if campaign_id:
        query_kwargs["campaign_id"] = campaign_id

    character = (
        PlayerCharacter.query.filter_by(**query_kwargs)
        .order_by(PlayerCharacter.id.asc())
        .first()
    )
    if character:
        return character

    # Determine system from campaign if available, otherwise fall back to generic.
    system_type = DEFAULT_SYSTEM_TYPE
    campaign = None
    if campaign_id:
        campaign = Campaign.query.filter_by(id=campaign_id).first()
        if campaign and campaign.system_type:
            system_type = campaign.system_type

    # Create a simple default character seeded with stats based on system type.
    character = PlayerCharacter(
        player_id=player.id,
        campaign_id=campaign_id,
        name=f"{player.player_user.username}'s Character",
        system_type=system_type,
        level=1,
    )
    db.session.add(character)
    db.session.flush()  # Ensure character.id is available

    # Seed stats from the configured system schema
    seed_default_stats_for_character(character, character.system_type, db)

    # Pre-create a few common equipment slots used by the SVG body model
    default_slots = ["head", "chest", "legs", "main_hand", "off_hand"]
    for slot_name in default_slots:
        db.session.add(
            CharacterEquipmentSlot(
                character_id=character.id,
                slot_name=slot_name,
                item_id=None,
            )
        )

    db.session.commit()
    return character


def _serialize_character(character: PlayerCharacter):
    """Serialize character core data, stats, and equipment slots for JSON responses."""
    stats = [
        {
            "id": stat.id,
            "key": stat.stat_key,
            "category": stat.category,
            "value": stat.value,
        }
        for stat in character.stats
    ]

    slots = []
    for slot in character.equipment_slots:
        item_data = None
        if slot.item:
            item_data = {
                "item_id": slot.item.item_id,
                "name": slot.item.name,
                "type": slot.item.type,
                "rarity": slot.item.rarity,
            }
        slots.append(
            {
                "id": slot.id,
                "slot_name": slot.slot_name,
                "item": item_data,
            }
        )

    return {
        "id": character.id,
        "name": character.name,
        "system_type": character.system_type,
        "level": character.level,
        "notes": character.notes,
        "stats": stats,
        "equipment_slots": slots,
    }


def _find_slot_for_item_type(item_type: str) -> str | None:
    """
    Very simple mapping from item.type to a character slot.
    This can be expanded/adjusted as you refine item categories.
    """
    if not item_type:
        return None

    normalized = item_type.lower()
    if "helm" in normalized or "head" in normalized:
        return "head"
    if "armor" in normalized or "chest" in normalized:
        return "chest"
    if "boots" in normalized or "legs" in normalized:
        return "legs"
    if "shield" in normalized or "off-hand" in normalized or "off hand" in normalized:
        return "off_hand"
    if "weapon" in normalized or "sword" in normalized or "main-hand" in normalized:
        return "main_hand"

    # Fallback: treat as main_hand
    return "main_hand"


# --- Route handlers -----------------------------------------------------------


def view_character():
    """
    Render a dedicated character sheet page (optional; currently not linked from nav).
    Uses the same data that the dashboard widget will use.
    """
    player, redirect_response = get_current_player()
    if redirect_response:
        return redirect_response

    character = _get_or_create_active_character(player)
    character_data = _serialize_character(character)

    return render_template(
        "Player_Character_Sheet.html",
        player=player,
        character=character_data,
    )


@login_required
def update_character():
    """
    Handle POST from the editable character sheet.
    Allows editing of name, level, notes, and all stats.
    """
    player, redirect_response = get_current_player()
    if redirect_response:
        return redirect_response

    character = _get_or_create_active_character(player)

    # Basic fields
    name = request.form.get("name", "").strip()
    level_raw = request.form.get("level", "").strip()
    notes = request.form.get("notes", "").strip()

    if name:
        character.name = name

    if level_raw:
        try:
            character.level = int(level_raw)
        except ValueError:
            flash("Level must be a number.", "error")

    character.notes = notes or None

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
                # Leave previous value intact but notify the user
                flash(f"Invalid value for {stat.stat_key}; expected a number.", "error")

    db.session.commit()
    flash("Character updated.", "success")

    return redirect(url_for("player.view_character"))


def get_character_data():
    """
    Return JSON with the current player's active character data,
    used by the Player_Home dashboard to render the body model + stats.
    """
    player, redirect_response = get_current_player()
    if redirect_response:
        # For JSON, return an error object instead of redirecting
        return jsonify({"error": "Player not available"}), 400

    character = _get_or_create_active_character(player)
    character_data = _serialize_character(character)
    return jsonify(character_data)


@login_required
def equip_item(item_id: int):
    """
    Equip an item from the player's inventory into the appropriate slot.
    Very simple rules: determine slot from item.type, then place in that slot.
    """
    player, redirect_response = get_current_player()
    if redirect_response:
        return redirect_response

    # Verify the item exists
    item = Item.query.get(item_id)
    if not item:
        flash("Item not found.", "error")
        return redirect(request.referrer or url_for("player.player_home"))

    # Verify the player actually owns this item
    player_inventory = PlayerInventory.query.filter_by(
        player_id=player.id, item_id=item.item_id
    ).first()
    if not player_inventory or player_inventory.quantity <= 0:
        flash("You do not own this item.", "error")
        return redirect(request.referrer or url_for("player.player_home"))

    character = _get_or_create_active_character(player)

    # Determine target slot
    slot_name = _find_slot_for_item_type(item.type)
    if not slot_name:
        flash("This item cannot be equipped.", "error")
        return redirect(request.referrer or url_for("player.player_home"))

    # Get or create the equipment slot
    slot = CharacterEquipmentSlot.query.filter_by(
        character_id=character.id, slot_name=slot_name
    ).first()
    if not slot:
        slot = CharacterEquipmentSlot(
            character_id=character.id, slot_name=slot_name, item_id=None
        )
        db.session.add(slot)
        db.session.flush()

    slot.item_id = item.item_id
    db.session.commit()

    # For now, just redirect back; front-end can refresh character data via AJAX if desired
    flash(f"Equipped {item.name} to {slot_name.replace('_', ' ').title()}.", "success")
    return redirect(request.referrer or url_for("player.player_home"))


@login_required
def unequip_item(slot_name: str):
    """
    Unequip whatever item is currently in the specified slot.
    """
    player, redirect_response = get_current_player()
    if redirect_response:
        return redirect_response

    character = _get_or_create_active_character(player)

    slot = CharacterEquipmentSlot.query.filter_by(
        character_id=character.id, slot_name=slot_name
    ).first()
    if not slot or not slot.item_id:
        flash("Nothing is equipped in that slot.", "info")
        return redirect(request.referrer or url_for("player.player_home"))

    slot.item_id = None
    db.session.commit()

    flash(f"Unequipped item from {slot_name.replace('_', ' ').title()}.", "success")
    return redirect(request.referrer or url_for("player.player_home"))


@login_required
def create_character():
    """
    Show character creation page for players.
    If no campaigns are available, show a message.
    """
    # Check if player has any campaigns
    player = Player.query.filter_by(user_id_player=current_user.id).first()
    if not player:
        flash("Player profile not found. Please contact support.", "error")
        return redirect(url_for("auth.logout"))
    
    # Get all campaigns this player is a member of
    memberships = CampaignPlayer.query.filter_by(player_id=player.id, is_active=True).all()
    available_campaigns = []
    for membership in memberships:
        campaign = membership.campaign
        if campaign and campaign.is_active:
            available_campaigns.append(campaign)
    
    if not available_campaigns:
        # No campaigns available - show message
        return render_template("Player_Create_Character.html", campaigns=[], has_campaigns=False)
    
    # If there's a campaign in session, use it; otherwise use the first available
    campaign_id = session.get('campaign_id')
    if campaign_id:
        selected_campaign = Campaign.query.filter_by(id=campaign_id).first()
        if selected_campaign and selected_campaign in [c for c in available_campaigns]:
            campaign = selected_campaign
        else:
            campaign = available_campaigns[0]
    else:
        campaign = available_campaigns[0]
    
    # Check if character already exists for this campaign
    existing_character = PlayerCharacter.query.filter_by(
        player_id=player.id,
        campaign_id=campaign.id
    ).first()
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Character name is required.", "error")
            return render_template("Player_Create_Character.html", campaigns=available_campaigns, has_campaigns=True, campaign=campaign, system_type=campaign.system_type)
        
        # Create new character
        character = PlayerCharacter(
            player_id=player.id,
            campaign_id=campaign.id,
            name=name,
            system_type=campaign.system_type,
            level=1,
        )
        db.session.add(character)
        db.session.flush()
        
        # Seed stats based on system
        seed_default_stats_for_character(character, campaign.system_type, db)
        
        # Create default equipment slots
        default_slots = ["head", "chest", "legs", "main_hand", "off_hand"]
        for slot_name in default_slots:
            db.session.add(
                CharacterEquipmentSlot(
                    character_id=character.id,
                    slot_name=slot_name,
                    item_id=None,
                )
            )
        
        db.session.commit()
        
        # Set campaign in session
        session['campaign_id'] = campaign.id
        session['system_type'] = campaign.system_type
        session.modified = True
        
        flash(f"Character '{name}' created successfully!", "success")
        return redirect(url_for("player.player_home"))
    
    # GET request - show creation form
    return render_template(
        "Player_Create_Character.html",
        campaigns=available_campaigns,
        has_campaigns=True,
        campaign=campaign,
        system_type=campaign.system_type
    )


@login_required
def update_character():
    """
    Update character information (name, level, notes, stats).
    """
    player, redirect_response = get_current_player()
    if redirect_response:
        return redirect_response
    
    campaign_id = session.get('campaign_id')
    if not campaign_id:
        flash("No campaign selected.", "error")
        return redirect(url_for("main.campaigns"))
    
    character = PlayerCharacter.query.filter_by(
        player_id=player.id,
        campaign_id=campaign_id
    ).first()
    
    if not character:
        flash("Character not found.", "error")
        return redirect(url_for("player.create_character"))
    
    if request.method == "POST":
        # Update basic fields
        character.name = request.form.get("name", character.name).strip()
        level_str = request.form.get("level", "")
        if level_str:
            try:
                character.level = int(level_str)
            except ValueError:
                pass
        character.notes = request.form.get("notes", character.notes or "")
        
        # Update stats
        for stat in character.stats:
            stat_value = request.form.get(f"stat_{stat.id}", "")
            if stat_value == "":
                stat.value = None
            else:
                try:
                    stat.value = float(stat_value)
                except ValueError:
                    pass
        
        db.session.commit()
        flash("Character updated successfully!", "success")
        return redirect(url_for("player.view_character"))
    
    # GET request - redirect to view
    return redirect(url_for("player.view_character"))

