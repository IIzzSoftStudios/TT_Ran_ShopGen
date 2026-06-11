import io
from types import SimpleNamespace
from typing import Optional

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from sqlalchemy.orm import subqueryload

from app.models import (
    Player,
    PlayerCharacterSheet,
    City,
    Shop,
    ShopInventory,
    Item,
    PlayerInventory,
    PlayerEquipment,
    Campaign,
    Region,
    MapCanvas,
    shop_cities,
)

EQUIPMENT_SLOTS = ("weapon", "armor", "accessory")
from flask_login import login_required, current_user
from app.extensions import db, limiter
from app.services.player_resolution import (
    get_active_player,
    get_active_player_or_ensure_solo,
    ensure_solo_player_profile,
    all_player_ids_for_user,
    get_character_for_user,
    list_user_characters,
)
from app.services.billing_rules import can_add_player_profile
from app.services.join_codes import (
    redeem_campaign_code,
    InvalidCodeError,
    SeatCapError,
    WrongRoleError,
    JoinCodeError,
    log_reveal,
    reveal_player_code_for_player,
)
from app.constants.simulation_flags import READ_PRICES_FROM_WORLD_STATE
from app.services.world_state_reads import get_effective_price, get_effective_stock
from app.services import character_sheet_service
from app.routes.handlers.gm_shops_handler import (
    _city_region_label,
    _region_table_exists,
)

player_bp = Blueprint("player", __name__)


@player_bp.route("/battle")
@login_required
def battle_panel():
    """Minimal player encounter panel (D&D 5e campaigns only).

    Finds the newest non-ended battle encounter across the user's D&D 5e
    campaign characters; the board itself loads through /api/combat which
    re-checks campaign membership and the D&D 5e gate server-side.
    """
    from app.models import BattleEncounter
    from app.services.rulesets import get_ruleset

    own_players = [
        p
        for p in Player.query.filter_by(user_id=current_user.id, is_npc=False).all()
        if p.campaign_id is not None
    ]
    dnd5e_players = [
        p
        for p in own_players
        if p.campaign is not None
        and get_ruleset(p.campaign.system_type).system_type == "dnd5e"
    ]
    if not dnd5e_players:
        flash("Battles are only available in D&D 5e campaigns.", "info")
        return redirect(url_for("player.list_characters"))

    campaign_ids = {p.campaign_id for p in dnd5e_players}
    encounter = (
        BattleEncounter.query.filter(
            BattleEncounter.campaign_id.in_(campaign_ids),
            BattleEncounter.status != "ended",
            BattleEncounter.visible_to_players.is_(True),
        )
        .order_by(BattleEncounter.id.desc())
        .first()
    )
    return render_template(
        "Player_Battle.html",
        encounter=encounter,
        own_player_ids=[p.id for p in dnd5e_players],
    )


def _redirect_solo_vault_to_character():
    flash(
        "Join a campaign to browse the world. You can still edit your character vault.",
        "info",
    )
    return redirect(url_for("player.list_characters"))


def _inventory_items_for_player(player):
    return (
        db.session.query(
            PlayerInventory.quantity,
            Item.name,
            Item.type,
            Item.rarity,
            Item.description,
            Item.item_id,
            Item.base_price,
        )
        .join(Item, PlayerInventory.item_id == Item.item_id)
        .filter(PlayerInventory.player_id == player.id)
        .all()
    )


def _equipment_slot_views_for_player(player):
    return [
        SimpleNamespace(slot_name=eq.slot, item=eq.item)
        for eq in (player.equipment_slots or [])
    ]


def _render_solo_character_dashboard(player):
    character_ctx = character_sheet_service.build_character_view(
        player,
        None,
        equipment_slots=_equipment_slot_views_for_player(player),
    )
    return render_template(
        "Player_Home.html",
        player=player,
        player_name=character_ctx.name,
        player_currency=int(player.currency or 0),
        character=character_ctx,
        player_has_active_campaign=False,
        player_join_code_reveal_url=url_for(
            "player.reveal_character_join_code", player_id=player.id
        ),
        character_data_url=url_for("player.character_data_id", player_id=player.id),
        combat_enabled=False,
        battle_encounter=None,
        battle_own_player_ids=[],
        cities=[],
        shops=[],
        items=[],
        inventory_items=_inventory_items_for_player(player),
        shop_items_by_shop={},
        city_browse=[],
        region_labels=[],
        campaign_regions=[],
    )


_PLAYER_ALLOWLIST = frozenset(
    {
        "static",
        "player.redeem_campaign_code_route",
        "player.reveal_player_join_code",
    }
)

# Character vault: no campaign code required; routes may lazy-create solo Player.
_CHARACTER_VAULT_ENDPOINTS = frozenset(
    {
        "player.create_character",
        "player.create_character_dnd5e_roll",
        "player.create_character_dnd5e_finalize",
        "player.list_characters",
        "player.view_character",
        "player.view_character_id",
        "player.character_dashboard",
        "player.character_data_id",
        "player.reveal_character_join_code",
        "player.update_character",
        "player.delete_character",
    }
)


@player_bp.before_request
def before_request():
    print(f"[DEBUG] Player Blueprint - Request URL: {request.url}")
    print(f"[DEBUG] Player Blueprint - Request Method: {request.method}")
    print(f"[DEBUG] Player Blueprint - Current User: {current_user.username if current_user.is_authenticated else 'Not authenticated'}")
    if not current_user.is_authenticated:
        return None
    ep = request.endpoint
    if ep in _PLAYER_ALLOWLIST or ep in _CHARACTER_VAULT_ENDPOINTS:
        return None

    from app.services.user_capabilities import has_player_capability

    if session.get("session_mode") == "gm":
        flash(
            "You are currently using GM tools. Please return to the picker to switch your active view.",
            "info",
        )
        return redirect(url_for("main.campaigns"))

    if not has_player_capability(current_user):
        flash("Access to player tools is restricted.", "danger")
        return redirect(url_for("main.campaigns"))

    if get_active_player(current_user) is None:
        return redirect(url_for("main.campaigns"))
    return None


