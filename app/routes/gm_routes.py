import traceback

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import City, Shop, Item, ShopInventory
from app.routes.handlers.gm_helpers import (
    city_for_gm_or_404,
    item_for_gm_or_404,
    shop_for_gm_or_404,
)
from app.routes.handlers.gm_players_handler import (
    list_players,
    view_character,
    update_character,
    equip_item,
    unequip_item,
    update_inventory,
)
from app.routes.handlers.gm_simulation_handler import (
    home as gm_dashboard_home,
    seed_world,
    run_simulation_tick,
    update_simulation_speed,
    run_period_stream,
    simulation_job_status,
    debug_form as gm_debug_form_handler,
)
from app.routes.handlers.gm_shops_handler import (
    update_shop_basic as update_shop_basic_handler,
    get_shop_city_panel_context,
    get_grouped_shops,
    get_linked_shop_ids_for_item,
)
from app.routes.handlers.gm_campaigns_handler import (
    list_campaigns,
    create_campaign,
    sync_players_to_campaign as sync_players_to_campaign_handler,
    delete_campaign as delete_campaign_handler,
)

gm_bp = Blueprint("gm", __name__, url_prefix="/gm")


@gm_bp.route("/")
@login_required
def home():
    return gm_dashboard_home()


@gm_bp.route("/seed_world", methods=["POST"])
@login_required
def gm_seed_world():
    return seed_world()

#cities routes

@gm_bp.route("/cities/")
@login_required
def view_cities():
    cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_view_cities.html", cities=cities)

