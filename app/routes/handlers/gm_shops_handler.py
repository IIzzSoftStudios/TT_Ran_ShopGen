"""
GM Shops Handler
Handles all shop-related business logic for GM routes
"""
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import subqueryload

from app.constants.shops import SHOP_TYPE_DEFAULTS
from app.extensions import db
from app.models.backend import City, Shop, Item, ShopInventory
from app.services.logging_config import gm_logger
from app.routes.handlers.gm_helpers import get_current_gm_profile
from collections import defaultdict


def _normalize_shop_type(raw):
    """Strip and title-case shop type for consistent grouping and display."""
    if raw is None:
        return ""
    return str(raw).strip().title()


def _normalize_shop_name(raw):
    if raw is None:
        return ""
    return str(raw).strip()


def group_cities_for_display(cities):
    """
    Groups cities by Region -> Size -> List of Cities
    
    Args:
        cities: List of City objects (must have region, size, and name attributes)
    
    Returns:
        dict: Nested dictionary structure: {region: {size: [city1, city2, ...]}}
    """
    grouped = defaultdict(lambda: defaultdict(list))
    
    for city in cities:
        region = city.region or "Unspecified"
        size = city.size or "Unspecified"
        grouped[region][size].append(city)
    
    # Convert defaultdict to regular dict for template rendering
    return {region: dict(sizes) for region, sizes in grouped.items()}


def get_shop_city_panel_context(gm_profile):
    """
    Build city_data and type_suggestions for the nested shops-by-city UI.
    Used by GM View Shops and the GM Home dashboard.
    """
    cities = (
        City.query.filter_by(gm_profile_id=gm_profile.id)
        .options(subqueryload(City.shops))
        .order_by(City.name)
        .all()
    )

    discovered_rows = (
        db.session.query(Shop.type)
        .filter_by(gm_profile_id=gm_profile.id)
        .distinct()
        .all()
    )
    discovered_normalized = {
        _normalize_shop_type(row[0]) for row in discovered_rows if row[0]
    }
    discovered_normalized.discard("")
    type_suggestions = sorted(SHOP_TYPE_DEFAULTS | discovered_normalized)

    city_data = []
    for city in cities:
        by_type = {}
        for shop in sorted(city.shops, key=lambda s: (s.name or "").lower()):
            type_key = _normalize_shop_type(shop.type) or "Unspecified"
            by_type.setdefault(type_key, []).append(shop)
        shop_type_rows = [
            {
                "type": type_key,
                "count": len(shops),
                "shops": sorted(shops, key=lambda s: (s.name or "").lower()),
            }
            for type_key, shops in by_type.items()
        ]
        shop_type_rows.sort(key=lambda r: (-r["count"], r["type"].lower()))
        city_data.append(
            {
                "city": city,
                "shop_count": len(city.shops),
                "shop_type_rows": shop_type_rows,
            }
        )

    return {"city_data": city_data, "type_suggestions": type_suggestions}


def view_shops():
    """View shops grouped by city for nested card UI."""
    try:
        gm_profile, redirect_response = get_current_gm_profile()
        if redirect_response:
            return redirect_response
        gm_logger.info(f"view_shops called for user: {current_user.username}, GM Profile ID: {gm_profile.id}")

        ctx = get_shop_city_panel_context(gm_profile)
        gm_logger.info(
            f"view_shops: {len(ctx['city_data'])} cities, {len(ctx['type_suggestions'])} type suggestions"
        )
        return render_template(
            "GM_view_shops.html",
            **ctx,
        )
    except Exception as e:
        gm_logger.error(f"Error in view_shops: {str(e)}", exc_info=True)
        flash(f"Error loading shops: {str(e)}", "danger")
        return redirect(url_for("gm.gm_home"))


def add_shop():
    """Add a new shop"""
    if request.method == "POST":
        shop_name = _normalize_shop_name(request.form.get("name"))
        shop_type = _normalize_shop_type(request.form.get("type"))
        city_ids = request.form.getlist("city_ids")

        print("DEBUG: Shop Name:", shop_name)
        print("DEBUG: Shop Type:", shop_type)
        print("DEBUG: City IDs:", city_ids)

        gm_profile, redirect_response = get_current_gm_profile()
        if redirect_response:
            return redirect_response

        if not shop_name or not shop_type:
            flash("Shop name and type are required.", "warning")
            return redirect(url_for("gm.gm_add_shop"))
        
        try:
            gm_profile_id = gm_profile.id
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
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    cities = City.query.filter_by(gm_profile_id=gm_profile.id).all()
    return render_template("GM_add_shop.html", cities=cities)