@player_bp.route("/redeem_campaign_code", methods=["POST"])
@login_required
@limiter.limit("3 per hour")
def redeem_campaign_code_route():
    from app.routes.handlers import campaign_selection_handler as csh

    from app.services.user_capabilities import can_redeem_campaign_code

    if not can_redeem_campaign_code(current_user):
        flash("Only players can redeem a campaign code.", "warning")
        return redirect(url_for("main.campaigns"))
    code = (request.form.get("campaign_code") or "").strip()
    if not code:
        flash("Enter a campaign code.", "warning")
        return redirect(request.referrer or url_for("player.player_home"))
    raw_player_id = (request.form.get("player_id") or "").strip()
    scoped_player_id: Optional[int] = None
    if raw_player_id:
        try:
            scoped_player_id = int(raw_player_id)
        except (TypeError, ValueError):
            scoped_player_id = None
    fails = csh._redeem_failures_in_window()
    if len(fails) >= 3:
        flash("Too many invalid code attempts. Try again in up to one hour.", "danger")
        return redirect(request.referrer or url_for("main.campaigns"))
    try:
        from app.services.join_codes import REDEMPTION_SOURCE_PLAYER_JOIN

        campaign = redeem_campaign_code(
            current_user,
            code,
            player_id=scoped_player_id,
            source=REDEMPTION_SOURCE_PLAYER_JOIN,
            _commit=True,
        )
        player = None
        if scoped_player_id is not None:
            player = get_character_for_user(current_user, scoped_player_id)
        if player is None:
            player = Player.query.filter_by(
                user_id=current_user.id,
                campaign_id=campaign.id,
                is_npc=False,
            ).order_by(Player.id.desc()).first()
        session["campaign_id"] = campaign.id
        session["system_type"] = campaign.system_type
        if player is not None:
            session["player_id"] = player.id
        session.permanent = True
        session.modified = True
        csh._clear_redeem_failures()
        flash("You joined the campaign.", "success")
        if player is not None and (campaign.system_type or "").lower() == "dnd5e":
            return redirect(
                url_for("player.create_character", campaign_player_id=player.id)
            )
        if scoped_player_id is not None:
            return redirect(
                url_for("player.character_dashboard", player_id=scoped_player_id)
            )
        return redirect(url_for("player.player_home"))
    except (InvalidCodeError, SeatCapError, WrongRoleError, JoinCodeError) as e:
        csh._register_redeem_failure()
        flash(
            (e.args[0] if getattr(e, "args", None) else None)
            or "Could not join with that code.",
            "danger",
        )
    return redirect(request.referrer or url_for("main.campaigns"))


@player_bp.route("/reveal-code", methods=["GET"])
@login_required
@limiter.limit("60 per hour")
def reveal_player_join_code():
    player = get_active_player(current_user)
    if not player:
        return jsonify(error="forbidden"), 403
    try:
        code = reveal_player_code_for_player(
            user_id=current_user.id, player=player
        )
        log_reveal(
            user_id=current_user.id,
            action="REVEAL_PLAYER_CODE",
            target_id=player.id,
            ip=request.remote_addr or "",
        )
        return jsonify(code=code)
    except (InvalidCodeError, WrongRoleError, JoinCodeError):
        return jsonify(error="forbidden"), 403


@player_bp.route("/character/<int:player_id>/reveal-code", methods=["GET"])
@login_required
@limiter.limit("60 per hour")
def reveal_character_join_code(player_id):
    player = get_character_for_user(current_user, player_id)
    if not player:
        return jsonify(error="forbidden"), 403
    try:
        code = reveal_player_code_for_player(
            user_id=current_user.id, player=player
        )
        log_reveal(
            user_id=current_user.id,
            action="REVEAL_PLAYER_CODE",
            target_id=player.id,
            ip=request.remote_addr or "",
        )
        return jsonify(code=code)
    except (InvalidCodeError, WrongRoleError, JoinCodeError):
        return jsonify(error="forbidden"), 403

