from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.users import Player, PlayerInventory
from app.models.backend import City, Shop, ShopInventory, Item, shop_cities

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
        player = Player.query.filter_by(user_id_player=current_user.id).first()
        if not player:
            print("[DEBUG] Player not found")
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        print(f"[DEBUG] Found player: {player.id}, GM Profile ID: {player.gm_profile_id}")

        # Get the shop and verify it belongs to the player's GM, with cities eagerly loaded
        shop = (
            Shop.query
            .options(db.joinedload(Shop.cities))
            .get_or_404(shop_id)
        )
        print(f"[DEBUG] Found shop: {shop.name}, GM Profile ID: {shop.gm_profile_id}")
        
        if shop.gm_profile_id != player.gm_profile_id:
            print(f"[DEBUG] Access denied - Shop GM Profile ID ({shop.gm_profile_id}) doesn't match Player's GM Profile ID ({player.gm_profile_id})")
            flash('You do not have access to this shop.', 'error')
            return redirect(url_for('player.player_home'))

        # Get the city this shop belongs to
        city = shop.cities[0] if shop.cities else None
        if not city:
            print("[DEBUG] No city found for shop")
            flash('Shop location not found.', 'error')
            return redirect(url_for('player.player_home'))

        print(f"[DEBUG] Found city: {city.name}")

        # Get shop inventory with item details
        shop_items = (
            db.session.query(
                Item.name,
                Item.type,
                ShopInventory.stock,
                ShopInventory.dynamic_price,
                Item.item_id,
                Item.base_price
            )
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .filter(ShopInventory.shop_id == shop_id)
            .all()
        )

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
        player = Player.query.filter_by(user_id_player=current_user.id).first()
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
        player = Player.query.filter_by(user_id_player=current_user.id).first()
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
        player = Player.query.filter_by(user_id_player=current_user.id).first()
        if not player:
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        # Get the city and verify it belongs to the player's GM
        city = City.query.get_or_404(city_id)
        if city.gm_profile_id != player.gm_profile_id:
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
    
    try:
        # Fetch player details
        player = Player.query.filter_by(user_id_player=current_user.id).first()
        if not player:
            print("[DEBUG] Player not found")
            flash("Player profile not found. Please contact your GM.", "error")
            return redirect(url_for("auth.logout"))
        
        print(f"[DEBUG] Found player: {player.id}, User ID: {player.user_id_player}, GM Profile ID: {player.gm_profile_id}")

        # Verify GM profile exists
        gm_profile = player.gm_profile
        if not gm_profile:
            print("[DEBUG] GM Profile not found")
            flash("GM profile not found. Please contact support.", "error")
            return redirect(url_for("auth.logout"))
        
        print(f"[DEBUG] Found GM Profile: {gm_profile.id}, User ID: {gm_profile.user_id}")

        # Get all cities for the GM
        cities = City.query.filter_by(gm_profile_id=gm_profile.id).all()
        print(f"[DEBUG] Found {len(cities)} cities for GM Profile {gm_profile.id}")
        for city in cities:
            print(f"[DEBUG] City: {city.name} (ID: {city.city_id})")

        # Get all shops for the GM
        shops = Shop.query.filter_by(gm_profile_id=gm_profile.id).all()
        print(f"[DEBUG] Found {len(shops)} shops for GM Profile {gm_profile.id}")
        for shop in shops:
            print(f"[DEBUG] Shop: {shop.name} (ID: {shop.shop_id})")

        # Get all items in shops for the GM
        shop_items = (
            db.session.query(Item)
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .join(Shop, Shop.shop_id == ShopInventory.shop_id)
            .filter(Shop.gm_profile_id == gm_profile.id)
            # .distinct()
            .all()
        )
        print(f"[DEBUG] Found {len(shop_items)} items in shops for GM Profile {gm_profile.id}")
        for item in shop_items:
            print(f"[DEBUG] Item: {item.name} (ID: {item.item_id})")

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

        return render_template(
            "Player_Home.html",
            player=player,
            cities=cities,
            shops=shops,
            shop_items=shop_items,
            inventory_items=inventory_items
        )
    except Exception as e:
        print(f"[ERROR] Error in player_home: {str(e)}")
        print(f"[ERROR] Exception type: {type(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        flash("An error occurred while loading your home page. Please try again.", "error")
        return redirect(url_for("auth.logout"))

# Search route
@player_bp.route("/search")
@login_required
def search_item():
    try:
        # Get the current player
        player = Player.query.filter_by(user_id_player=current_user.id).first()
        if not player:
            return jsonify({'error': 'Player not found'}), 404

        print(f"[DEBUG] Searching for player: {player.id}, GM Profile ID: {player.gm_profile_id}")

        # Debug: Check available shops and items
        shops = Shop.query.filter_by(gm_profile_id=player.gm_profile_id).all()
        print(f"[DEBUG] Found {len(shops)} shops for GM Profile {player.gm_profile_id}")
        for shop in shops:
            print(f"[DEBUG] Shop: {shop.name} (ID: {shop.shop_id})")
            print(f"[DEBUG] Cities: {[city.name for city in shop.cities]}")

        items = Item.query.all()
        print(f"[DEBUG] Found {len(items)} total items in database")
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
                ShopInventory.dynamic_price
            )
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .join(Shop, ShopInventory.shop_id == Shop.shop_id)
            .join(shop_cities, Shop.shop_id == shop_cities.c.shop_id)
            .join(City, shop_cities.c.city_id == City.city_id)
            .filter(Shop.gm_profile_id == player.gm_profile_id)
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

        # Format results
        formatted_results = [{
            'item_name': result.item_name,
            'shop_name': result.shop_name,
            'city_name': result.city_name,
            'shop_id': result.shop_id,
            'item_id': result.item_id,
            'stock': result.stock,
            'price': result.dynamic_price
        } for result in results]

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
        player = Player.query.filter_by(user_id_player=current_user.id).first()
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'})

        # Get the shop and verify it belongs to the player's GM
        shop = Shop.query.get_or_404(shop_id)
        if shop.gm_profile_id != player.gm_profile_id:
            return jsonify({'success': False, 'message': 'You do not have access to this shop'})

        # Get the shop inventory item
        inventory = ShopInventory.query.filter_by(shop_id=shop_id, item_id=item_id).first()
        if not inventory:
            return jsonify({'success': False, 'message': 'Item not found in shop'})

        # Get quantity from request (default to 1 if not specified)
        quantity = int(request.form.get('quantity', 1))
        if quantity <= 0:
            return jsonify({'success': False, 'message': 'Invalid quantity'})

        # Check if item is in stock
        if inventory.stock < quantity:
            return jsonify({'success': False, 'message': 'Not enough items in stock'})

        # Process the purchase
        total_cost = inventory.dynamic_price * quantity
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
        player = Player.query.filter_by(user_id_playe=current_user.id).first()
        if not player:
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))

        # Get the shop and verify it belongs to the player's GM
        shop = Shop.query.get_or_404(shop_id)
        if shop.gm_profile_id != player.gm_profile_id:
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
        player = Player.query.filter_by(user_id_player=current_user.id).first()
        if not player:
            return _ajax_or_redirect('Player profile not found.', error=True)

        # Get the item and verify it belongs to the player's GM
        item = Item.query.get_or_404(item_id)
        if item.gm_profile_id != player.gm_profile_id:
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
        player = Player.query.filter_by(user_id_player =current_user.id).first()
        if not player:
            print("[DEBUG] Player not found - redirecting to home")
            flash('Player profile not found.', 'error')
            return redirect(url_for('player.player_home'))
        
        print(f"[DEBUG] Found player: {player.id}, GM Profile ID: {player.gm_profile_id}")

        # Get all shops for the player's GM
        shops = Shop.query.filter_by(gm_profile_id=player.gm_profile_id).all()
        print(f"[DEBUG] Found {len(shops)} shops for player's GM")

        # Get all items in shops for the GM
        items = (
            db.session.query(Item)
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .join(Shop, Shop.shop_id == ShopInventory.shop_id)
            .filter(Shop.gm_profile_id == player.gm_profile_id)
            # .distinct()
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
