"""
Player Character Handler
Handles character model, stats, and equipment for the player.
"""

from flask import jsonify, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required

from app.extensions import db
from app.models.users import Player, PlayerCharacter, CharacterEquipmentSlot, CharacterStat, PlayerInventory
from app.config.system_config import seed_default_stats_for_character, get_system_schema
from app.services.character_math import compute_character_derived_stats, ability_modifier
from app.models.backend import Item
from app.models.campaigns import Campaign, CampaignPlayer
from app.routes.handlers.player_helpers import get_current_player
from flask import session


# --- Helpers -----------------------------------------------------------------

DEFAULT_SYSTEM_TYPE = "generic"

# Single source of truth for equipment slots (Head, Neck, Torso, Hands, Finger x2, Legs, Feet, Main Hand, Off Hand)
DEFAULT_EQUIPMENT_SLOTS = [
    "head", "neck", "torso", "hands", "finger_1", "finger_2",
    "legs", "feet", "main_hand", "off_hand",
]


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
    seed_default_stats_for_character(character, character.system_type, db.session)

    # Pre-create equipment slots (shared schema with create_character)
    for slot_name in DEFAULT_EQUIPMENT_SLOTS:
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
    stats_list = list(character.stats) if character.stats else []
    stats = [
        {
            "id": stat.id,
            "key": stat.stat_key,
            "category": stat.category,
            "value": stat.value,
        }
        for stat in stats_list
    ]

    slots = []
    for slot in (character.equipment_slots or []):
        item_data = None
        if slot.item:
            desc = (slot.item.description or "")[:100]
            if len(slot.item.description or "") > 100:
                desc += "..."
            item_data = {
                "item_id": slot.item.item_id,
                "name": slot.item.name,
                "type": slot.item.type,
                "rarity": slot.item.rarity,
                "description_short": desc,
            }
        slots.append(
            {
                "id": slot.id,
                "slot_name": slot.slot_name,
                "item": item_data,
            }
        )

    # Compute system-specific derived values (skills and saves)
    computed = compute_character_derived_stats(character, character.stats or [])

    # Proficiency metadata (kept out of the main stat_display groups)
    skill_prof_tiers = {
        stat.stat_key: stat.value
        for stat in stats_list
        if stat.category == "skill_prof_tier"
    }
    save_prof_flags = {
        stat.stat_key: stat.value
        for stat in stats_list
        if stat.category == "save_prof_flag"
    }

    schema = get_system_schema(character.system_type or "generic")
    stat_schema = [
        {"key": f.key, "label": f.label, "category": f.category}
        for f in schema
    ]
    # Index stats by (category, key) so that parallel fields like
    # "Athletics" (skill) and "Athletics" (skill_prof) do not overwrite
    # each other when we look up display values.
    stats_by_key = {(s["category"], s["key"]): s for s in stats}
    stat_display = []
    for f in schema:
        s = stats_by_key.get((f.category, f.key))
        base_entry = {
            "id": s["id"] if s else None,
            "key": f.key,
            "label": f.label,
            "category": f.category,
            "value": s["value"] if s else None,
        }

        # Attach computed skill/save modifiers when available
        if f.category == "skill":
            base_entry["computed_value"] = computed.skills.get(f.key)
        elif f.category == "save":
            base_entry["computed_value"] = computed.saves.get(f.key)
        elif f.category == "ability":
            # Also attach the derived ability modifier for display (always an int)
            score = s["value"] if s else None
            base_entry["modifier"] = ability_modifier(score)

        stat_display.append(base_entry)

    # Split stats into logical groups for the template
    abilities_display = [
        s for s in stat_display if s.get("category") == "ability"
    ]
    skills_display = [
        s for s in stat_display if s.get("category") == "skill"
    ]
    defenses_display = [
        s
        for s in stat_display
        if s.get("category") in {"derived", "save", "defense"}
    ]

    return {
        "id": character.id,
        "name": character.name,
        "class_name": getattr(character, "class_name", None),
        "species": getattr(character, "species", None),
        "system_type": character.system_type,
        "level": character.level,
        "notes": character.notes,
        "stats": stats,
        "equipment_slots": slots,
        "stat_schema": stat_schema,
        "stat_display": stat_display,
        "abilities_display": abilities_display or stat_display,
        "skills_display": skills_display,
        "defenses_display": defenses_display,
        "skill_prof_tiers": skill_prof_tiers,
        "save_prof_flags": save_prof_flags,
    }


