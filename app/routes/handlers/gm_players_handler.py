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
    Region,
)
from app.routes.handlers.gm_helpers import get_campaign_for_gm_session
from app.services import character_sheet_service
from app.services.equipment.slots import ALL_EQUIPMENT_SLOTS, normalize_slot
from app.services.equipment.item_rules import pick_equip_slot, validate_attunement

EQUIPMENT_SLOTS = ALL_EQUIPMENT_SLOTS


def _embed_mode() -> bool:
    if request.args.get("embed") == "1" or request.form.get("embed") == "1":
        return True
    payload = request.get_json(silent=True) or {}
    if payload.get("embed"):
        return True
    referer = request.referrer or ""
    return "embed=1" in referer


def _redirect_players_pane():
    if _embed_mode():
        return redirect(
            url_for("gm.compendium_embed_close", anchor="players-npcs-pane-content")
        )
    return redirect(url_for("gm.gm_view_players"))


def _redirect_character(character_id: int):
    if _embed_mode():
        return redirect(
            url_for("gm.gm_view_character", character_id=character_id, embed=1)
        )
    return redirect(url_for("gm.gm_view_character", character_id=character_id))


def _ruler_context_from_request():
    region_id = request.args.get("region_id", type=int) or request.form.get(
        "region_id", type=int
    )
    assign_ruler = (
        request.args.get("assign_ruler") == "1"
        or request.form.get("assign_ruler") == "1"
    )
    return region_id, assign_ruler


def _owner_context_from_request():
    city_id = request.args.get("city_id", type=int) or request.form.get(
        "city_id", type=int
    )
    shop_id = request.args.get("shop_id", type=int) or request.form.get(
        "shop_id", type=int
    )
    assign_owner = (
        request.args.get("assign_owner") == "1"
        or request.form.get("assign_owner") == "1"
    )
    return city_id, shop_id, assign_owner


def _assign_region_ruler(campaign_id: int, region_id: int, player_id: int) -> bool:
    region = Region.query.filter_by(id=region_id, campaign_id=campaign_id).first()
    player = Player.query.filter_by(
        id=player_id, campaign_id=campaign_id, is_npc=True
    ).first()
    if region is None or player is None:
        return False
    region.ruler_player_id = player.id
    db.session.flush()
    return True


def _assign_city_owner(campaign_id: int, city_id: int, player_id: int) -> bool:
    from app.models import City

    city = City.query.filter_by(city_id=city_id, campaign_id=campaign_id).first()
    player = Player.query.filter_by(
        id=player_id, campaign_id=campaign_id, is_npc=True
    ).first()
    if city is None or player is None:
        return False
    city.owner_player_id = player.id
    db.session.flush()
    return True


def _assign_shop_owner(campaign_id: int, shop_id: int, player_id: int) -> bool:
    from app.models import Shop

    shop = Shop.query.filter_by(shop_id=shop_id, campaign_id=campaign_id).first()
    player = Player.query.filter_by(
        id=player_id, campaign_id=campaign_id, is_npc=True
    ).first()
    if shop is None or player is None:
        return False
    shop.owner_player_id = player.id
    db.session.flush()
    return True


def _redirect_after_ruler_npc_create(region_id: int):
    if _embed_mode():
        return redirect(url_for("gm.edit_region", region_id=region_id, embed=1))
    return redirect(url_for("gm.edit_region", region_id=region_id))


