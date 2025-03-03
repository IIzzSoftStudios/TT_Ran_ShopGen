from flask import Blueprint, render_template, request, redirect, url_for
from app.models import Player, City, Shop, Inventory, Item
from flask_login import login_required, current_user
from app.extensions import db

player_bp = Blueprint("player", __name__)

#Player Home
@player_bp.route("/player_home")
@login_required
def player_home():
    # Fetch player details
    player = Player.query.filter_by(id=current_user.id).first()
    if not player:
        return "Player not found", 404

    # Fetch inventory and currency
    inventory = (
        db.session.query(Item.name, Inventory.quantity)
        .join(Inventory, Inventory.item_id == Item.id)
        .filter(Inventory.player_id == player.id)
        .all()
    )
    
    # Fetch available cities
    cities = City.query.all()

    return render_template(
        "Player_Home.html",
        player_currency=player.currency,
        player_inventory=inventory,
        cities=cities
    )

#City View
@player_bp.route("/city/<int:city_id>")
@login_required
def view_city(city_id):
    city = City.query.get_or_404(city_id)
    shops = Shop.query.filter_by(city_id=city.id).all()

    return render_template("city_view.html", city=city, shops=shops)

#Shop Inventory
@player_bp.route("/shop/<int:shop_id>")
@login_required
def view_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    shop_items = (
        db.session.query(Item.name, Inventory.stock, Inventory.dynamic_price)
        .join(Inventory, Inventory.item_id == Item.id)
        .filter(Inventory.shop_id == shop.id)
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
        .join(Inventory, Inventory.item_id == Item.id)
        .join(Shop, Inventory.shop_id == Shop.id)
        .join(City, Shop.city_id == City.id)
        .filter(Item.name.ilike(f"%{query}%"))
        .all()
    )

    return render_template("search_results.html", query=query, results=results)