# Shop routes first (more specific)
@player_bp.route("/shop/<int:shop_id>")
@login_required
def view_shop(shop_id):
    try:
        player = get_active_player(current_user)
        if not player:
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))
        if player.campaign_id is None:
            return _redirect_solo_vault_to_character()

        campaign_id = player.campaign_id

        shop = (
            Shop.query.filter_by(shop_id=shop_id, campaign_id=campaign_id)
            .options(db.joinedload(Shop.cities))
            .first()
        )
        if not shop:
            flash('You do not have access to this shop.', 'error')
            return redirect(url_for('player.player_home'))

        city = shop.cities[0] if shop.cities else None
        if not city:
            flash('Shop location not found.', 'error')
            return redirect(url_for('player.player_home'))

        shop_items_raw = (
            db.session.query(
                Item.name,
                Item.type,
                ShopInventory.stock,
                ShopInventory.dynamic_price,
                Item.item_id,
                Item.base_price,
                ShopInventory.inventory_id,
            )
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .filter(ShopInventory.shop_id == shop_id)
            .filter(ShopInventory.campaign_id == campaign_id)
            .all()
        )
        if READ_PRICES_FROM_WORLD_STATE:
            shop_items = [
                SimpleNamespace(
                    name=r.name,
                    type=r.type,
                    stock=get_effective_stock(
                        campaign_id, r.inventory_id, int(r.stock)
                    ),
                    dynamic_price=get_effective_price(
                        campaign_id, r.inventory_id, float(r.dynamic_price)
                    ),
                    item_id=r.item_id,
                    base_price=r.base_price,
                )
                for r in shop_items_raw
            ]
        else:
            shop_items = [
                SimpleNamespace(
                    name=r.name,
                    type=r.type,
                    stock=r.stock,
                    dynamic_price=r.dynamic_price,
                    item_id=r.item_id,
                    base_price=r.base_price,
                )
                for r in shop_items_raw
            ]

        print(f"[DEBUG] Found {len(shop_items)} items in shop")

        # Get player's inventory quantities for each item
        player_inventory = {}
        for item in shop_items:
            inventory_entry = PlayerInventory.query.filter_by(
                player_id=player.id,
                item_id=item.item_id
            ).first()
            player_inventory[item.item_id] = inventory_entry.quantity if inventory_entry else 0

        def getStockStatus(stock):
            if stock <= 0:
                return "out-of-stock"
            elif stock <= 5:
                return "low-stock"
            else:
                return "in-stock"

        return render_template(
            "Player_view_city_shops.html",
            shop=shop,
            city=city,
            shop_items=shop_items,
            player_currency=player.currency,
            player_inventory=player_inventory,
            getStockStatus=getStockStatus
        )
    except Exception as e:
        print(f"[ERROR] Error viewing shop: {e}")
        print(f"[ERROR] Exception type: {type(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        flash('An error occurred while viewing the shop.', 'error')
        return redirect(url_for('player.player_home'))

@player_bp.route("/shops")
@player_bp.route("/cities")
@player_bp.route("/cities/<int:city_id>")
@login_required
def legacy_player_browse_redirect(city_id=None):
    """Retired list/browse pages — player home includes the shop browse panel."""
    return redirect(url_for("player.player_home"))

# Home route last (least specific)
@player_bp.route("/home")
@login_required
def player_home():
    player = get_active_player(current_user)
    if not player:
        flash("Join a campaign with a code first.", "warning")
        return redirect(url_for("main.campaigns"))

    if player.campaign_id is None:
        flash(
            "Join a campaign to browse shops. You can still build your character from "
            "the character sheet.",
            "info",
        )
        return redirect(url_for("player.list_characters"))

    campaign_id = player.campaign_id
    active_campaign = player.campaign
    if active_campaign is None:
        flash("Your campaign could not be loaded.", "error")
        return redirect(url_for("main.campaigns"))
    gm_profile = active_campaign.gm_profile

    cities_q = City.query.filter_by(campaign_id=campaign_id)
    if _region_table_exists():
        cities_q = cities_q.options(subqueryload(City.region_obj))
    cities = cities_q.all()

    shops = (
        Shop.query.filter_by(campaign_id=campaign_id)
        .options(db.joinedload(Shop.cities))
        .all()
    )

    shop_items = (
        db.session.query(Item)
        .filter(
            Item.item_id.in_(
                db.session.query(ShopInventory.item_id)
                .join(Shop, Shop.shop_id == ShopInventory.shop_id)
                .filter(Shop.campaign_id == campaign_id)
            )
        )
        .all()
    )

    inventory_pairs = (
        db.session.query(ShopInventory.shop_id, ShopInventory.item_id)
        .join(Shop, Shop.shop_id == ShopInventory.shop_id)
        .filter(Shop.campaign_id == campaign_id)
        .all()
    )
    item_by_id = {it.item_id: it for it in shop_items}
    shop_items_by_shop: dict[int, list[dict]] = {}
    seen_per_shop: dict[int, set] = {}
    for shop_id, item_id in inventory_pairs:
        it = item_by_id.get(item_id)
        if it is None:
            continue
        seen_ids = seen_per_shop.setdefault(shop_id, set())
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        shop_items_by_shop.setdefault(shop_id, []).append({
            "id": it.item_id,
            "name": it.name,
            "type": it.type,
            "rarity": it.rarity,
        })
    print(f"[DEBUG] Built shop_items_by_shop for {len(shop_items_by_shop)} shops")

    # Get player's inventory with item details
    inventory_items = (
        db.session.query(
            PlayerInventory.quantity,
            Item.name,
            Item.type,
            Item.rarity,
            Item.description,
            Item.item_id,
            Item.base_price
        )
        .join(Item, PlayerInventory.item_id == Item.item_id)
        .filter(PlayerInventory.player_id == player.id)
        .all()
    )
    print(f"[DEBUG] Found {len(inventory_items)} items in player's inventory")

    # Build the City -> Shop -> Items browse accordion data that replaces
    # the old filter-based search UI. One bulk inventory query (keyed by
    # shop_id) combined with the already-loaded cities/shops keeps this at
    # three round-trips regardless of campaign size, and the world-state
    # overlay mirrors player.view_shop so displayed price/stock match what
    # the buy action will actually charge.
    inv_rows = (
        db.session.query(
            ShopInventory.shop_id,
            ShopInventory.inventory_id,
            ShopInventory.dynamic_price,
            ShopInventory.stock,
            Item.item_id,
            Item.name,
            Item.type,
            Item.rarity,
        )
        .join(Item, Item.item_id == ShopInventory.item_id)
        .join(Shop, Shop.shop_id == ShopInventory.shop_id)
        .filter(Shop.campaign_id == campaign_id)
        .order_by(Item.name.asc())
        .all()
    )

    items_by_shop: dict[int, list[dict]] = {}
    for row in inv_rows:
        shop_id = row[0]
        inv_id = row[1]
        dyn_price = row[2]
        raw_stock = row[3]
        it_id = row[4]
        it_name = row[5]
        it_type = row[6]
        it_rarity = row[7]
        if READ_PRICES_FROM_WORLD_STATE:
            price = get_effective_price(
                campaign_id, inv_id, float(dyn_price or 0)
            )
            eff_stock = get_effective_stock(
                campaign_id, inv_id, int(raw_stock or 0)
            )
        else:
            price = float(dyn_price or 0)
            eff_stock = int(raw_stock or 0)
        items_by_shop.setdefault(shop_id, []).append({
            "item_id": it_id,
            "name": it_name,
            "type": it_type,
            "rarity": it_rarity,
            "price": price,
            "stock": eff_stock,
        })

    city_browse = []
    for city in sorted(cities, key=lambda c: (c.name or "").lower()):
        shops_in_city = sorted(
            [s for s in shops if any(cc.city_id == city.city_id for cc in s.cities)],
            key=lambda s: (s.name or "").lower(),
        )
        shop_entries = [
            {"shop": shop, "item_rows": items_by_shop.get(shop.shop_id, [])}
            for shop in shops_in_city
        ]
        city_browse.append(
            {
                "city": city,
                "shops": shop_entries,
                "region_label": _city_region_label(city),
            }
        )

    region_labels = sorted(
        {row["region_label"] for row in city_browse},
        key=lambda s: (s or "").lower(),
    )
    campaign_regions = []
    if _region_table_exists() and campaign_id is not None:
        campaign_regions = (
            Region.query.filter_by(campaign_id=campaign_id)
            .order_by(Region.name)
            .all()
        )

    # Player_Home.html references a `character` context var (name/class_name/
    # level/equipment_slots), a `player_name` header string, and a
    # `player_currency` value. Both the h1 header and the character panel
    # h2 must reflect the saved character sheet, so we route through
    # ``character_sheet_service.build_character_view`` — the same service
    # that powers /player/character — instead of hardcoding username. That
    # keeps Player_Home.html and Player_Character_Sheet.html rendering
    # against a single shape, including the user-editable ``name`` field
    # that lives in sheet_json (username is only the fallback).
    #
    # The template iterates `character.equipment_slots` expecting each
    # entry to expose `.slot_name` and `.item` (with `.name`/`.type`).
    # The PlayerEquipment ORM column is `.slot`, so normalize into
    # SimpleNamespace rows before handing them to the view builder.
    equipment_slot_views = [
        SimpleNamespace(slot_name=eq.slot, item=eq.item)
        for eq in (player.equipment_slots or [])
    ]
    character_ctx = character_sheet_service.build_character_view(
        player,
        active_campaign,
        equipment_slots=equipment_slot_views,
    )
    display_name = character_ctx.name
    from app.models import BattleEncounter
    from app.services.rulesets import get_ruleset

    combat_enabled = get_ruleset(active_campaign.system_type).system_type == "dnd5e"
    battle_encounter = None
    visible_battle_encounters = []
    battle_own_player_ids = []
    if combat_enabled:
        battle_own_player_ids = [
            p.id
            for p in Player.query.filter_by(
                user_id=current_user.id,
                campaign_id=campaign_id,
                is_npc=False,
            ).all()
        ]
        visible_battle_encounters = (
            BattleEncounter.query.filter(
                BattleEncounter.campaign_id == campaign_id,
                BattleEncounter.status != "ended",
                BattleEncounter.visible_to_players.is_(True),
            )
            .order_by(BattleEncounter.id.desc())
            .all()
        )
        battle_encounter = visible_battle_encounters[0] if visible_battle_encounters else None

    return render_template(
        "Player_Home.html",
        player=player,
        player_name=display_name,
        player_currency=int(player.currency or 0),
        character=character_ctx,
        player_has_active_campaign=active_campaign is not None,
        player_join_code_reveal_url=url_for("player.reveal_player_join_code"),
        character_data_url=url_for("player.character_data"),
        combat_enabled=combat_enabled,
        battle_encounter=battle_encounter,
        visible_battle_encounters=visible_battle_encounters,
        battle_own_player_ids=battle_own_player_ids,
        cities=cities,
        shops=shops,
        items=shop_items,
        inventory_items=inventory_items,
        shop_items_by_shop=shop_items_by_shop,
        city_browse=city_browse,
        region_labels=region_labels,
        campaign_regions=campaign_regions,
    )

# Search route
@player_bp.route("/search")
@login_required
def search_item():
    try:
        player = get_active_player(current_user)
        if not player:
            return jsonify({'error': 'Player not found'}), 404
        if player.campaign_id is None:
            return jsonify({'error': 'Join a campaign to search the market.'}), 403

        campaign_id = player.campaign_id

        city_id = request.args.get("city")
        shop_id = request.args.get("shop")
        item_id = request.args.get("item")

        query = (
            db.session.query(
                Item.name.label("item_name"),
                Shop.name.label("shop_name"),
                City.name.label("city_name"),
                Shop.shop_id,
                Item.item_id,
                ShopInventory.stock,
                ShopInventory.dynamic_price,
                ShopInventory.inventory_id,
            )
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .join(Shop, ShopInventory.shop_id == Shop.shop_id)
            .join(shop_cities, Shop.shop_id == shop_cities.c.shop_id)
            .join(City, shop_cities.c.city_id == City.city_id)
            .filter(
                Shop.campaign_id == campaign_id,
                Item.campaign_id == campaign_id,
            )
        )

        if city_id:
            query = query.filter(City.city_id == city_id)
        if shop_id:
            query = query.filter(Shop.shop_id == shop_id)
        if item_id:
            query = query.filter(Item.item_id == item_id)

        results = query.all()

        formatted_results = []
        for result in results:
            inv_id = result.inventory_id
            price = (
                get_effective_price(campaign_id, inv_id, float(result.dynamic_price))
                if READ_PRICES_FROM_WORLD_STATE
                else float(result.dynamic_price)
            )
            stock = (
                get_effective_stock(campaign_id, inv_id, int(result.stock))
                if READ_PRICES_FROM_WORLD_STATE
                else int(result.stock)
            )
            formatted_results.append(
                {
                    "item_name": result.item_name,
                    "shop_name": result.shop_name,
                    "city_name": result.city_name,
                    "shop_id": result.shop_id,
                    "item_id": result.item_id,
                    "stock": stock,
                    "price": price,
                }
            )

        return jsonify(formatted_results)

    except Exception as e:
        print(f"[ERROR] Error in search: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return jsonify({'error': 'An error occurred while searching'}), 500

@player_bp.route("/shop/<int:shop_id>/buy/<int:item_id>", methods=['POST'])
@login_required
def buy_item(shop_id, item_id):
    try:
        player = get_active_player(current_user)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'})
        if player.campaign_id is None:
            return jsonify(
                {'success': False, 'message': 'Join a campaign before purchasing.'}
            )

        campaign_id = player.campaign_id
        campaign = Campaign.query.filter_by(id=campaign_id).first()
        if not campaign:
            return jsonify({'success': False, 'message': 'Campaign not found'})

        shop = Shop.query.filter_by(
            shop_id=shop_id, campaign_id=campaign_id
        ).first()
        if not shop:
            return jsonify({'success': False, 'message': 'You do not have access to this shop'})

        inventory = ShopInventory.query.filter_by(
            shop_id=shop_id, item_id=item_id, campaign_id=campaign_id
        ).first()
        if not inventory:
            return jsonify({'success': False, 'message': 'Item not found in shop'})

        quantity = int(request.form.get('quantity', 1))
        if quantity <= 0:
            return jsonify({'success': False, 'message': 'Invalid quantity'})

        unit_price = get_effective_price(
            campaign_id,
            inventory.inventory_id,
            float(inventory.dynamic_price),
        )
        effective_stock = get_effective_stock(
            campaign_id,
            inventory.inventory_id,
            int(inventory.stock),
        )

        # Check if item is in stock
        if effective_stock < quantity:
            return jsonify({'success': False, 'message': 'Not enough items in stock'})

        # Process the purchase
        total_cost = unit_price * quantity
        if (
            not bool(getattr(campaign, "allow_player_debt", False))
            and (player.currency or 0) - total_cost < 0
        ):
            return jsonify({
                'success': False,
                'error_code': 'would_overdraft',
                'message': 'This purchase will bring you below 0 Credits.',
                'new_currency': player.currency,
            })

        player.currency -= total_cost
        inventory.stock -= quantity

        # Add item to player's inventory
        player_inventory = PlayerInventory.query.filter_by(
            player_id=player.id,
            item_id=item_id
        ).first()

        if player_inventory:
            # Update existing inventory entry
            player_inventory.quantity += quantity
        else:
            # Create new inventory entry
            player_inventory = PlayerInventory(
                player_id=player.id,
                item_id=item_id,
                quantity=quantity
            )
            db.session.add(player_inventory)

        db.session.commit()
        return jsonify({
            'success': True, 
            'message': f'Successfully purchased {quantity} {inventory.item.name}',
            'new_currency': player.currency
        })

    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Error buying item: {e}")
        return jsonify({'success': False, 'message': 'An error occurred while processing your purchase'})

@player_bp.route("/shop/<int:shop_id>/items")
@login_required
def view_shop_items(shop_id):
    try:
        player = get_active_player(current_user)
        if not player:
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))
        if player.campaign_id is None:
            return _redirect_solo_vault_to_character()

        campaign_id = player.campaign_id

        shop = Shop.query.filter_by(
            shop_id=shop_id, campaign_id=campaign_id
        ).first()
        if not shop:
            flash('You do not have access to this shop.', 'error')
            return redirect(url_for('player.player_home'))

        inventory = (
            db.session.query(ShopInventory)
            .filter_by(shop_id=shop_id, campaign_id=campaign_id)
            .options(db.joinedload(ShopInventory.item))
            .all()
        )

        print(f"Shop: {shop.name}, Found {len(inventory)} inventory items.")

        # Debug individual inventory entries
        for entry in inventory:
            print(f"Inventory Entry -> Item ID: {entry.item_id}, Stock: {entry.stock}, Price: {entry.dynamic_price}")
            print(f"Linked Item -> Name: {entry.item.name if entry.item else 'None'}")

        return render_template('Player_view_shop_items.html', shop=shop, inventory=inventory, player_currency=player.currency)
    except Exception as e:
        print(f"[ERROR] Error viewing shop items: {e}")
        flash('An error occurred while viewing shop items.', 'error')
        return redirect(url_for('player.player_home'))