def _redirect_after_npc_create(
    player_id: int,
    region_id: int | None,
    assign_ruler: bool,
    *,
    city_id: int | None = None,
    shop_id: int | None = None,
    assign_owner: bool = False,
):
    if region_id and assign_ruler:
        return _redirect_after_ruler_npc_create(region_id)
    if city_id and assign_owner:
        if _embed_mode():
            return redirect(url_for("gm.edit_city", city_id=city_id, embed=1))
        return redirect(url_for("gm.edit_city", city_id=city_id))
    if shop_id and assign_owner:
        if _embed_mode():
            return redirect(url_for("gm.edit_shop", shop_id=shop_id, embed=1))
        return redirect(url_for("gm.edit_shop", shop_id=shop_id))
    if _embed_mode():
        return redirect(
            url_for("gm.compendium_embed_close", anchor="players-npcs-pane-content")
        )
    return redirect(url_for("gm.gm_view_character", character_id=player_id))


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
        sheet = character_sheet_service.get_or_default_sheet(player, campaign)
        sheet_name = (sheet.get("name") or "").strip()
        if player.is_npc:
            player_label = sheet_name or f"NPC #{player.id}"
        elif player.user:
            player_label = player.user.username
        else:
            player_label = sheet_name or "Unknown"
        characters = [
            SimpleNamespace(
                id=player.id,
                name=sheet_name or player_label,
                class_name=(sheet.get("class_name") or "").strip() or None,
                level=sheet.get("level"),
            )
        ]
        player_entries.append({"player": player, "characters": characters, "player_label": player_label})
    return player_entries


def build_known_npc_entries(campaign):
    """NPCs the GM has marked visible to players."""
    from app.services.player_npc_service import build_npc_lore_profile

    entries = []
    npcs = (
        Player.query.filter_by(
            campaign_id=campaign.id,
            is_npc=True,
            known_to_players=True,
        )
        .order_by(Player.id.asc())
        .all()
    )
    for npc in npcs:
        profile = build_npc_lore_profile(npc, campaign)
        entries.append(
            {
                "id": npc.id,
                "name": profile["name"],
                "class_name": profile.get("class_name"),
                "species": profile.get("species"),
                "level": profile.get("level"),
                "location_summary": profile.get("location_summary"),
                "locations": profile.get("locations") or [],
            }
        )
    return entries


def _serialize_compendium_entry(entry):
    player = entry["player"]
    char = entry["characters"][0] if entry["characters"] else None
    return {
        "player_id": player.id,
        "label": entry["player_label"],
        "currency": int(player.currency or 0),
        "name": char.name if char else entry["player_label"],
        "class_name": char.class_name if char else None,
        "level": char.level if char else None,
        "known_to_players": bool(getattr(player, "known_to_players", False)),
        "edit_url": url_for("gm.gm_view_character", character_id=player.id),
        "delete_url": url_for("gm.delete_npc_player", player_id=player.id)
        if player.is_npc
        else None,
        "remove_url": url_for("gm.remove_player_from_campaign", player_id=player.id)
        if not player.is_npc
        else None,
    }


def players_compendium_json():
    from flask import jsonify

    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return jsonify({"error": "GM session required."}), 403

    player_entries = build_player_entries(campaign)
    pcs = [e for e in player_entries if not e["player"].is_npc]
    npcs = [e for e in player_entries if e["player"].is_npc]
    return jsonify(
        {
            "players": [_serialize_compendium_entry(e) for e in pcs],
            "npcs": [_serialize_compendium_entry(e) for e in npcs],
        }
    )


def list_players():
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir

    player_entries = build_player_entries(campaign)
    pc_entries = [e for e in player_entries if not e["player"].is_npc]
    npc_entries = [e for e in player_entries if e["player"].is_npc]

    return render_template(
        "GM_view_players.html",
        campaign=campaign,
        player_entries=player_entries,
        pc_entries=pc_entries,
        npc_entries=npc_entries,
    )