@gm_bp.route("/cities/add", methods=["GET", "POST"])
@login_required
def add_city():
    if request.method == "POST":
        name = request.form.get("name")
        size = request.form.get("size")
        population = request.form.get("population")
        region = request.form.get("region")

        if not name or not size or not population or not region:
            flash("All fields are required!", "danger")
            return render_template("GM_add_city.html")

        try:
            new_city = City(
                name=name,
                size=size,
                population=int(population),
                region=region,
                gm_profile_id=current_user.gm_profile.id
            )
            db.session.add(new_city)
            db.session.commit()
            flash(f"City '{name}' added successfully!", "success")
            return redirect(url_for("gm.view_cities"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding city: {e}", "danger")

    return render_template("GM_add_city.html")

@gm_bp.route("/cities/edit/<int:city_id>", methods=["GET", "POST"])
@login_required
def edit_city(city_id):
    city = city_for_gm_or_404(city_id, current_user.gm_profile.id)
    
    if request.method == "POST":
        city.name = request.form.get("name")
        city.size = request.form.get("size")
        city.population = request.form.get("population")
        city.region = request.form.get("region")

        try:
            db.session.commit()
            flash("City updated successfully!", "success")
            return redirect(url_for("gm.view_cities"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating city: {e}", "danger")

    return render_template("GM_edit_city.html", city=city)

@gm_bp.route("/cities/delete/<int:city_id>", methods=["POST"])
@login_required
def delete_city(city_id):
    city = city_for_gm_or_404(city_id, current_user.gm_profile.id)
    try:
        db.session.delete(city)
        db.session.commit()
        flash("City deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting city: {e}", "danger")
    return redirect(url_for("gm.view_cities"))


@gm_bp.route("/shops/")
@login_required
def view_shops():
    ctx = get_shop_city_panel_context(current_user.gm_profile)
    return render_template("GM_view_shops.html", **ctx)

@gm_bp.route("/shops/add", methods=["GET", "POST"])
@login_required
def add_shop():
    if request.method == "POST":
        shop_name = request.form.get("name")
        shop_type = request.form.get("type")
        city_ids = request.form.getlist("city_ids")

        print("DEBUG: Shop Name:", shop_name)
        print("DEBUG: Shop Type:", shop_type)
        print("DEBUG: City IDs:", city_ids)

        try:
            gm_profile_id = current_user.gm_profile.id
            print("DEBUG: GM Profile ID:", gm_profile_id)

            new_shop = Shop(
                name=shop_name,
                type=shop_type,
                gm_profile_id=gm_profile_id
            )
            db.session.add(new_shop)
            db.session.flush()  # Ensures new_shop gets an ID

            for city_id in city_ids:
                try:
                    cid = int(city_id)
                    city = City.query.filter_by(
                        city_id=cid, gm_profile_id=gm_profile_id
                    ).first()
                    if city:
                        new_shop.cities.append(city)
                    else:
                        print(f"[WARNING] City ID {city_id} not found or not in campaign.")
                except ValueError:
                    print(f"[ERROR] Invalid city_id value: {city_id}")

            db.session.commit()
            flash(f"Shop '{shop_name}' added successfully!", "success")

        except Exception as e:
            db.session.rollback()
            print("[ERROR] Exception occurred while adding shop:")
            traceback.print_exc()
            flash(f"Error adding shop: {e}", "danger")

        return redirect(url_for("gm.view_shops"))

    # GET request: render form
    cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_add_shop.html", cities=cities)

@gm_bp.route("/shops/edit/<int:shop_id>", methods=["GET", "POST"])
@login_required
def edit_shop(shop_id):
    shop = shop_for_gm_or_404(shop_id, current_user.gm_profile.id)
    
    if request.method == "POST":
        shop.name = request.form["name"]
        shop.type = request.form["type"]
        try:
            db.session.commit()
            flash("Shop updated successfully!", "success")
            return redirect(url_for("gm.view_shops"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating shop: {e}", "danger")

    cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_edit_shop.html", shop=shop, cities=cities)


@gm_bp.route("/shops/update-basic/<int:shop_id>", methods=["POST"])
@login_required
def update_shop_basic(shop_id):
    return update_shop_basic_handler(shop_id)


@gm_bp.route("/shops/delete/<int:shop_id>", methods=["POST"])
@login_required
def delete_shop(shop_id):
    shop = shop_for_gm_or_404(shop_id, current_user.gm_profile.id)
    try:
        db.session.delete(shop)
        db.session.commit()
        flash("Shop deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting shop: {e}", "danger")
    return redirect(url_for("gm.view_shops"))

@gm_bp.route("/shops/city/<int:city_id>/shops")
@login_required
def view_city_shops(city_id):
    city = city_for_gm_or_404(city_id, current_user.gm_profile.id)
    shops = city.shops
    return render_template("GM_view_city_shops.html", city=city, shops=shops)

@gm_bp.route("/shops/<int:shop_id>/items")
@login_required
def view_shop_items(shop_id):
    shop = shop_for_gm_or_404(shop_id, current_user.gm_profile.id)
    city = shop.cities[0] if shop.cities else None
    shop_inventory = ShopInventory.query.filter_by(shop_id=shop_id).all()
    item_ids = [inv.item_id for inv in shop_inventory]
    items = Item.query.filter(Item.item_id.in_(item_ids)).all()
    return render_template("GM_view_shop_items.html", items=items, shop=shop, city=city)

@gm_bp.route("/shops/remove_item/<int:shop_id>/<int:item_id>", methods=["POST"])
@login_required
def remove_item_from_shop(shop_id, item_id):
    shop_for_gm_or_404(shop_id, current_user.gm_profile.id)
    try:
        inventory = ShopInventory.query.filter_by(shop_id=shop_id, item_id=item_id).first()
        if inventory:
            db.session.delete(inventory)
            db.session.commit()
            flash("Item removed from shop successfully!", "success")
        else:
            flash("Item not found in shop.", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Error removing item from shop: {e}", "danger")
    return redirect(url_for("gm.view_shop_items", shop_id=shop_id))

#items routes

@gm_bp.route("/items/")
@login_required
def view_items():
    items = Item.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_view_items.html", items=items)

@gm_bp.route("/items/add", methods=["GET", "POST"])
@login_required
def add_item():
    if request.method == "POST":
        # Get all form fields
        name = request.form.get("name")
        item_type = request.form.get("type")
        rarity = request.form.get("rarity")
        base_price = request.form.get("base_price", type=float)
        description = request.form.get("description")
        shop_ids = request.form.getlist("shop_ids")
        stock = request.form.get("stock", type=int)
        dynamic_price = request.form.get("dynamic_price", type=float)
        
        #stock
        stock = request.form.get("stock", type=int)
        if stock is None:
            stock = 0

        #dynamic price
        dynamic_price = request.form.get("dynamic_price", type=float)
        if dynamic_price is None:
            dynamic_price = 0

        # Debug print statements
        print("DEBUG: Item Name:", name)
        print("DEBUG: Shop IDs:", shop_ids)
        print("DEBUG: Base Price:", base_price, "| Stock:", stock, "| Dyn Price:", dynamic_price)

        try:
            gm_profile_id = current_user.gm_profile.id
            print("DEBUG: GM Profile ID:", gm_profile_id)

            new_item = Item(
                name=name,
                type=item_type,
                rarity=rarity,
                base_price=base_price,
                description=description,
                gm_profile_id=gm_profile_id
            )

            db.session.add(new_item)
            db.session.flush()  # assign item_id to new_item

            for shop_id in shop_ids:
                try:
                    sid = int(shop_id)
                    print(f"[DEBUG] Linking to Shop ID: {sid}")
                    shop = Shop.query.filter_by(
                        shop_id=sid, gm_profile_id=gm_profile_id
                    ).first()
                    if shop:
                        print(f"[DEBUG] Found Shop: {shop.name}")
                        print(f"[DEBUG] Stock: {stock} | Dyn Price: {dynamic_price}")  # <-- Add this here
                        entry = ShopInventory(
                            shop_id=shop.shop_id,
                            item_id=new_item.item_id,
                            stock=stock,
                            dynamic_price=dynamic_price
                        )
                        db.session.add(entry)
                    else:
                        print(f"[WARNING] Shop ID {sid} not found.")
                except ValueError:
                    print(f"[ERROR] Invalid shop_id: {shop_id}")


            db.session.commit()
            flash(f"Item '{name}' added successfully!", "success")

        except Exception as e:
            db.session.rollback()
            import traceback
            print("[ERROR] Exception while adding item:")
            traceback.print_exc()
            flash(f"Error adding item: {e}", "danger")

        return redirect(url_for("gm.view_items"))

    grouped_shops = get_grouped_shops(current_user.gm_profile)
    return render_template("GM_add_item.html", grouped_shops=grouped_shops)


@gm_bp.route("/items/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    item = item_for_gm_or_404(item_id, current_user.gm_profile.id)
    
    if request.method == "POST":
        item.name = request.form.get("name")
        item.type = request.form.get("type")
        item.rarity = request.form.get("rarity")
        item.base_price = request.form.get("base_price")
        item.description = request.form.get("description")
        
        try:
            db.session.commit()
            flash("Item updated successfully!", "success")
            return redirect(url_for("gm.view_items"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating item: {e}", "danger")

    grouped_shops = get_grouped_shops(current_user.gm_profile)
    linked_shop_ids = get_linked_shop_ids_for_item(item.item_id)
    return render_template(
        "GM_edit_item.html",
        item=item,
        grouped_shops=grouped_shops,
        linked_shop_ids=linked_shop_ids,
    )

@gm_bp.route("/items/detail/<int:item_id>")
@login_required
def item_detail(item_id):
    item = item_for_gm_or_404(item_id, current_user.gm_profile.id)
    grouped_shops = get_grouped_shops(current_user.gm_profile)
    linked_shop_ids = get_linked_shop_ids_for_item(item.item_id)
    return render_template(
        "GM_item_detail.html",
        item=item,
        grouped_shops=grouped_shops,
        linked_shop_ids=linked_shop_ids,
    )

@gm_bp.route("/items/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    item = item_for_gm_or_404(item_id, current_user.gm_profile.id)
    try:
        db.session.delete(item)
        db.session.commit()
        flash("Item deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting item: {e}", "danger")
    return redirect(url_for("gm.view_items")) 

@gm_bp.route("/debug/form", methods=["POST"])
def gm_debug_form():
    return gm_debug_form_handler()


# Campaign routes
@gm_bp.route("/campaigns/")
@login_required
def view_campaigns():
    return list_campaigns()


@gm_bp.route("/campaigns/add", methods=["GET", "POST"])
@login_required
def add_campaign():
    return create_campaign()


@gm_bp.route("/campaigns/sync/<int:campaign_id>", methods=["POST"])
@login_required
def sync_players_to_campaign(campaign_id):
    return sync_players_to_campaign_handler(campaign_id)


@gm_bp.route("/campaigns/delete/<int:campaign_id>", methods=["POST"])
@login_required
def delete_campaign(campaign_id):
    return delete_campaign_handler(campaign_id)


# Simulation routes
@gm_bp.route("/simulation/tick", methods=["POST"])
@login_required
def gm_run_simulation_tick():
    """Execute one simulation tick manually from the GM dashboard"""
    return run_simulation_tick()

@gm_bp.route("/simulation/speed", methods=["POST"])
@login_required
def gm_update_simulation_speed():
    """Pause the simulation engine (period runs use the streaming endpoint)."""
    return update_simulation_speed()


@gm_bp.route("/simulation/run-period", methods=["POST"])
@login_required
def gm_simulation_run_period():
    """Run a simulation period as NDJSON (one line per game day)."""
    return run_period_stream()

@gm_bp.route("/simulation/jobs/<job_id>", methods=["GET"])
@login_required
def gm_simulation_job_status(job_id: str):
    """Return background simulation job status for polling UI."""
    return simulation_job_status(job_id)


# Player / Character management routes
@gm_bp.route("/players/")
@login_required
def gm_view_players():
    """List players and characters for the current campaign."""
    return list_players()


@gm_bp.route("/characters/<int:character_id>")
@login_required
def gm_view_character(character_id):
    """View and edit a specific character as GM."""
    return view_character(character_id)


@gm_bp.route("/characters/<int:character_id>/update", methods=["POST"])
@login_required
def gm_update_character(character_id):
    """Apply GM-side updates to a character."""
    return update_character(character_id)


@gm_bp.route("/characters/<int:character_id>/equip", methods=["POST"])
@login_required
def gm_equip_item_for_character(character_id):
    """Equip an item for a character (GM-side)."""
    return equip_item(character_id)


@gm_bp.route("/characters/<int:character_id>/unequip", methods=["POST"])
@login_required
def gm_unequip_item_for_character(character_id):
    """Unequip an item from a character slot (GM-side)."""
    return unequip_item(character_id)


@gm_bp.route("/characters/<int:character_id>/inventory/update", methods=["POST"])
@login_required
def gm_update_inventory_for_character(character_id):
    """Adjust a character's player inventory (GM-side)."""
    return update_inventory(character_id)


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
