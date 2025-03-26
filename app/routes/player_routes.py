from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import Player, City, Shop, ShopInventory, Item
from flask_login import login_required, current_user
from app.extensions import db

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
                Item.item_id
            )
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .filter(ShopInventory.shop_id == shop_id)
            .all()
        )

        print(f"[DEBUG] Found {len(shop_items)} items in shop")

        return render_template(
            "Player_view_city_shops.html",
            shop=shop,
            city=city,
            shop_items=shop_items,
            player_currency=player.currency
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
    
    # Fetch player details
    player = Player.query.filter_by(user_id=current_user.id).first()
    if not player:
        print("[DEBUG] Player not found")
        return "Player not found", 404
    
    print(f"[DEBUG] Found player: {player.id}, User ID: {player.user_id}, GM Profile ID: {player.gm_profile_id}")

    # Verify GM profile exists
    gm_profile = player.gm_profile
    if not gm_profile:
        print("[DEBUG] GM Profile not found for player")
        return "GM Profile not found", 404
    
    print(f"[DEBUG] Found GM Profile: {gm_profile.id}, User ID: {gm_profile.user_id}")

    # Fetch available cities for the player's GM
    cities = City.query.filter_by(gm_profile_id=player.gm_profile_id).all()
    print(f"[DEBUG] Found {len(cities)} cities for GM Profile {player.gm_profile_id}")
    for city in cities:
        print(f"[DEBUG] City: {city.name} (ID: {city.city_id})")

    return render_template(
        "Player_Home.html",
        player_currency=player.currency,
        cities=cities,
    )

# Search route
@player_bp.route("/search")
@login_required
def search_item():
    query = request.args.get("query", "").strip()
    if not query:
        return redirect(url_for("player.player_home"))

    # Search for items matching the query
    results = (
        db.session.query(Item.name, Shop.name.label("shop_name"), City.name.label("city_name"))
        .join(ShopInventory, ShopInventory.item_id == Item.id)
        .join(Shop, ShopInventory.shop_id == Shop.id)
        .join(City, Shop.city_id == City.id)
        .filter(Item.name.ilike(f"%{query}%"))
        .all()
    )

    return render_template("search_results.html", query=query, results=results)

@player_bp.route("/shop/<int:shop_id>/buy/<int:item_id>", methods=['POST'])
@login_required
def buy_item(shop_id, item_id):
    try:
        # Get the current player
        player = Player.query.filter_by(user_id=current_user.id).first()
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

        # Check if player has enough currency
        if player.currency < inventory.dynamic_price:
            return jsonify({'success': False, 'message': 'Not enough currency'})

        # Check if item is in stock
        if inventory.stock <= 0:
            return jsonify({'success': False, 'message': 'Item out of stock'})

        # Process the purchase
        player.currency -= inventory.dynamic_price
        inventory.stock -= 1

        db.session.commit()
        return jsonify({'success': True, 'message': 'Purchase successful'})

    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Error buying item: {e}")
        return jsonify({'success': False, 'message': 'An error occurred while processing your purchase'})
