"""
Player Market Handler
Handles all market-related business logic for player routes
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from app.extensions import db
from app.models.users import Player, PlayerInventory
from app.models.backend import City, Shop, ShopInventory, Item, shop_cities
from app.routes.handlers.player_helpers import get_current_player


def view_market():
    """View the market with all available items"""
    try:
        print("[DEBUG] Entered /player/market route")
        
        # Get the current player
        player, redirect_response = get_current_player()
        if redirect_response:
            return redirect_response
        
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


def search_item():
    """Search for items across shops and cities"""
    try:
        # Get the current player
        player, redirect_response = get_current_player()
        if redirect_response:
            return jsonify({'error': 'Please select a campaign first'}), 400

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
