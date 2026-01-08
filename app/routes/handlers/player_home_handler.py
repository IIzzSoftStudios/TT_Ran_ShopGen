"""
Player Home Handler
Handles the main player dashboard and home page logic
"""
from flask import render_template, redirect, url_for, flash, session
from flask_login import current_user
from app.extensions import db
from app.models.users import Player, PlayerInventory
from app.models.backend import City, Shop, ShopInventory, Item


def player_home():
    """Render the player home dashboard"""
    print("[DEBUG] Starting player_home route")
    print(f"[DEBUG] Current user: {current_user.username}, Role: {current_user.role}")
    
    # Check if campaign is selected in session
    campaign_id = session.get('campaign_id')
    if not campaign_id:
        flash("Please select a campaign first.", "info")
        return redirect(url_for("main.campaigns"))
    
    try:
        # Fetch player details for the selected campaign
        player = Player.query.filter_by(
            user_id_player=current_user.id,
            gm_profile_id=campaign_id
        ).first()
        if not player:
            print("[DEBUG] Player not found for campaign")
            flash("Player profile not found for this campaign. Please contact your GM.", "error")
            session.pop('campaign_id', None)
            return redirect(url_for("main.campaigns"))
        
        print(f"[DEBUG] Found player: {player.id}, User ID: {player.user_id_player}, GM Profile ID: {player.gm_profile_id}")

        # Verify GM profile exists
        gm_profile = player.gm_profile
        if not gm_profile:
            print("[DEBUG] GM Profile not found")
            flash("GM profile not found. Please contact support.", "error")
            session.pop('campaign_id', None)
            return redirect(url_for("main.campaigns"))
        
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

        # Get market data for visualizations - top items by average price
        market_data = (
            db.session.query(
                Item.name,
                Item.base_price,
                db.func.avg(ShopInventory.dynamic_price).label('avg_price'),
                db.func.count(ShopInventory.shop_id).label('shop_count'),
                db.func.sum(ShopInventory.stock).label('total_stock')
            )
            .join(ShopInventory, ShopInventory.item_id == Item.item_id)
            .join(Shop, Shop.shop_id == ShopInventory.shop_id)
            .filter(Shop.gm_profile_id == gm_profile.id)
            .group_by(Item.item_id, Item.name, Item.base_price)
            .order_by(db.func.avg(ShopInventory.dynamic_price).desc())
            .limit(6)
            .all()
        )
        print(f"[DEBUG] Found {len(market_data)} items for market visualization")

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
            player_name=player.player_user.username,
            player_currency=player.currency,
            cities=cities,
            shops=shops,
            items=shop_items,
            shop_items=shop_items,
            inventory_items=inventory_items,
            market_data=market_data
        )
    except Exception as e:
        print(f"[ERROR] Error in player_home: {str(e)}")
        print(f"[ERROR] Exception type: {type(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        flash("An error occurred while loading your home page. Please try again.", "error")
        return redirect(url_for("auth.logout"))
