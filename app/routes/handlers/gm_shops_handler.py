"""
GM Shops Handler
Handles all shop-related business logic for GM routes
"""
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.extensions import db
from app.models.backend import City, Shop, Item, ShopInventory
from app.services.logging_config import gm_logger


def view_shops():
    """View all shops for the current GM"""
    shops = Shop.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_view_shops.html", shops=shops)


def add_shop():
    """Add a new shop"""
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
            import traceback
            traceback.print_exc()
            flash(f"Error adding shop: {e}", "danger")

        return redirect(url_for("gm.gm_view_shops"))

    # GET request: render form
    cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_add_shop.html", cities=cities)


def edit_shop(shop_id):
    """Edit an existing shop"""
    shop = Shop.query.get_or_404(shop_id)
    
    if request.method == "POST":
        shop.name = request.form["name"]
        shop.type = request.form["type"]
        try:
            db.session.commit()
            flash("Shop updated successfully!", "success")
            return redirect(url_for("gm.gm_view_shops"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating shop: {e}", "danger")

    cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_edit_shop.html", shop=shop, cities=cities)


def delete_shop(shop_id):
    """Delete a shop"""
    shop = Shop.query.get_or_404(shop_id)
    try:
        db.session.delete(shop)
        db.session.commit()
        flash("Shop deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting shop: {e}", "danger")
    return redirect(url_for("gm.gm_view_shops"))


def view_city_shops(city_id):
    """View all shops in a specific city"""
    city = City.query.get_or_404(city_id)
    shops = city.shops
    return render_template("GM_view_city_shops.html", city=city, shops=shops)


def view_shop_items(shop_id):
    """View all items in a specific shop"""
    shop = Shop.query.get_or_404(shop_id)
    city = shop.cities[0] if shop.cities else None
    shop_inventory = ShopInventory.query.filter_by(shop_id=shop_id).all()
    item_ids = [inv.item_id for inv in shop_inventory]
    items = Item.query.filter(Item.item_id.in_(item_ids)).all()
    return render_template("GM_view_shop_items.html", items=items, shop=shop, city=city)


def remove_item_from_shop(shop_id, item_id):
    """Remove an item from a shop's inventory"""
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
    return redirect(url_for("gm.gm_view_shop_items", shop_id=shop_id))