def edit_shop(shop_id):
    """Edit an existing shop"""
    shop = Shop.query.get_or_404(shop_id)
    
    if request.method == "POST":
        shop.name = _normalize_shop_name(request.form.get("name"))
        shop.type = _normalize_shop_type(request.form.get("type"))
        if not shop.name or not shop.type:
            flash("Name and type are required.", "warning")
            return redirect(url_for("gm.gm_edit_shop", shop_id=shop_id))

        # Handle city associations
        city_ids = request.form.getlist("city_ids")
        # Get current city associations
        current_city_ids = {city.city_id for city in shop.cities}
        new_city_ids = {int(cid) for cid in city_ids if cid}
        
        # Remove cities that are no longer selected
        for city in shop.cities[:]:  # Use slice to create a copy for iteration
            if city.city_id not in new_city_ids:
                shop.cities.remove(city)
        
        # Add new city associations
        for city_id in new_city_ids:
            if city_id not in current_city_ids:
                city = City.query.get(city_id)
                if city:
                    shop.cities.append(city)
        
        try:
            db.session.commit()
            flash("Shop updated successfully!", "success")
            return redirect(url_for("gm.gm_view_shops"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating shop: {e}", "danger")

    # GET route: Load cities and determine which cities have this shop
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    cities = City.query.filter_by(gm_profile_id=gm_profile.id).all()
    grouped_cities = group_cities_for_display(cities)
    linked_city_ids = [city.city_id for city in shop.cities]
    return render_template("GM_edit_shop.html", shop=shop, cities=cities, grouped_cities=grouped_cities, linked_city_ids=linked_city_ids)


def update_shop_basic(shop_id):
    """Update shop name and type only; preserves city M2M links."""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    shop = Shop.query.get_or_404(shop_id)
    if shop.gm_profile_id != gm_profile.id:
        flash("You don't have permission to update this shop.", "danger")
        return redirect(url_for("gm.gm_view_shops"))

    new_name = _normalize_shop_name(request.form.get("name"))
    new_type = _normalize_shop_type(request.form.get("type"))

    if not new_name or not new_type:
        flash("Name and type are required.", "warning")
        return redirect(url_for("gm.gm_view_shops"))

    try:
        shop.name = new_name
        shop.type = new_type
        db.session.commit()
        flash(f"Updated {shop.name}.", "success")
    except Exception as e:
        db.session.rollback()
        gm_logger.error(f"update_shop_basic failed: {e}", exc_info=True)
        flash(f"Error updating shop: {e}", "danger")

    return redirect(url_for("gm.gm_view_shops"))


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
    try:
        gm_logger.info(f"view_shop_items called for shop_id: {shop_id}, user: {current_user.username}")
        
        shop = Shop.query.get_or_404(shop_id)
        gm_logger.info(f"Shop found: {shop.name} (ID: {shop.shop_id}), GM Profile ID: {shop.gm_profile_id}")
        
        # Verify shop belongs to current user's GM profile
        gm_profile, redirect_response = get_current_gm_profile()
        if redirect_response:
            return redirect_response
        if shop.gm_profile_id != gm_profile.id:
            gm_logger.warning(f"Access denied: Shop {shop_id} does not belong to user {current_user.username}")
            flash("You don't have permission to view this shop.", "danger")
            return redirect(url_for("gm.gm_view_shops"))
        
        city = shop.cities[0] if shop.cities else None
        gm_logger.info(f"City: {city.name if city else 'None'}")
        
        shop_inventory = ShopInventory.query.filter_by(shop_id=shop_id).all()
        gm_logger.info(f"Found {len(shop_inventory)} inventory entries")
        
        item_ids = [inv.item_id for inv in shop_inventory]
        items = Item.query.filter(Item.item_id.in_(item_ids)).all() if item_ids else []
        gm_logger.info(f"Found {len(items)} items")
        
        # Log inventory details
        for inv in shop_inventory:
            gm_logger.debug(f"Inventory entry: item_id={inv.item_id}, stock={inv.stock}, price={inv.dynamic_price}")
        
        gm_logger.info(f"Rendering template GM_view_shop_items.html with shop_id={shop_id}")
        return render_template("GM_view_shop_items.html", items=items, shop=shop, city=city)
        
    except Exception as e:
        gm_logger.error(f"Error in view_shop_items for shop_id {shop_id}: {str(e)}", exc_info=True)
        flash(f"Error loading shop items: {str(e)}", "danger")
        return redirect(url_for("gm.gm_view_shops"))


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