def _find_slot_for_item_type(item_type: str) -> str | None:
    """
    Map item.type to a character equipment slot.
    Supports: head, neck, torso, hands, finger_1, finger_2, legs, feet, main_hand, off_hand.
    """
    if not item_type:
        return None

    normalized = item_type.lower()
    if "helm" in normalized or "head" in normalized or "hat" in normalized:
        return "head"
    if "amulet" in normalized or "necklace" in normalized or "neck" in normalized:
        return "neck"
    if "armor" in normalized or "chest" in normalized or "torso" in normalized or "body" in normalized:
        return "torso"
    if "glove" in normalized or "gauntlet" in normalized or "hands" in normalized:
        return "hands"
    if "ring" in normalized:
        return "finger_1"  # UI can allow choosing finger_2 if needed
    if "boots" in normalized or "feet" in normalized or "shoes" in normalized:
        return "feet"
    if "legs" in normalized or "greave" in normalized or "pants" in normalized:
        return "legs"
    if "shield" in normalized or "off-hand" in normalized or "off hand" in normalized:
        return "off_hand"
    if "weapon" in normalized or "sword" in normalized or "main-hand" in normalized or "main hand" in normalized:
        return "main_hand"

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

    # Stats: iterate through existing stats and update from form inputs.
    # Only update stats that actually have a corresponding form field so
    # that derived-only stats (like skills for 5e) are not accidentally cleared.
    for stat in character.stats:
        field_name = f"stat_{stat.id}"
        raw_value = request.form.get(field_name, None)
        if raw_value is None:
            continue
        raw_value = raw_value.strip()
        if raw_value == "":
            # Allow clearing a value
            stat.value = None
        else:
            try:
                stat.value = float(raw_value)
            except ValueError:
                # Leave previous value intact but notify the user
                flash(f"Invalid value for {stat.stat_key}; expected a number.", "error")

    # 5e-specific proficiency wiring (skills and saves)
    system_type = (character.system_type or "").lower()
    if system_type in {"dnd", "dnd5e", "5e"}:
        # Skill proficiency tiers
        skill_tier_stats = {
            (s.stat_key): s
            for s in character.stats
            if s.category == "skill_prof_tier"
        }
        for skill_key, stat in skill_tier_stats.items():
            flag_field = f"skill_prof_flag_{skill_key}"
            tier_field = f"skill_prof_tier_{skill_key}"
            flag_raw = request.form.get(flag_field)
            if not flag_raw:
                # Unchecked -> untrained
                stat.value = 0.0
                continue
            tier_raw = request.form.get(tier_field, "2")
            try:
                tier_int = int(tier_raw)
            except ValueError:
                tier_int = 2
            if tier_int not in (1, 2, 3):
                tier_int = 2
            stat.value = float(tier_int)

        # Save proficiency flags (binary)
        save_flag_stats = {
            (s.stat_key): s
            for s in character.stats
            if s.category == "save_prof_flag"
        }
        for save_key, stat in save_flag_stats.items():
            flag_field = f"save_prof_flag_{save_key}"
            flag_raw = request.form.get(flag_field)
            stat.value = 1.0 if flag_raw else 0.0

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

    # Prevent duplicate characters per player/campaign, but ensure session context
    # is set to this campaign so the existing character is shown correctly.
    if existing_character:
        session["campaign_id"] = campaign.id
        session["system_type"] = campaign.system_type
        session.modified = True
        flash("You already have a character for this campaign.", "info")
        return redirect(url_for("player.view_character"))
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        class_name = request.form.get("class_name", "").strip()
        species = request.form.get("species", "").strip()
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
            class_name=class_name or None,
            species=species or None,
        )
        db.session.add(character)
        db.session.flush()
        
        # Seed stats based on system
        seed_default_stats_for_character(character, campaign.system_type, db.session)
        
        # Create default equipment slots (same schema as _get_or_create_active_character)
        for slot_name in DEFAULT_EQUIPMENT_SLOTS:
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