def create_npc():
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir

    system_type = (campaign.system_type or "generic").strip().lower()
    region_id, assign_ruler = _ruler_context_from_request()
    city_id, shop_id, assign_owner = _owner_context_from_request()

    if request.method == "GET":
        if system_type == "dnd5e":
            import secrets

            from app.services.character_creation.campaign_settings import (
                get_character_options,
                get_creation_settings,
            )
            from app.services.character_creation.creation_service import (
                wizard_catalog_for_user,
            )
            from app.services.classes_compendium_service import ensure_classes_compendium
            from app.services.species_compendium_service import ensure_species_compendium

            wizard_payload = wizard_catalog_for_user(
                campaign_id=campaign.id,
                species_compendium=ensure_species_compendium(campaign.id),
                classes_compendium=ensure_classes_compendium(campaign.id),
                character_options=get_character_options(campaign.id),
            )
            back_url = (
                url_for("gm.edit_region", region_id=region_id, embed=1)
                if region_id and assign_ruler and _embed_mode()
                else url_for("gm.edit_region", region_id=region_id)
                if region_id and assign_ruler
                else url_for("gm.edit_city", city_id=city_id, embed=1)
                if city_id and assign_owner and _embed_mode()
                else url_for("gm.edit_city", city_id=city_id)
                if city_id and assign_owner
                else url_for("gm.edit_shop", shop_id=shop_id, embed=1)
                if shop_id and assign_owner and _embed_mode()
                else url_for("gm.edit_shop", shop_id=shop_id)
                if shop_id and assign_owner
                else url_for(
                    "gm.compendium_embed_close", anchor="players-npcs-pane-content"
                )
                if _embed_mode()
                else url_for("gm.gm_view_players")
            )
            wizard_title = "Create NPC"
            if assign_ruler:
                wizard_title = "Create ruler"
            elif assign_owner:
                wizard_title = "Create owner"
            wizard_payload.update(
                {
                    "default_system": "dnd5e",
                    "can_add": True,
                    "gm_npc_mode": True,
                    "draft_token": secrets.token_urlsafe(16),
                    "back_url": back_url,
                    "finalize_url": url_for("gm.gm_create_npc_dnd5e_finalize"),
                    "create_button_label": "Create NPC",
                    "wizard_title": wizard_title,
                    "ability_min": 1,
                    "ability_max": 999,
                    "region_id": region_id,
                    "assign_ruler": assign_ruler,
                    "city_id": city_id,
                    "shop_id": shop_id,
                    "assign_owner": assign_owner,
                    "embed": _embed_mode(),
                    "settings": {
                        **wizard_payload.get("settings", {}),
                        "ability_method": "gm_set",
                    },
                }
            )
            return render_template(
                "GM_Create_NPC.html",
                campaign=campaign,
                system_type=system_type,
                wizard_config=wizard_payload,
                use_wizard=True,
                region_id=region_id,
                assign_ruler=assign_ruler,
                city_id=city_id,
                shop_id=shop_id,
                assign_owner=assign_owner,
            )
        return render_template(
            "GM_Create_NPC.html",
            campaign=campaign,
            system_type=system_type,
            use_wizard=False,
            region_id=region_id,
            assign_ruler=assign_ruler,
            city_id=city_id,
            shop_id=shop_id,
            assign_owner=assign_owner,
        )

    name = (request.form.get("name") or "").strip() or None
    class_name = (request.form.get("class_name") or "").strip() or None
    species = (request.form.get("species") or "").strip() or None
    player = None
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
        if region_id and assign_ruler:
            if not _assign_region_ruler(campaign.id, region_id, player.id):
                db.session.rollback()
                flash("NPC was created but could not be assigned as ruler.", "warning")
                return _redirect_players_pane()
        if city_id and assign_owner:
            if not _assign_city_owner(campaign.id, city_id, player.id):
                db.session.rollback()
                flash("NPC was created but could not be assigned as city owner.", "warning")
                return _redirect_players_pane()
        if shop_id and assign_owner:
            if not _assign_shop_owner(campaign.id, shop_id, player.id):
                db.session.rollback()
                flash("NPC was created but could not be assigned as shop owner.", "warning")
                return _redirect_players_pane()
        db.session.commit()
        flash("NPC added to this campaign.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")
        return _redirect_players_pane()
    return _redirect_after_npc_create(
        player.id,
        region_id,
        assign_ruler,
        city_id=city_id,
        shop_id=shop_id,
        assign_owner=assign_owner,
    )