@player_bp.route("/sell/<int:item_id>", methods=['POST'])
@login_required
def sell_item(item_id):
    try:
        player = get_active_player(current_user)
        if not player:
            return _ajax_or_redirect('Player profile not found.', error=True)
        if player.campaign_id is None:
            return _ajax_or_redirect(
                'Join a campaign before selling items.', error=True
            )

        item = Item.query.filter_by(
            item_id=item_id, campaign_id=player.campaign_id
        ).first()
        if not item:
            return _ajax_or_redirect('You do not have access to this item.', error=True)

        # Get the quantity to sell from the form
        quantity = int(request.form.get('quantity', 1))
        if quantity <= 0:
            return _ajax_or_redirect('Invalid quantity to sell.', error=True)

        # Get the player's inventory entry for this item
        player_inventory = PlayerInventory.query.filter_by(
            player_id=player.id,
            item_id=item_id
        ).first()

        if not player_inventory or player_inventory.quantity < quantity:
            return _ajax_or_redirect('You do not have enough of this item to sell.', error=True)

        # Calculate sell price (50-75% of base price)
        sell_price = int(item.base_price * 0.75)
        total_value = sell_price * quantity

        # Update inventory and currency
        player_inventory.quantity -= quantity
        player.currency += total_value

        if player_inventory.quantity <= 0:
            # Clear any equipment slot still pointing at an item the player no
            # longer owns, otherwise the dashboard body-model and equipment
            # list keep rendering a phantom equipped item after a full sell.
            stale_slots = PlayerEquipment.query.filter_by(
                player_id=player.id, item_id=item_id
            ).all()
            for eq in stale_slots:
                eq.item_id = None
            db.session.delete(player_inventory)

        db.session.commit()

        return _ajax_or_redirect(
            f'Successfully sold {quantity} {item.name} for {total_value} gold!',
            success=True,
            extra={'new_currency': player.currency},
        )

    except Exception as e:
        print(f"[ERROR] Error selling item: {e}")
        db.session.rollback()
        return _ajax_or_redirect('An error occurred while selling the item.', error=True)

