from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.backend import City, Shop, Item, ShopInventory
from app.services.logging_config import gm_logger
from app.services.simulation import SimulationEngine
from datetime import datetime

gm_bp = Blueprint("gm", __name__, url_prefix="/gm")

# Initialize the simulation engine singleton
simulation_engine = SimulationEngine()

def _debug_request(request_type: str, route: str):
    """Debug helper for request logging."""
    gm_logger.debug(
        f"{request_type} request to {route}:\n"
        f"  Method: {request.method}\n"
        f"  Form data: {request.form}\n"
        f"  Args: {request.args}\n"
        f"  Current speed: {simulation_engine.current_speed}\n"
        f"  Last tick: {simulation_engine.last_tick_time}"
    )

@gm_bp.route("/")
@login_required
def home():
    """Render the GM dashboard with simulation controls and status."""
    _debug_request("GET", "/gm/")
    
    # Check if we should run a tick based on current speed
    if simulation_engine.should_run_tick():
        try:
            stats = simulation_engine.run_tick(current_user.gm_profile.id)
            flash(
                f"Simulation tick completed: Updated {stats['shops_updated']} shops "
                f"and {stats['items_updated']} items.",
                "success"
            )
        except Exception as e:
            flash(f"Error during simulation tick: {str(e)}", "danger")
    
    # Log current simulation state
    gm_logger.debug(
        f"GM dashboard state:\n"
        f"  User ID: {current_user.gm_profile.id}\n"
        f"  Current speed: {simulation_engine.current_speed}\n"
        f"  Last tick: {simulation_engine.last_tick_time}\n"
        f"  Time since last tick: {datetime.now() - simulation_engine.last_tick_time}"
    )
    
    return render_template(
        "GM_Home.html",
        current_tick=0,  # Will be stored in database
        current_speed=simulation_engine.current_speed,
        last_tick_time=simulation_engine.last_tick_time,
        simulation_status="active" if simulation_engine.current_speed != "pause" else "paused"
    )

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
    city = City.query.get_or_404(city_id)
    
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
    city = City.query.get_or_404(city_id)
    try:
        db.session.delete(city)
        db.session.commit()
        flash("City deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting city: {e}", "danger")
    return redirect(url_for("gm.view_cities"))

    #shops routes

@gm_bp.route("/shops/")
@login_required
def view_shops():
    shops = Shop.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_view_shops.html", shops=shops)

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
                    city = City.query.get(int(city_id))
                    if city:
                        new_shop.cities.append(city)
                    else:
                        print(f"[WARNING] City ID {city_id} not found.")
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
    shop = Shop.query.get_or_404(shop_id)
    
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

@gm_bp.route("/shops/delete/<int:shop_id>", methods=["POST"])
@login_required
def delete_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
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
    city = City.query.get_or_404(city_id)
    shops = city.shops
    return render_template("GM_view_city_shops.html", city=city, shops=shops)

@gm_bp.route("/shops/<int:shop_id>/items")
@login_required
def view_shop_items(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    city = shop.cities[0] if shop.cities else None
    shop_inventory = ShopInventory.query.filter_by(shop_id=shop_id).all()
    item_ids = [inv.item_id for inv in shop_inventory]
    items = Item.query.filter(Item.item_id.in_(item_ids)).all()
    return render_template("GM_view_shop_items.html", items=items, shop=shop, city=city)

@gm_bp.route("/shops/remove_item/<int:shop_id>/<int:item_id>", methods=["POST"])
@login_required
def remove_item_from_shop(shop_id, item_id):
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
                    shop = Shop.query.get(sid)
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

    # GET route: Load shops
    shops = Shop.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_add_item.html", shops=shops)


@gm_bp.route("/items/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    item = Item.query.get_or_404(item_id)
    
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

    return render_template("GM_edit_item.html", item=item)

@gm_bp.route("/items/detail/<int:item_id>")
@login_required
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)
    return render_template("GM_view_items.html", item=item)

@gm_bp.route("/items/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    try:
        db.session.delete(item)
        db.session.commit()
        flash("Item deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting item: {e}", "danger")
    return redirect(url_for("gm.view_items")) 

@gm_bp.route("/debug/form", methods=["POST"])
def debug_form():
    print("FORM KEYS:", request.form.keys())
    print("FORM DICT:", request.form.to_dict(flat=False))
    return "Check logs"

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

@gm_bp.route("/simulation/tick", methods=["POST"])
@login_required
def run_simulation_tick():
    """
    Execute one simulation tick manually from the GM dashboard.
    Redirects back to the dashboard with a flash message.
    """
    _debug_request("POST", "/gm/simulation/tick")
    
    try:
        stats = simulation_engine.run_tick(current_user.gm_profile.id)
        
        # Log the tick execution
        gm_logger.debug(
            f"Manual tick execution:\n"
            f"  User ID: {current_user.gm_profile.id}\n"
            f"  Shops updated: {stats['shops_updated']}\n"
            f"  Items updated: {stats['items_updated']}\n"
            f"  Last tick time: {simulation_engine.last_tick_time}\n"
            f"  Time since last tick: {datetime.now() - simulation_engine.last_tick_time}"
        )
        
        return jsonify({
            "status": "success",
            "message": f"Simulation tick completed: Updated {stats['shops_updated']} shops and {stats['items_updated']} items.",
            "stats": stats
        })
        
    except Exception as e:
        gm_logger.error(f"Error during simulation tick: {str(e)}")
        flash(f"Error during simulation tick: {str(e)}", "danger")
    
    return redirect(url_for("gm.home"))

@gm_bp.route("/simulation/speed", methods=["POST"])
@login_required
def update_simulation_speed():
    """
    Update the simulation speed setting and run the appropriate time period.
    """
    _debug_request("POST", "/gm/simulation/speed")
    
    try:
        speed = request.form.get("speed", "pause")
        
        # Map speed to time period
        speed_to_period = {
            "1x": "hour",
            "5x": "day",
            "100x": "week",
            "1000x": "month"
        }
        
        if speed == "pause":
            simulation_engine.set_speed(speed)
            flash("Simulation paused", "info")
        else:
            time_period = speed_to_period.get(speed)
            if not time_period:
                raise ValueError(f"Invalid speed setting: {speed}")
                
            # Run the simulation for the selected time period
            stats = simulation_engine.run_time_period(current_user.gm_profile.id, time_period)
            
            # Log the simulation results
            gm_logger.debug(
                f"Time period simulation completed:\n"
                f"  Period: {time_period}\n"
                f"  Ticks completed: {stats['ticks_completed']}\n"
                f"  Shops updated: {stats['shops_updated']}\n"
                f"  Items updated: {stats['items_updated']}\n"
                f"  Duration: {stats['total_duration']:.2f}s"
            )
            
            flash(
                f"Simulated {time_period}: Updated {stats['shops_updated']} shops "
                f"and {stats['items_updated']} items in {stats['total_duration']:.2f}s",
                "success"
            )
        
    except Exception as e:
        gm_logger.error(f"Error during simulation: {str(e)}")
        flash(f"Error during simulation: {str(e)}", "danger")
    
    return redirect(url_for("gm.home"))
