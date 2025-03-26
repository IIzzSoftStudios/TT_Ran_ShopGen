from flask import Blueprint, render_template, request, redirect, url_for
from app.models import Player, City, Shop, ShopInventory, Item
from flask_login import login_required, current_user
from app.extensions import db

player_bp = Blueprint("player", __name__)

#Player Home
@player_bp.route("/player_home")
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

    #TO-DO: Fetch inventory, need to add buy and sell functionality first to query from the shop inventory table, and aquire items to display in the inventory.
    # Fetch inventory and currency
    # inventory = (
    #     db.session.query(Item.name, ShopInventory.quantity)
    #     .join(ShopInventory, ShopInventory.item_id == Item.id)
    #     .filter(ShopInventory.player_id == player.id)
    #     .all()
    # )
    # print(f"[DEBUG] Found {len(inventory)} inventory items")
    
    # Fetch available cities for the player's GM
    cities = City.query.filter_by(gm_profile_id=player.gm_profile_id).all()
    print(f"[DEBUG] Found {len(cities)} cities for GM Profile {player.gm_profile_id}")
    for city in cities:
        print(f"[DEBUG] City: {city.name} (ID: {city.city_id})")

    return render_template(
        "Player_Home.html",
        player_currency=player.currency,
        # player_inventory=inventory,
        cities=cities
    )

#City View
@player_bp.route("/city/<int:city_id>")
@login_required
def view_city(city_id):
    # Get the player and verify they have access to this city
    player = Player.query.filter_by(user_id=current_user.id).first()
    if not player:
        return "Player not found", 404

    city = City.query.filter_by(city_id=city_id, gm_profile_id=player.gm_profile_id).first_or_404()
    shops = Shop.query.filter_by(city_id=city.id).all()

    return render_template("city_view.html", city=city, shops=shops)

#Shop Inventory
@player_bp.route("/shop/<int:shop_id>")
@login_required
def view_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    shop_items = (
        db.session.query(Item.name, ShopInventory.stock, ShopInventory.dynamic_price)
        .join(ShopInventory, ShopInventory.item_id == Item.id)
        .filter(ShopInventory.shop_id == shop.id)
        .all()
    )

    return render_template("shop_inventory.html", shop=shop, shop_items=shop_items)

#Search for an Item
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