def _ajax_or_redirect(message, success=False, error=False, extra=None):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        payload = {
            'status': 'success' if success else 'error',
            'message': message,
        }
        if extra:
            payload.update(extra)
        return jsonify(payload), 200 if success else 400

    # Fallback for normal HTML forms (kept for non-JS callers).
    flash(message, 'success' if success else 'error')
    return redirect(request.referrer or url_for('player.player_home'))

@player_bp.route("/market")
@login_required
def view_market():
    """Retired market stub — browse shops from the player dashboard."""
    return redirect(url_for("player.player_home"))

@player_bp.route("/api/market-data")
@login_required
def get_market_data():
    try:
        player = get_active_player(current_user)
        if not player:
            return jsonify({'error': 'Player not found'}), 404
        if player.campaign_id is None:
            return jsonify({'error': 'Join a campaign to view market data.'}), 403

        filter_type = request.args.get('filter', 'all')
        campaign_id = player.campaign_id

        items_query = (
            db.session.query(
                Item,
                db.func.sum(ShopInventory.stock).label('total_stock'),
                db.func.avg(ShopInventory.dynamic_price).label('avg_price')
            )
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .join(Shop, Shop.shop_id == ShopInventory.shop_id)
            .filter(Shop.campaign_id == campaign_id)
        )

        if filter_type != 'all':
            items_query = items_query.filter(Item.type == filter_type)

        items_query = (
            items_query.group_by(Item.item_id)
            .order_by(Item.name)
        )

        market_items = []
        for item, total_stock, avg_price in items_query.all():
            # Calculate buy/sell orders (simplified example)
            sell_orders = total_stock
            buy_orders = int(total_stock * 1.2)  # Example: 20% more buy orders than stock
            
            # Calculate price trend (simplified example)
            base_price_diff = ((avg_price or item.base_price) - item.base_price) / item.base_price * 100
            
            market_items.append({
                'name': item.name,
                'icon': f"{item.type.lower()}/{item.name.lower().replace(' ', '_')}.png",
                'sellOrders': sell_orders,
                'buyOrders': buy_orders,
                'price': float(avg_price or item.base_price),
                'trend': round(base_price_diff, 1),
                'productionSources': [
                    "Rye Farms",
                    "Wheat Farms",
                    "Rice Farms"
                ] if item.type == 'Agricultural' else [
                    "Factories",
                    "Workshops"
                ],
                'priceHistory': {
                    'dates': ['Jan 1', 'Jan 15', 'Feb 1', 'Feb 15', 'Mar 1'],
                    'prices': [
                        item.base_price * 0.9,
                        item.base_price * 0.95,
                        item.base_price,
                        item.base_price * 1.1,
                        float(avg_price or item.base_price)
                    ]
                }
            })

        return jsonify({
            'items': market_items
        })
    except Exception as e:
        print(f"[ERROR] Error fetching market data: {e}")
        return jsonify({'error': str(e)}), 500


def _active_campaign_player_for_json():
    player = get_active_player(current_user)
    if not player:
        return None, (jsonify({"error": "Player not found."}), 404)
    if player.campaign_id is None:
        return None, (jsonify({"error": "Join a campaign to view this data."}), 403)
    return player, None


@player_bp.route("/maps/world", methods=["GET"])
@login_required
def player_world_map():
    player, err = _active_campaign_player_for_json()
    if err:
        return err
    from app.services import gm_maps

    payload = gm_maps.build_world_map_payload(player.campaign_id, for_player=True)
    db.session.commit()  # canvas may be lazily created by the read builder
    return jsonify(payload)


@player_bp.route("/maps/cities/<int:city_id>", methods=["GET"])
@login_required
def player_city_map(city_id):
    player, err = _active_campaign_player_for_json()
    if err:
        return err
    city = City.query.filter_by(city_id=city_id, campaign_id=player.campaign_id).first()
    if city is None:
        return jsonify({"error": "City not found in this campaign."}), 404
    from app.services import gm_maps

    payload = gm_maps.build_city_map_payload(player.campaign_id, city, for_player=True)
    db.session.commit()
    return jsonify(payload)