def create_npc_dnd5e_finalize():
    from flask import jsonify

    from app.services.character_creation.campaign_settings import (
        get_character_options,
        get_creation_settings,
    )
    from app.services.character_creation.creation_service import (
        CreationValidationError,
        build_final_sheet_json,
        wizard_catalog_for_user,
    )
    from app.services.classes_compendium_service import ensure_classes_compendium
    from app.services.species_compendium_service import ensure_species_compendium

    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    if (campaign.system_type or "").strip().lower() != "dnd5e":
        return jsonify({"ok": False, "errors": ["NPC wizard is D&D 5e only."]}), 400

    payload = request.get_json(silent=True) or {}
    region_id = payload.get("region_id")
    assign_ruler = bool(payload.get("assign_ruler"))
    city_id = payload.get("city_id")
    shop_id = payload.get("shop_id")
    assign_owner = bool(payload.get("assign_owner"))
    if region_id is not None:
        try:
            region_id = int(region_id)
        except (TypeError, ValueError):
            region_id = None
    if city_id is not None:
        try:
            city_id = int(city_id)
        except (TypeError, ValueError):
            city_id = None
    if shop_id is not None:
        try:
            shop_id = int(shop_id)
        except (TypeError, ValueError):
            shop_id = None
    try:
        ctx = wizard_catalog_for_user(
            campaign_id=campaign.id,
            species_compendium=ensure_species_compendium(campaign.id),
            classes_compendium=ensure_classes_compendium(campaign.id),
            character_options=get_character_options(campaign.id),
        )
        sheet_json = build_final_sheet_json(
            payload,
            catalog=ctx["catalog"],
            settings=get_creation_settings(campaign.id),
            roll_draft=None,
            uncapped=True,
        )
        if not sheet_json.get("name"):
            sheet_json["name"] = _next_default_npc_label(campaign.id)

        player = Player(
            is_npc=True,
            user_id=None,
            campaign_id=campaign.id,
            currency=0,
        )
        db.session.add(player)
        db.session.flush()
        db.session.add(
            PlayerCharacterSheet(
                player_id=player.id,
                campaign_id=campaign.id,
                sheet_json=sheet_json,
            )
        )
        if region_id and assign_ruler:
            if not _assign_region_ruler(campaign.id, region_id, player.id):
                db.session.rollback()
                return jsonify(
                    {"ok": False, "errors": ["Could not assign ruler to this nation."]}
                ), 400
        if city_id and assign_owner:
            if not _assign_city_owner(campaign.id, city_id, player.id):
                db.session.rollback()
                return jsonify(
                    {"ok": False, "errors": ["Could not assign owner to this city."]}
                ), 400
        if shop_id and assign_owner:
            if not _assign_shop_owner(campaign.id, shop_id, player.id):
                db.session.rollback()
                return jsonify(
                    {"ok": False, "errors": ["Could not assign owner to this shop."]}
                ), 400
        db.session.commit()
        if region_id and assign_ruler:
            redirect_url = (
                url_for("gm.edit_region", region_id=region_id, embed=1)
                if _embed_mode()
                else url_for("gm.edit_region", region_id=region_id)
            )
        elif city_id and assign_owner:
            redirect_url = (
                url_for("gm.edit_city", city_id=city_id, embed=1)
                if _embed_mode()
                else url_for("gm.edit_city", city_id=city_id)
            )
        elif shop_id and assign_owner:
            redirect_url = (
                url_for("gm.edit_shop", shop_id=shop_id, embed=1)
                if _embed_mode()
                else url_for("gm.edit_shop", shop_id=shop_id)
            )
        elif _embed_mode():
            redirect_url = url_for(
                "gm.compendium_embed_close", anchor="players-npcs-pane-content"
            )
        else:
            redirect_url = url_for("gm.gm_view_character", character_id=player.id)
        return jsonify(
            {
                "ok": True,
                "player_id": player.id,
                "redirect_url": redirect_url,
                "sheet": sheet_json,
            }
        )
    except CreationValidationError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "errors": [str(exc)]}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "errors": [f"Could not create NPC: {exc}"]}), 500


def view_character(character_id: int):
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_campaign(character_id, campaign.id)
    if not player:
        flash("Player not found in this campaign.", "danger")
        return _redirect_players_pane()
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
    )


def update_character(character_id: int):
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_campaign(character_id, campaign.id)
    if not player:
        flash("Player not found.", "danger")
        return _redirect_players_pane()

    # This route serves both the narrow "currency only" legacy form and the
    # full character sheet form. We dispatch on which fields are present to
    # keep the existing currency-save button working without changes.
    form_section = (request.form.get("form_section") or "").strip()

    try:
        if form_section == "sheet":
            if player.is_npc:
                player.gm_notes = (request.form.get("gm_notes") or "").strip() or None
                player.known_to_players = request.form.get("known_to_players") == "1"
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
    return _redirect_character(character_id)


