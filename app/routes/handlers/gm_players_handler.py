<<<<<<< HEAD
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
=======
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
from app.services.equipment.slots import ALL_EQUIPMENT_SLOTS, normalize_slot
from app.services.equipment.item_rules import pick_equip_slot, validate_attunement

EQUIPMENT_SLOTS = ALL_EQUIPMENT_SLOTS


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
>>>>>>> GCP
        .all()
    )

    player_entries = []
<<<<<<< HEAD
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
=======
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
>>>>>>> GCP

    return render_template(
        "GM_view_players.html",
        campaign=campaign,
        player_entries=player_entries,
    )


<<<<<<< HEAD
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
=======
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
    equipment = {normalize_slot(e.slot) or e.slot: e for e in player.equipment_slots}
    for slot in EQUIPMENT_SLOTS:
        equipment.setdefault(slot, None)

    equipment_slot_views = [
        SimpleNamespace(
            slot_name=slot,
            item=(equipment[slot].item if equipment.get(slot) and equipment[slot].item_id else None),
        )
        for slot in EQUIPMENT_SLOTS
        if equipment.get(slot) and equipment[slot].item_id
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
>>>>>>> GCP
    )


def update_character(character_id: int):
<<<<<<< HEAD
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

    # Stats: iterate through existing stats and update from form inputs.
    # Only update stats that actually have a corresponding form field so
    # that derived-only stats (like skills for 5e) are not accidentally cleared.
    # Armor Class and other derived defenses remain read-only from the GM side.
    for stat in character.stats:
        # Server-side guard: never update armor class-derived stats from this form.
        if stat.stat_key in ("armor_class", "ac", "armor_class_base"):
            continue

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

    # 5e-specific proficiency wiring (skills and saves), mirrored from the player handler
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

=======
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

    slot = normalize_slot((request.form.get("slot") or "").strip())
    item_id = request.form.get("item_id", type=int)
    if not slot or slot not in EQUIPMENT_SLOTS:
        flash("Invalid equipment slot.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))
    if item_id is None:
        flash("Item is required.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))

    item = Item.query.filter_by(item_id=item_id, campaign_id=campaign.id).first()
    if not item:
        flash("Invalid item.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))

    resolved_slot = pick_equip_slot(player, item, requested_slot=slot)
    if not resolved_slot:
        flash("This item cannot be equipped in that slot.", "danger")
        return redirect(url_for("gm.gm_view_character", character_id=character_id))
    attune_err = validate_attunement(player, item)
    if attune_err:
        flash(attune_err, "warning")
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

        eq = PlayerEquipment.query.filter_by(player_id=player.id, slot=resolved_slot).first()
        if eq:
            eq.item_id = item_id
            eq.source = "GM"
        else:
            db.session.add(
                PlayerEquipment(
                    player_id=player.id,
                    slot=resolved_slot,
                    item_id=item_id,
                    source="GM",
                )
            )
        db.session.commit()
        flash(f"Equipped to {resolved_slot.replace('_', ' ')} (+1 to inventory, tagged GM).", "success")
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

    slot = normalize_slot((request.form.get("slot") or "").strip())
    if not slot or slot not in EQUIPMENT_SLOTS:
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
>>>>>>> GCP