@player_bp.route("/maps/image/<int:canvas_id>", methods=["GET"])
@login_required
def player_map_image(canvas_id):
    player, err = _active_campaign_player_for_json()
    if err:
        return err
    canvas = MapCanvas.query.filter_by(
        id=canvas_id,
        campaign_id=player.campaign_id,
    ).first()
    if canvas is None or not canvas.image_path:
        return jsonify({"error": "Map image not found."}), 404
    from app.services import gm_maps

    path = gm_maps.map_image_file(canvas.id)
    if not path.exists():
        return jsonify({"error": "Map image not found."}), 404
    return send_file(io.BytesIO(path.read_bytes()), mimetype="image/webp", max_age=0)


@player_bp.route("/api/market-overview", methods=["GET"])
@login_required
def player_market_overview():
    player, err = _active_campaign_player_for_json()
    if err:
        return err
    from app.services.market_overview import build_market_overview_payload

    return jsonify(build_market_overview_payload(player.campaign_id))


def _slot_for_item_type(item_type: str) -> str:
    # Map Item.type onto one of the three equipment slots the game supports.
    # Unknown/consumable/utility types fall back to "accessory" so players can
    # still equip generic items (e.g. Bag of Holding) without the UI having to
    # offer a slot picker.
    t = (item_type or "").strip().lower()
    if "weapon" in t or "sword" in t or "bow" in t or "staff" in t or "axe" in t or "gun" in t:
        return "weapon"
    if "armor" in t or "armour" in t or "shield" in t:
        return "armor"
    return "accessory"


def _active_campaign_for_player(player):
    """Resolve the Campaign the player's character is bound to.

    With the campaign-tenancy refactor each character (`Player`) has at
    most one campaign via ``Player.campaign_id``. ``None`` means a solo
    vault character with no campaign attached.
    """
    if player is None or player.campaign_id is None:
        return None
    return player.campaign


@player_bp.route("/character/create", methods=["GET", "POST"])
@login_required
def create_character():
    """Render the character-creation form (GET) or provision a new character (POST).

    D&D 5e uses a multi-step wizard finalized via JSON; other rulesets keep the
    one-screen instant create flow.
    """
    import secrets

    from app.services.rulesets import get_ruleset, known_system_types
    from app.services.user_capabilities import has_player_capability
    from app.services.character_creation.creation_service import wizard_catalog_for_user

    if not has_player_capability(current_user):
        return redirect(url_for("main.campaigns"))

    valid_systems = list(known_system_types())
    system_options = [
        {"value": st, "label": get_ruleset(st).display_name}
        for st in valid_systems
    ]
    default_system = "dnd5e" if "dnd5e" in valid_systems else valid_systems[0]

    if request.method == "GET":
        campaign_player = None
        campaign_id = None
        raw_campaign_player_id = (request.args.get("campaign_player_id") or "").strip()
        if raw_campaign_player_id:
            try:
                campaign_player = get_character_for_user(
                    current_user, int(raw_campaign_player_id)
                )
            except (TypeError, ValueError):
                campaign_player = None
            if campaign_player is not None and campaign_player.campaign_id is not None:
                campaign_id = campaign_player.campaign_id
        ok, msg = can_add_player_profile(current_user)
        if campaign_id is not None:
            from app.services.character_creation.campaign_settings import (
                get_character_options,
            )
            from app.services.species_compendium_service import ensure_species_compendium

            wizard_payload = wizard_catalog_for_user(
                campaign_id=campaign_id,
                species_compendium=ensure_species_compendium(campaign_id),
                character_options=get_character_options(campaign_id),
            )
            ok = True
            msg = ""
            wizard_payload["campaign_player_id"] = campaign_player.id
        else:
            wizard_payload = wizard_catalog_for_user()
        wizard_payload["default_system"] = default_system
        wizard_payload["can_add"] = ok
        wizard_payload["back_url"] = url_for("main.campaigns")
        wizard_payload["draft_token"] = secrets.token_urlsafe(16)
        return render_template(
            "Player_Create_Character.html",
            systems=system_options,
            default_system=default_system,
            can_add=ok,
            cap_message=msg or "",
            wizard_config=wizard_payload,
        )

    ok, msg = can_add_player_profile(current_user)
    if not ok:
        flash(
            msg or "You have reached your character profile limit on this plan.",
            "warning",
        )
        return redirect(url_for("player.list_characters"))

    raw_system = (request.form.get("system_type") or "").strip().lower()
    if raw_system not in valid_systems:
        flash("Pick a valid rule system.", "warning")
        return redirect(url_for("player.create_character"))
    raw_name = (request.form.get("name") or "").strip()
    if len(raw_name) > 100:
        raw_name = raw_name[:100]

    new_player = Player(
        user_id=current_user.id,
        campaign_id=None,
        currency=0,
        is_npc=False,
    )
    db.session.add(new_player)
    try:
        db.session.flush()
        character_sheet_service.create_initial_vault_sheet(
            new_player.id,
            system_type=raw_system,
            name=raw_name or None,
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f"Could not create a new character: {exc}", "error")
        return redirect(url_for("player.list_characters"))

    return redirect(
        url_for("player.character_dashboard", player_id=new_player.id)
    )


@player_bp.route("/character/create/dnd5e/roll", methods=["POST"])
@login_required
@limiter.limit("120 per hour")
def create_character_dnd5e_roll():
    from app.services.character_creation.creation_service import (
        CreationValidationError,
        get_roll_draft,
        issue_random_roll,
        wizard_catalog_for_user,
    )

    payload = request.get_json(silent=True) or {}
    ability_key = payload.get("ability_key")
    reroll = bool(payload.get("reroll"))
    try:
        campaign_scope = None
        raw_campaign_player_id = payload.get("campaign_player_id")
        if raw_campaign_player_id:
            player = get_character_for_user(current_user, int(raw_campaign_player_id))
            if player is None or player.campaign_id is None:
                raise CreationValidationError("Campaign character not found.")
            campaign_scope = player.campaign_id
            from app.services.character_creation.campaign_settings import (
                get_creation_settings,
            )

            ctx = {"settings": get_creation_settings(campaign_scope)}
        else:
            ctx = wizard_catalog_for_user()
        result = issue_random_roll(
            session,
            user_id=current_user.id,
            settings=ctx["settings"],
            campaign_scope=campaign_scope,
            ability_key=str(ability_key or ""),
            reroll=reroll,
        )
        return jsonify({"ok": True, "roll": result, "draft": get_roll_draft(session, current_user.id)})
    except CreationValidationError as exc:
        return jsonify({"ok": False, "errors": [str(exc)]}), 400


