from types import SimpleNamespace

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app.models import (
    Player,
    City,
    Shop,
    ShopInventory,
    Item,
    PlayerInventory,
    PlayerEquipment,
    Campaign,
    CampaignPlayer,
    shop_cities,
)

EQUIPMENT_SLOTS = ("weapon", "armor", "accessory")
from flask_login import login_required, current_user
from app.extensions import db
from app.constants.simulation_flags import READ_PRICES_FROM_WORLD_STATE
from app.services.world_state_reads import get_effective_price, get_effective_stock
from app.services import character_sheet_service

player_bp = Blueprint("player", __name__)

@player_bp.before_request
def before_request():
    print(f"[DEBUG] Player Blueprint - Request URL: {request.url}")
    print(f"[DEBUG] Player Blueprint - Request Method: {request.method}")
    print(f"[DEBUG] Player Blueprint - Current User: {current_user.username if current_user.is_authenticated else 'Not authenticated'}")

# Shop routes first (more specific)
@player_bp.route("/shop/<int:shop_id>")
@login_required
def view_shop(shop_id):
    try:
        print(f"[DEBUG] Attempting to view shop ID: {shop_id}")
        print(f"[DEBUG] Request URL: {request.url}")
        print(f"[DEBUG] Request Path: {request.path}")
        
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            print("[DEBUG] Player not found")
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        print(f"[DEBUG] Found player: {player.id}, GM Profile ID: {player.gm_profile_id}")

        # Scoped load: never resolve another campaign's shop by ID alone
        shop = (
            Shop.query.filter_by(shop_id=shop_id, gm_profile_id=player.gm_profile_id)
            .options(db.joinedload(Shop.cities))
            .first()
        )
        if not shop:
            print("[DEBUG] Shop not in player's campaign")
            flash('You do not have access to this shop.', 'error')
            return redirect(url_for('player.player_home'))
        print(f"[DEBUG] Found shop: {shop.name}, GM Profile ID: {shop.gm_profile_id}")

        # Get the city this shop belongs to
        city = shop.cities[0] if shop.cities else None
        if not city:
            print("[DEBUG] No city found for shop")
            flash('Shop location not found.', 'error')
            return redirect(url_for('player.player_home'))

        print(f"[DEBUG] Found city: {city.name}")

        # Get shop inventory with item details (inventory_id for optional world-state price overlay)
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
            .all()
        )
        if READ_PRICES_FROM_WORLD_STATE:
            shop_items = [
                SimpleNamespace(
                    name=r.name,
                    type=r.type,
                    stock=get_effective_stock(
                        player.gm_profile_id, r.inventory_id, int(r.stock)
                    ),
                    dynamic_price=get_effective_price(
                        player.gm_profile_id, r.inventory_id, float(r.dynamic_price)
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
@login_required
def view_shops():
    try:
        print("[DEBUG] Starting view_shops route")
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            print("[DEBUG] Player not found")
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        print(f"[DEBUG] Found player: {player.id}, GM Profile ID: {player.gm_profile_id}")

        # Get all shops for the player's GM with cities eagerly loaded
        shops = (
            Shop.query
            .filter_by(gm_profile_id=player.gm_profile_id)
            .options(db.joinedload(Shop.cities))
            .all()
        )
        
        print(f"[DEBUG] Found {len(shops)} shops")
        for shop in shops:
            print(f"[DEBUG] Shop: {shop.name} (ID: {shop.shop_id})")
            print(f"[DEBUG] Cities: {[city.name for city in shop.cities]}")
        
        return render_template('Player_view_shops.html', shops=shops)
    except Exception as e:
        print(f"[ERROR] Error viewing shops: {e}")
        flash('An error occurred while viewing shops.', 'error')
        return redirect(url_for('player.player_home'))

# City routes
@player_bp.route("/cities")
@login_required
def view_cities():
    try:
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        # Get all cities for the player's GM
        cities = City.query.filter_by(gm_profile_id=player.gm_profile_id).all()
        
        return render_template('Player_city_view.html', cities=cities)
    except Exception as e:
        print(f"[ERROR] Error viewing cities: {e}")
        flash('An error occurred while viewing cities.', 'error')
        return redirect(url_for('player.player_home'))

@player_bp.route("/cities/<int:city_id>")
@login_required
def view_city(city_id):
    try:
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        city = City.query.filter_by(
            city_id=city_id, gm_profile_id=player.gm_profile_id
        ).first()
        if not city:
            flash('You do not have access to this city.', 'error')
            return redirect(url_for('player.player_home'))

        # Get all shops in the city
        shops = city.shops

        return render_template('Player_city_view.html', city=city, shops=shops)
    except Exception as e:
        print(f"[ERROR] Error viewing city: {e}")
        flash('An error occurred while viewing the city.', 'error')
        return redirect(url_for('player.player_home'))

# Home route last (least specific)
@player_bp.route("/home")
@login_required
def player_home():
    print("[DEBUG] Starting player_home route")
    print(f"[DEBUG] Current user: {current_user.username}, Role: {current_user.role}")
    
    # Fetch player details
    player = Player.query.filter_by(user_id=current_user.id).first()
    if not player:
        print("[DEBUG] Player not found")
        return "Player not found", 404
    
    print(f"[DEBUG] Found player: {player.id}, User ID: {player.user_id}, GM Profile ID: {player.gm_profile_id}")

    # Verify GM profile exists
    gm_profile = player.gm_profile
    if not gm_profile:
        print("[DEBUG] GM Profile not found")
        return "GM Profile not found", 404
    
    print(f"[DEBUG] Found GM Profile: {gm_profile.id}, User ID: {gm_profile.user_id}")

    # Get all cities for the GM
    cities = City.query.filter_by(gm_profile_id=gm_profile.id).all()
    print(f"[DEBUG] Found {len(cities)} cities for GM Profile {gm_profile.id}")
    for city in cities:
        print(f"[DEBUG] City: {city.name} (ID: {city.city_id})")

    # Get all shops for the GM (eager-load cities so the city->shop->items
    # accordion rendered by Player_Home.html does not trigger N+1 lookups on
    # shop.cities during template iteration).
    shops = (
        Shop.query
        .filter_by(gm_profile_id=gm_profile.id)
        .options(db.joinedload(Shop.cities))
        .all()
    )
    print(f"[DEBUG] Found {len(shops)} shops for GM Profile {gm_profile.id}")
    for shop in shops:
        print(f"[DEBUG] Shop: {shop.name} (ID: {shop.shop_id})")

    # Get all items in shops for the GM.
    # NB: we cannot use SELECT DISTINCT directly on Item rows because
    # Item.preferred_regions is Postgres `json`, which has no equality operator
    # and breaks DISTINCT / UNION. Dedupe at the integer item_id layer via a
    # subquery instead; the items PK guarantees outer uniqueness.
    shop_items = (
        db.session.query(Item)
        .filter(
            Item.item_id.in_(
                db.session.query(ShopInventory.item_id)
                .join(Shop, Shop.shop_id == ShopInventory.shop_id)
                .filter(Shop.gm_profile_id == gm_profile.id)
            )
        )
        .all()
    )
    print(f"[DEBUG] Found {len(shop_items)} items in shops for GM Profile {gm_profile.id}")
    for item in shop_items:
        print(f"[DEBUG] Item: {item.name} (ID: {item.item_id})")

    # Build shop_id -> [{id,name,type,rarity}] for the client-side filter JS in
    # Player_Home.html (SHOP_ITEMS_BY_SHOP). Reuse `shop_items` as the Item
    # lookup so we do not re-select Item rows (which would re-expose the
    # preferred_regions `json` equality pitfall if ever DISTINCT-ed).
    inventory_pairs = (
        db.session.query(ShopInventory.shop_id, ShopInventory.item_id)
        .join(Shop, Shop.shop_id == ShopInventory.shop_id)
        .filter(Shop.gm_profile_id == gm_profile.id)
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
        .filter(Shop.gm_profile_id == gm_profile.id)
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
                gm_profile.id, inv_id, float(dyn_price or 0)
            )
            eff_stock = get_effective_stock(
                gm_profile.id, inv_id, int(raw_stock or 0)
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
        city_browse.append({"city": city, "shops": shop_entries})

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
    active_campaign = _active_campaign_for_player(player)
    character_ctx = character_sheet_service.build_character_view(
        player,
        active_campaign,
        equipment_slots=equipment_slot_views,
    )
    display_name = character_ctx.name

    return render_template(
        "Player_Home.html",
        player=player,
        player_name=display_name,
        player_currency=int(player.currency or 0),
        character=character_ctx,
        cities=cities,
        shops=shops,
        items=shop_items,
        inventory_items=inventory_items,
        shop_items_by_shop=shop_items_by_shop,
        city_browse=city_browse,
    )

# Search route
@player_bp.route("/search")
@login_required
def search_item():
    try:
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            return jsonify({'error': 'Player not found'}), 404

        print(f"[DEBUG] Searching for player: {player.id}, GM Profile ID: {player.gm_profile_id}")

        # Debug: Check available shops and items
        shops = Shop.query.filter_by(gm_profile_id=player.gm_profile_id).all()
        print(f"[DEBUG] Found {len(shops)} shops for GM Profile {player.gm_profile_id}")
        for shop in shops:
            print(f"[DEBUG] Shop: {shop.name} (ID: {shop.shop_id})")
            print(f"[DEBUG] Cities: {[city.name for city in shop.cities]}")

        items = Item.query.filter_by(gm_profile_id=player.gm_profile_id).all()
        print(f"[DEBUG] Found {len(items)} items in this campaign")
        for item in items:
            print(f"[DEBUG] Item: {item.name} (ID: {item.item_id})")

        # Get filter parameters
        city_id = request.args.get("city")
        shop_id = request.args.get("shop")
        item_id = request.args.get("item")

        print(f"[DEBUG] Search filters - City: {city_id}, Shop: {shop_id}, Item: {item_id}")

        # Base query
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
                Shop.gm_profile_id == player.gm_profile_id,
                Item.gm_profile_id == player.gm_profile_id,
            )
        )

        # Apply filters
        if city_id:
            query = query.filter(City.city_id == city_id)
        if shop_id:
            query = query.filter(Shop.shop_id == shop_id)
        if item_id:
            query = query.filter(Item.item_id == item_id)

        # Execute query
        results = query.all()
        print(f"[DEBUG] Found {len(results)} matching results")

        # Format results (optional world-state price/stock when READ_PRICES_FROM_WORLD_STATE)
        formatted_results = []
        for result in results:
            inv_id = result.inventory_id
            price = (
                get_effective_price(player.gm_profile_id, inv_id, float(result.dynamic_price))
                if READ_PRICES_FROM_WORLD_STATE
                else float(result.dynamic_price)
            )
            stock = (
                get_effective_stock(player.gm_profile_id, inv_id, int(result.stock))
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
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'})

        shop = Shop.query.filter_by(
            shop_id=shop_id, gm_profile_id=player.gm_profile_id
        ).first()
        if not shop:
            return jsonify({'success': False, 'message': 'You do not have access to this shop'})

        # Get the shop inventory item
        inventory = ShopInventory.query.filter_by(shop_id=shop_id, item_id=item_id).first()
        if not inventory:
            return jsonify({'success': False, 'message': 'Item not found in shop'})

        # Get quantity from request (default to 1 if not specified)
        quantity = int(request.form.get('quantity', 1))
        if quantity <= 0:
            return jsonify({'success': False, 'message': 'Invalid quantity'})

        unit_price = get_effective_price(
            player.gm_profile_id,
            inventory.inventory_id,
            float(inventory.dynamic_price),
        )
        effective_stock = get_effective_stock(
            player.gm_profile_id,
            inventory.inventory_id,
            int(inventory.stock),
        )

        # Check if item is in stock
        if effective_stock < quantity:
            return jsonify({'success': False, 'message': 'Not enough items in stock'})

        # Process the purchase
        total_cost = unit_price * quantity
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
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        shop = Shop.query.filter_by(
            shop_id=shop_id, gm_profile_id=player.gm_profile_id
        ).first()
        if not shop:
            flash('You do not have access to this shop.', 'error')
            return redirect(url_for('player.player_home'))

        # Query for inventory with item relationships
        inventory = db.session.query(ShopInventory).filter_by(shop_id=shop_id).options(
            db.joinedload(ShopInventory.item)
        ).all()

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
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            return _ajax_or_redirect('Player profile not found.', error=True)

        item = Item.query.filter_by(
            item_id=item_id, gm_profile_id=player.gm_profile_id
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
            success=True
        )

    except Exception as e:
        print(f"[ERROR] Error selling item: {e}")
        db.session.rollback()
        return _ajax_or_redirect('An error occurred while selling the item.', error=True)

def _ajax_or_redirect(message, success=False, error=False):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'success' if success else 'error',
            'message': message
        }), 200 if success else 400

    # Fallback for normal HTML forms
    flash(message, 'success' if success else 'error')
    return redirect(request.referrer or url_for('player.player_home'))

@player_bp.route("/market")
@login_required
def view_market():
    try:
        print("[DEBUG] Entered /player/market route")
        
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            print("[DEBUG] Player not found - redirecting to home")
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))
        
        print(f"[DEBUG] Found player: {player.id}, GM Profile ID: {player.gm_profile_id}")

        # Get all shops for the player's GM
        shops = Shop.query.filter_by(gm_profile_id=player.gm_profile_id).all()
        print(f"[DEBUG] Found {len(shops)} shops for player's GM")

        # See player_home() — DISTINCT on Item breaks because preferred_regions
        # is Postgres `json`. Dedupe via a subquery on the integer item_id.
        items = (
            db.session.query(Item)
            .filter(
                Item.item_id.in_(
                    db.session.query(ShopInventory.item_id)
                    .join(Shop, Shop.shop_id == ShopInventory.shop_id)
                    .filter(Shop.gm_profile_id == player.gm_profile_id)
                )
            )
            .all()
        )
        print(f"[DEBUG] Found {len(items)} items in shops")

        return render_template(
            'Player_market_view.html',
            player=player,
            shops=shops,
            items=items
        )
    except Exception as e:
        print(f"[ERROR] Error viewing market: {e}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        flash('An error occurred while viewing the market.', 'error')
        return redirect(url_for('player.player_home'))

@player_bp.route("/api/market-data")
@login_required
def get_market_data():
    try:
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            return jsonify({'error': 'Player not found'}), 404

        filter_type = request.args.get('filter', 'all')

        # Query all items and their inventories across all shops in the player's GM profile
        items_query = (
            db.session.query(
                Item,
                db.func.sum(ShopInventory.stock).label('total_stock'),
                db.func.avg(ShopInventory.dynamic_price).label('avg_price')
            )
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .join(Shop, Shop.shop_id == ShopInventory.shop_id)
            .filter(Shop.gm_profile_id == player.gm_profile_id)
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
    """Resolve the Campaign the player is currently acting inside.

    Priority: the campaign stored in session (set by campaign_selection),
    verified against an active CampaignPlayer membership for ``player``. If
    that is missing/stale we fall back to the player's single active
    membership (if there is exactly one).
    """
    if player is None:
        return None

    sess_id = session.get("campaign_id")
    if sess_id is not None:
        membership = CampaignPlayer.query.filter_by(
            campaign_id=sess_id, player_id=player.id, is_active=True
        ).first()
        if membership is not None:
            return membership.campaign

    memberships = CampaignPlayer.query.filter_by(
        player_id=player.id, is_active=True
    ).all()
    if len(memberships) == 1:
        return memberships[0].campaign
    return None


@player_bp.route("/character")
@login_required
def view_character():
    player = Player.query.filter_by(user_id=current_user.id).first()
    if not player:
        flash("Player profile not found.", "error")
        return redirect(url_for("player.player_home"))

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


@player_bp.route("/character/update", methods=["POST"])
@login_required
def update_character():
    player = Player.query.filter_by(user_id=current_user.id).first()
    if not player:
        flash("Player profile not found.", "error")
        return redirect(url_for("player.player_home"))

    campaign = _active_campaign_for_player(player)
    if campaign is None:
        flash("Select a campaign before editing your character.", "warning")
        return redirect(url_for("main.campaigns"))

    ok, errors = character_sheet_service.apply_sheet_update(
        player, campaign, request.form
    )
    if ok:
        flash("Character sheet saved.", "success")
    else:
        for msg in errors or ["Failed to save character sheet."]:
            flash(msg, "error")
    return redirect(url_for("player.view_character"))


@player_bp.route("/equip/<int:item_id>", methods=["POST"])
@login_required
def equip_item(item_id):
    try:
        player = Player.query.filter_by(user_id=current_user.id).first()
        if not player:
            flash("Player profile not found.", "error")
            return redirect(url_for("player.player_home"))

        # Must be a real item in the player's campaign, AND the player must
        # actually own at least one of it in their inventory. This blocks
        # direct-POST attempts to equip items the player does not have.
        item = Item.query.filter_by(
            item_id=item_id, gm_profile_id=player.gm_profile_id
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
        player = Player.query.filter_by(user_id=current_user.id).first()
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
        player = Player.query.filter_by(user_id=current_user.id).first()
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