def update_inventory(character_id: int):
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_campaign(character_id, campaign.id)
    if not player:
        flash("Player not found.", "danger")
        return _redirect_players_pane()

    action = request.form.get("action", "set")
    item_id = request.form.get("item_id", type=int)
    quantity = request.form.get("quantity", type=int)

    if item_id is None:
        flash("Item is required.", "danger")
        return _redirect_character(character_id)

    item = Item.query.filter_by(item_id=item_id, campaign_id=campaign.id).first()
    if not item:
        flash("Invalid item for this campaign.", "danger")
        return _redirect_character(character_id)

    try:
        row = PlayerInventory.query.filter_by(player_id=player.id, item_id=item_id).first()
        if action == "remove":
            if row:
                db.session.delete(row)
            db.session.commit()
            flash("Inventory row removed.", "success")
            return _redirect_character(character_id)

        if quantity is None or quantity < 0:
            flash("Valid quantity required.", "danger")
            return _redirect_character(character_id)

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
    return _redirect_character(character_id)


def equip_item(character_id: int):
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_campaign(character_id, campaign.id)
    if not player:
        flash("Player not found.", "danger")
        return _redirect_players_pane()

    slot = normalize_slot((request.form.get("slot") or "").strip())
    item_id = request.form.get("item_id", type=int)
    if not slot or slot not in EQUIPMENT_SLOTS:
        flash("Invalid equipment slot.", "danger")
        return _redirect_character(character_id)
    if item_id is None:
        flash("Item is required.", "danger")
        return _redirect_character(character_id)

    item = Item.query.filter_by(item_id=item_id, campaign_id=campaign.id).first()
    if not item:
        flash("Invalid item.", "danger")
        return _redirect_character(character_id)

    resolved_slot = pick_equip_slot(player, item, requested_slot=slot)
    if not resolved_slot:
        flash("This item cannot be equipped in that slot.", "danger")
        return _redirect_character(character_id)
    attune_err = validate_attunement(player, item)
    if attune_err:
        flash(attune_err, "warning")
        return _redirect_character(character_id)

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
    return _redirect_character(character_id)


def unequip_item(character_id: int):
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = _player_for_campaign(character_id, campaign.id)
    if not player:
        flash("Player not found.", "danger")
        return _redirect_players_pane()

    slot = normalize_slot((request.form.get("slot") or "").strip())
    if not slot or slot not in EQUIPMENT_SLOTS:
        flash("Invalid slot.", "danger")
        return _redirect_character(character_id)

    try:
        eq = PlayerEquipment.query.filter_by(player_id=player.id, slot=slot).first()
        if eq:
            eq.item_id = None
            db.session.commit()
        flash("Slot cleared.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")
    return _redirect_character(character_id)


def remove_player_from_campaign(player_id: int):
    """Drop a PC from the active campaign (clears Player.campaign_id, keeps Player row)."""
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = Player.query.filter_by(id=player_id, campaign_id=campaign.id).first()
    if not player or player.is_npc:
        flash("Player not found.", "danger")
        return _redirect_players_pane()
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
    return _redirect_players_pane()


def delete_npc_player(player_id: int):
    """Permanently delete an NPC and all dependent rows."""
    gm_profile, campaign, redir = get_campaign_for_gm_session()
    if redir:
        return redir
    player = Player.query.filter_by(id=player_id, campaign_id=campaign.id).first()
    if not player or not player.is_npc:
        flash("NPC not found.", "danger")
        return _redirect_players_pane()
    try:
        from app.models import City, Region, Shop

        Region.query.filter_by(
            campaign_id=campaign.id, ruler_player_id=player.id
        ).update({Region.ruler_player_id: None}, synchronize_session=False)
        City.query.filter_by(
            campaign_id=campaign.id, owner_player_id=player.id
        ).update({City.owner_player_id: None}, synchronize_session=False)
        Shop.query.filter_by(
            campaign_id=campaign.id, owner_player_id=player.id
        ).update({Shop.owner_player_id: None}, synchronize_session=False)
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
    return _redirect_players_pane()