@player_bp.route("/character/create/dnd5e/finalize", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def create_character_dnd5e_finalize():
    from app.services.character_creation.creation_service import (
        CreationValidationError,
        clear_roll_draft,
        finalize_vault_character,
        get_finalize_result,
        get_roll_draft,
        store_finalize_result,
    )

    payload = request.get_json(silent=True) or {}
    draft_token = str(payload.get("draft_token") or "").strip()
    existing = get_finalize_result(session, current_user.id)
    raw_campaign_player_id = payload.get("campaign_player_id")
    campaign_player = None
    campaign_id = None
    if raw_campaign_player_id:
        try:
            campaign_player = get_character_for_user(
                current_user, int(raw_campaign_player_id)
            )
        except (TypeError, ValueError):
            campaign_player = None
        if campaign_player is None or campaign_player.campaign_id is None:
            return jsonify({"ok": False, "errors": ["Campaign character not found."]}), 404
        campaign_id = campaign_player.campaign_id

    ok_cap, cap_msg = can_add_player_profile(current_user)
    if campaign_player is None and not ok_cap and not (
        existing and existing.get("draft_token") == draft_token and draft_token
    ):
        return jsonify({"ok": False, "errors": [cap_msg or "Character profile limit reached."]}), 403

    try:
        if campaign_player is not None:
            from app.models import PlayerCharacterSheet
            from app.services.character_creation.campaign_settings import (
                get_character_options,
                get_creation_settings,
            )
            from app.services.character_creation.creation_service import (
                build_final_sheet_json,
                wizard_catalog_for_user,
            )
            from app.services.species_compendium_service import ensure_species_compendium

            ctx = wizard_catalog_for_user(
                campaign_id=campaign_id,
                species_compendium=ensure_species_compendium(campaign_id),
                character_options=get_character_options(campaign_id),
            )
            sheet_json = build_final_sheet_json(
                payload,
                catalog=ctx["catalog"],
                settings=get_creation_settings(campaign_id),
                roll_draft=get_roll_draft(session, current_user.id),
            )
            row = PlayerCharacterSheet.query.filter_by(
                player_id=campaign_player.id,
                campaign_id=campaign_id,
            ).first()
            if row is None:
                row = PlayerCharacterSheet(
                    player_id=campaign_player.id,
                    campaign_id=campaign_id,
                    sheet_json=sheet_json,
                )
                db.session.add(row)
            else:
                row.sheet_json = sheet_json
            db.session.commit()
            player = campaign_player
            clear_roll_draft(session)
        else:
            player, sheet_json = finalize_vault_character(
                current_user.id,
                payload,
                campaign_id=None,
                roll_draft=get_roll_draft(session, current_user.id),
                draft_token=draft_token or None,
                existing_finalize=existing,
            )
            if not (existing and existing.get("draft_token") == draft_token and draft_token):
                db.session.commit()
                store_finalize_result(
                    session,
                    user_id=current_user.id,
                    player_id=player.id,
                    draft_token=draft_token,
                )
                clear_roll_draft(session)
        return jsonify(
            {
                "ok": True,
                "player_id": player.id,
                "redirect_url": url_for(
                    "player.character_dashboard", player_id=player.id
                ),
                "sheet": sheet_json,
            }
        )
    except CreationValidationError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "errors": [str(exc)]}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"ok": False, "errors": [f"Could not create character: {exc}"]}), 500


@player_bp.route("/characters")
@login_required
def list_characters():
    """Picker / index for all characters this user owns (solo + per-campaign)."""
    from app.services.user_capabilities import has_player_capability

    if not has_player_capability(current_user):
        return redirect(url_for("main.campaigns"))

    characters = list_user_characters(current_user)
    rows = []
    for p in characters:
        sheet = character_sheet_service.get_or_default_sheet(
            p, _active_campaign_for_player(p)
        )
        rows.append(
            {
                "id": p.id,
                "name": (sheet.get("name") or "").strip()
                or f"Character #{p.id}",
                "system_type": sheet.get("system_type") or "generic",
                "level": sheet.get("level"),
                "is_solo": p.campaign_id is None,
            }
        )

    can_add, cap_msg = can_add_player_profile(current_user)
    return render_template(
        "Player_characters_list.html",
        characters=rows,
        can_add=can_add,
        cap_message=cap_msg or "",
    )


@player_bp.route("/character")
@login_required
def view_character():
    """Backwards-compatible entry point: pick a sensible character or list them."""
    from app.services.user_capabilities import has_player_capability

    if not has_player_capability(current_user):
        return redirect(url_for("main.campaigns"))

    characters = list_user_characters(current_user)
    if not characters:
        ensure_solo_player_profile(current_user)
        characters = list_user_characters(current_user)
    if len(characters) == 1:
        return redirect(
            url_for("player.view_character_id", player_id=characters[0].id)
        )
    return redirect(url_for("player.list_characters"))


@player_bp.route("/character/<int:player_id>")
@login_required
def view_character_id(player_id):
    player = get_character_for_user(current_user, player_id)
    if not player:
        flash("Character not found.", "warning")
        return redirect(url_for("player.list_characters"))

    equipment_slot_views = [
        SimpleNamespace(slot_name=eq.slot, item=eq.item)
        for eq in (player.equipment_slots or [])
    ]

    campaign = _active_campaign_for_player(player)
    character_ctx = character_sheet_service.build_character_view(
        player,
        campaign,
        equipment_slots=equipment_slot_views,
    )
    return render_template("Player_Character_Sheet.html", character=character_ctx)


@player_bp.route("/character/<int:player_id>/dashboard")
@login_required
def character_dashboard(player_id):
    player = get_character_for_user(current_user, player_id)
    if not player:
        flash("Character not found.", "warning")
        return redirect(url_for("player.list_characters"))
    if player.campaign_id is None:
        return _render_solo_character_dashboard(player)

    active_campaign = _active_campaign_for_player(player)
    if active_campaign is not None:
        session["campaign_id"] = active_campaign.id
        session["system_type"] = active_campaign.system_type
        session.permanent = True
        session.modified = True
        return redirect(url_for("player.player_home"))

    flash("That character is not assigned to an active campaign.", "warning")
    return redirect(url_for("player.view_character_id", player_id=player.id))


@player_bp.route("/character/<int:player_id>/update", methods=["POST"])
@login_required
def update_character(player_id):
    player = get_character_for_user(current_user, player_id)
    if not player:
        flash("Character not found.", "warning")
        return redirect(url_for("player.list_characters"))

    campaign = _active_campaign_for_player(player)
    ok, errors = character_sheet_service.apply_sheet_update(
        player, campaign, request.form
    )
    if ok:
        flash("Character sheet saved.", "success")
        # Drop back to the dashboard on a clean save (matches the
        # "Back to Dashboard" link in the sheet template). On validation
        # or DB failure we keep the player on the sheet so the flashed
        # error sits next to the form they were editing.
        return redirect(
            url_for("player.character_dashboard", player_id=player.id)
        )
    for msg in errors or ["Failed to save character sheet."]:
        flash(msg, "error")
    return redirect(url_for("player.view_character_id", player_id=player.id))


