from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.routes.handlers.gm_cities_handler import (
    view_cities, add_city, edit_city, delete_city
)
from app.routes.handlers.gm_shops_handler import (
    view_shops, add_shop, edit_shop, delete_shop, view_city_shops, 
    view_shop_items, remove_item_from_shop
)
from app.routes.handlers.gm_items_handler import (
    view_items, add_item, edit_item, item_detail, delete_item
)
from app.routes.handlers.gm_simulation_handler import (
    home, seed_world, run_simulation_tick, update_simulation_speed, debug_form
)

gm_bp = Blueprint("gm", __name__, url_prefix="/gm")


@gm_bp.route("/")
@login_required
def gm_home():
    """Render the GM dashboard with simulation controls and status."""
    return home()

# --- Seeding Route ---
@gm_bp.route("/seed_world", methods=["POST"])
@login_required
def gm_seed_world():
    """Route to trigger the seeding of the GM's world data."""
    return seed_world()


# Cities routes
@gm_bp.route("/cities/")
@login_required
def gm_view_cities():
    """View all cities for the current GM"""
    return view_cities()

@gm_bp.route("/cities/add", methods=["GET", "POST"])
@login_required
def gm_add_city():
    """Add a new city"""
    return add_city()

@gm_bp.route("/cities/edit/<int:city_id>", methods=["GET", "POST"])
@login_required
def gm_edit_city(city_id):
    """Edit an existing city"""
    return edit_city(city_id)

@gm_bp.route("/cities/delete/<int:city_id>", methods=["POST"])
@login_required
def gm_delete_city(city_id):
    """Delete a city"""
    return delete_city(city_id)

# Shops routes
@gm_bp.route("/shops/")
@login_required
def gm_view_shops():
    """View all shops for the current GM"""
    return view_shops()

@gm_bp.route("/shops/add", methods=["GET", "POST"])
@login_required
def gm_add_shop():
    """Add a new shop"""
    return add_shop()

@gm_bp.route("/shops/edit/<int:shop_id>", methods=["GET", "POST"])
@login_required
def gm_edit_shop(shop_id):
    """Edit an existing shop"""
    return edit_shop(shop_id)

@gm_bp.route("/shops/delete/<int:shop_id>", methods=["POST"])
@login_required
def gm_delete_shop(shop_id):
    """Delete a shop"""
    return delete_shop(shop_id)

@gm_bp.route("/shops/city/<int:city_id>/shops")
@login_required
def gm_view_city_shops(city_id):
    """View all shops in a specific city"""
    return view_city_shops(city_id)

# Shop items routes
@gm_bp.route("/shops/<int:shop_id>/items")
@login_required
def gm_view_shop_items(shop_id):
    """View all items in a specific shop"""
    return view_shop_items(shop_id)

@gm_bp.route("/shops/remove_item/<int:shop_id>/<int:item_id>", methods=["POST"])
@login_required
def gm_remove_item_from_shop(shop_id, item_id):
    """Remove an item from a shop's inventory"""
    return remove_item_from_shop(shop_id, item_id)

# Items routes
@gm_bp.route("/items/")
@login_required
def gm_view_items():
    """View all items for the current GM"""
    return view_items()

@gm_bp.route("/items/add", methods=["GET", "POST"])
@login_required
def gm_add_item():
    """Add a new item"""
    return add_item()


@gm_bp.route("/items/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def gm_edit_item(item_id):
    """Edit an existing item"""
    return edit_item(item_id)

@gm_bp.route("/items/detail/<int:item_id>")
@login_required
def gm_item_detail(item_id):
    """View detailed information about an item"""
    return item_detail(item_id)

@gm_bp.route("/items/delete/<int:item_id>", methods=["POST"])
@login_required
def gm_delete_item(item_id):
    """Delete an item"""
    return delete_item(item_id) 

@gm_bp.route("/debug/form", methods=["POST"])
def gm_debug_form():
    """Debug form submission"""
    return debug_form()



# Simulation routes
@gm_bp.route("/simulation/tick", methods=["POST"])
@login_required
def gm_run_simulation_tick():
    """Execute one simulation tick manually from the GM dashboard"""
    return run_simulation_tick()

@gm_bp.route("/simulation/speed", methods=["POST"])
@login_required
def gm_update_simulation_speed():
    """Update the simulation speed setting and run the appropriate time period"""
    return update_simulation_speed()


# # Resource Node routes
# @gm_bp.route("/resource_nodes/")
# @login_required
# def view_resource_nodes():
#     nodes = ResourceNode.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     return render_template("GM_view_resource_nodes.html", nodes=nodes)

# @gm_bp.route("/resource_nodes/add", methods=["GET", "POST"])
# @login_required
# def add_resource_node():
#     if request.method == "POST":
#         name = request.form.get("name")
#         type = request.form.get("type")
#         production_rate = float(request.form.get("production_rate"))
#         quality = float(request.form.get("quality"))
#         city_id = int(request.form.get("city_id"))
#         item_id = int(request.form.get("item_id"))

#         if not all([name, type, production_rate, quality, city_id, item_id]):
#             flash("All fields are required!", "danger")
#             return render_template("GM_add_resource_node.html")

#         try:
#             new_node = ResourceNode(
#                 name=name,
#                 type=type,
#                 production_rate=production_rate,
#                 quality=quality,
#                 city_id=city_id,
#                 item_id=item_id,
#                 gm_profile_id=current_user.gm_profile.id
#             )
#             db.session.add(new_node)
#             db.session.commit()
#             flash(f"Resource node '{name}' added successfully!", "success")
#             return redirect(url_for("gm.view_resource_nodes"))
#         except Exception as e:
#             db.session.rollback()
#             flash(f"Error adding resource node: {e}", "danger")

#     # GET request - show form
#     cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     items = Item.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     return render_template("GM_add_resource_node.html", cities=cities, items=items)

# @gm_bp.route("/resource_nodes/edit/<int:node_id>", methods=["GET", "POST"])
# @login_required
# def edit_resource_node(node_id):
#     node = ResourceNode.query.get_or_404(node_id)
    
#     if request.method == "POST":
#         node.name = request.form.get("name")
#         node.type = request.form.get("type")
#         node.production_rate = float(request.form.get("production_rate"))
#         node.quality = float(request.form.get("quality"))
#         node.city_id = int(request.form.get("city_id"))
#         node.item_id = int(request.form.get("item_id"))
        
#         try:
#             db.session.commit()
#             flash("Resource node updated successfully!", "success")
#             return redirect(url_for("gm.view_resource_nodes"))
#         except Exception as e:
#             db.session.rollback()
#             flash(f"Error updating resource node: {e}", "danger")

#     cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     items = Item.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     return render_template("GM_edit_resource_node.html", node=node, cities=cities, items=items)

# @gm_bp.route("/resource_nodes/delete/<int:node_id>", methods=["POST"])
# @login_required
# def delete_resource_node(node_id):
#     node = ResourceNode.query.get_or_404(node_id)
#     try:
#         db.session.delete(node)
#         db.session.commit()
#         flash("Resource node deleted successfully!", "success")
#     except Exception as e:
#         db.session.rollback()
#         flash(f"Error deleting resource node: {e}", "danger")
#     return redirect(url_for("gm.view_resource_nodes"))