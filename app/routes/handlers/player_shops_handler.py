"""
Player Shops Handler
Handles all shop-related business logic for player routes
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from app.extensions import db
from app.models.users import Player, PlayerInventory
from app.models.backend import City, Shop, ShopInventory, Item


def view_shops():
    """View all shops for the player's GM"""
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


def view_shop(shop_id):
    """View a specific shop and its items"""
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


def view_shop_items(shop_id):
    """View all items in a specific shop"""
    try:
        # Get the current player
        player = Player.query.filter_by(user_id_player=current_user.id).first()
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


def buy_item(shop_id, item_id):
    """Buy an item from a shop"""
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