@player_bp.route("/character/<int:player_id>/delete", methods=["POST"])
@login_required
def delete_character(player_id):
    """Delete a solo (campaign-less) character owned by the current user.

    Refuses to touch a Player whose ``campaign_id`` is not None: that
    character has joined a campaign and belongs to the GM's workflow, not
    a self-service player delete. PlayerInventory and PlayerCharacterSheet
    have no FK ON DELETE CASCADE, so we clear them explicitly before
    SQLAlchemy cascades equipment via the relationship-level
    ``delete-orphan`` rules on ``Player``.
    """
    player = get_character_for_user(current_user, player_id)
    if not player:
        flash("Character not found.", "warning")
        return redirect(url_for("player.list_characters"))

    if player.campaign_id is not None:
        flash(
            "This character is in a campaign. Ask the GM to remove you, or "
            "leave the campaign first.",
            "warning",
        )
        return redirect(url_for("player.list_characters"))

    try:
        PlayerCharacterSheet.query.filter_by(player_id=player.id).delete(
            synchronize_session=False
        )
        PlayerInventory.query.filter_by(player_id=player.id).delete(
            synchronize_session=False
        )
        db.session.delete(player)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f"Could not delete character: {exc}", "error")
        return redirect(url_for("player.list_characters"))

    flash("Character deleted.", "success")
    return redirect(request.referrer or url_for("player.list_characters"))


@player_bp.route("/equip/<int:item_id>", methods=["POST"])
@login_required
def equip_item(item_id):
    try:
        player = get_active_player(current_user)
        if not player:
            flash("Player profile not found.", "error")
            return redirect(url_for("player.player_home"))
        if player.campaign_id is None:
            flash("Join a campaign before equipping gear.", "warning")
            return redirect(url_for("player.list_characters"))

        item = Item.query.filter_by(
            item_id=item_id, campaign_id=player.campaign_id
        ).first()
        if not item:
            flash("Item not found in your campaign.", "error")
            return redirect(url_for("player.player_home"))

        inv = PlayerInventory.query.filter_by(
            player_id=player.id, item_id=item_id
        ).first()
        if not inv or (inv.quantity or 0) <= 0:
            flash("You do not own that item.", "error")
            return redirect(url_for("player.player_home"))

        slot = _slot_for_item_type(item.type)
        eq = PlayerEquipment.query.filter_by(
            player_id=player.id, slot=slot
        ).first()
        if eq:
            eq.item_id = item.item_id
            eq.source = None  # player-initiated (GM-initiated rows are tagged "GM")
        else:
            db.session.add(
                PlayerEquipment(
                    player_id=player.id,
                    slot=slot,
                    item_id=item.item_id,
                    source=None,
                )
            )
        db.session.commit()
        flash(f"Equipped {item.name} to {slot}.", "success")
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Error equipping item: {e}")
        flash("An error occurred while equipping the item.", "error")

    return redirect(request.referrer or url_for("player.player_home"))


@player_bp.route("/unequip/<string:slot_name>", methods=["POST"])
@login_required
def unequip_item(slot_name):
    try:
        player = get_active_player(current_user)
        if not player:
            flash("Player profile not found.", "error")
            return redirect(url_for("player.player_home"))

        slot = (slot_name or "").strip().lower()
        if slot not in EQUIPMENT_SLOTS:
            flash("Invalid equipment slot.", "error")
            return redirect(url_for("player.player_home"))

        eq = PlayerEquipment.query.filter_by(
            player_id=player.id, slot=slot
        ).first()
        if eq and eq.item_id is not None:
            eq.item_id = None
            db.session.commit()
            flash(f"Unequipped {slot}.", "success")
        else:
            # Idempotent: already empty -> silent no-op is fine UX-wise, but
            # surface a neutral message so the click visibly "did" something.
            flash(f"{slot.title()} slot was already empty.", "info")
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Error unequipping slot: {e}")
        flash("An error occurred while unequipping.", "error")

    return redirect(request.referrer or url_for("player.player_home"))


@player_bp.route("/character-data")
@login_required
def character_data():
    # Feeds loadCharacterData() in Player_Home.html. Populated from the
    # PlayerCharacterSheet row scoped to (player, active campaign) via the
    # character_sheet_service. The rule-set registry drives which keys are
    # surfaced (dnd5e -> 18 skills + 6 saves; pf2e -> 16 skills + 3 saves;
    # generic -> abilities + HP only). equipment_slots comes from the real
    # PlayerEquipment rows so the body-model SVG highlights and tooltips in
    # Player_Home.html keep rendering as before.
    try:
        player = get_active_player(current_user)
        if not player:
            return jsonify({'error': 'Player not found'}), 404

        slot_rows = (
            db.session.query(PlayerEquipment, Item)
            .outerjoin(Item, Item.item_id == PlayerEquipment.item_id)
            .filter(PlayerEquipment.player_id == player.id)
            .all()
        )

        equipment_slots = []
        for eq, item in slot_rows:
            slot_payload = {
                "slot_name": eq.slot,
                "item": None,
            }
            if item is not None and eq.item_id is not None:
                desc = item.description or ""
                slot_payload["item"] = {
                    "id": item.item_id,
                    "name": item.name,
                    "rarity": item.rarity,
                    "description_short": (desc[:140] + "…") if len(desc) > 140 else desc,
                }
            equipment_slots.append(slot_payload)

        campaign = _active_campaign_for_player(player)
        payload = character_sheet_service.character_data_payload(
            player, campaign, equipment_slots=equipment_slots
        )
        return jsonify(payload)
    except Exception as e:
        print(f"[ERROR] Error fetching character data: {e}")
        return jsonify({'error': str(e)}), 500


@player_bp.route("/character/<int:player_id>/data")
@login_required
def character_data_id(player_id):
    try:
        player = get_character_for_user(current_user, player_id)
        if not player:
            return jsonify({"error": "Character not found"}), 404

        slot_rows = (
            db.session.query(PlayerEquipment, Item)
            .outerjoin(Item, Item.item_id == PlayerEquipment.item_id)
            .filter(PlayerEquipment.player_id == player.id)
            .all()
        )

        equipment_slots = []
        for eq, item in slot_rows:
            slot_payload = {
                "slot_name": eq.slot,
                "item": None,
            }
            if item is not None and eq.item_id is not None:
                desc = item.description or ""
                slot_payload["item"] = {
                    "id": item.item_id,
                    "name": item.name,
                    "rarity": item.rarity,
                    "description_short": (desc[:140] + "...") if len(desc) > 140 else desc,
                }
            equipment_slots.append(slot_payload)

        campaign = _active_campaign_for_player(player)
        payload = character_sheet_service.character_data_payload(
            player, campaign, equipment_slots=equipment_slots
        )
        return jsonify(payload)
    except Exception as e:
        print(f"[ERROR] Error fetching character data: {e}")
        return jsonify({"error": str(e)}), 500
