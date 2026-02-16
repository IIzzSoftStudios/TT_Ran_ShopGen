from flask import Blueprint, request
from flask_login import login_required, current_user
from app.routes.handlers.player_shops_handler import (
    view_shop as handle_view_shop, 
    view_shops as handle_view_shops, 
    view_shop_items as handle_view_shop_items, 
    buy_item as handle_buy_item
)
from app.routes.handlers.player_cities_handler import (
    view_cities as handle_view_cities, 
    view_city as handle_view_city
)
from app.routes.handlers.player_home_handler import (
    player_home as handle_player_home
)
from app.routes.handlers.player_market_handler import (
    view_market as handle_view_market, 
    search_item as handle_search_item
)
from app.routes.handlers.player_inventory_handler import (
    sell_item as handle_sell_item
)
from app.routes.handlers.player_character_handler import (
    view_character as handle_view_character,
    get_character_data as handle_get_character_data,
    equip_item as handle_equip_item,
    unequip_item as handle_unequip_item,
    create_character as handle_create_character,
    update_character as handle_update_character,
)

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
    """View a specific shop and its items"""
    return handle_view_shop(shop_id)

@player_bp.route("/shops")
@login_required
def view_shops():
    """View all shops for the player's GM"""
    return handle_view_shops()

# City routes
@player_bp.route("/cities")
@login_required
def view_cities():
    """View all cities for the player's GM"""
    return handle_view_cities()

@player_bp.route("/cities/<int:city_id>")
@login_required
def view_city(city_id):
    """View a specific city and its shops"""
    return handle_view_city(city_id)

# Home route last (least specific)
@player_bp.route("/home")
@login_required
def player_home():
    """Render the player home dashboard"""
    return handle_player_home()


@player_bp.route("/character")
@login_required
def view_character():
    """Render the full character sheet page"""
    return handle_view_character()

@player_bp.route("/character/create", methods=["GET", "POST"])
@login_required
def create_character():
    """Create a new character for the player"""
    return handle_create_character()

@player_bp.route("/character/update", methods=["POST"])
@login_required
def update_character():
    """Update character information"""
    return handle_update_character()

# Search route
@player_bp.route("/search")
@login_required
def search_item():
    """Search for items across shops and cities"""
    return handle_search_item()


@player_bp.route("/character/data")
@login_required
def character_data():
    """JSON endpoint for the current player's active character"""
    return handle_get_character_data()

@player_bp.route("/shop/<int:shop_id>/buy/<int:item_id>", methods=['POST'])
@login_required
def buy_item(shop_id, item_id):
    """Buy an item from a shop"""
    return handle_buy_item(shop_id, item_id)

@player_bp.route("/shop/<int:shop_id>/items")
@login_required
def view_shop_items(shop_id):
    """View all items in a specific shop"""
    return handle_view_shop_items(shop_id)

@player_bp.route("/sell/<int:item_id>", methods=['POST'])
@login_required
def sell_item(item_id):
    """Sell an item from player's inventory"""
    return handle_sell_item(item_id)


@player_bp.route("/character/equip/<int:item_id>", methods=["POST"])
@login_required
def equip_item(item_id):
    """Equip an item from the player's inventory onto their character"""
    return handle_equip_item(item_id)


@player_bp.route("/character/unequip/<slot_name>", methods=["POST"])
@login_required
def unequip_item(slot_name):
    """Unequip the item currently in the specified slot"""
    return handle_unequip_item(slot_name)

@player_bp.route("/market")
@login_required
def view_market():
    """View the market with all available items"""
    return handle_view_market()
