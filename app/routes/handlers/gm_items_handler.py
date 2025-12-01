"""
GM Items Handler
Handles all item-related business logic for GM routes
"""
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.extensions import db
from app.models.backend import Shop, Item, ShopInventory
from app.services.logging_config import gm_logger
import json
from collections import defaultdict


def group_shops_for_display(shops):
    """
    Groups shops by City -> Shop Type -> List of Shops
    
    Args:
        shops: List of Shop objects (must have cities relationship and type attribute)
    
    Returns:
        dict: Nested dictionary structure: {city_name: {shop_type: [shop1, shop2, ...]}}
    """
    grouped = defaultdict(lambda: defaultdict(list))
    
    for shop in shops:
        # A shop can be in multiple cities
        for city in shop.cities:
            city_name = city.name
            shop_type = shop.type
            grouped[city_name][shop_type].append(shop)
    
    # Convert defaultdict to regular dict for template rendering
    return {city: dict(types) for city, types in grouped.items()}


def view_items():
    """View all items for the current GM"""
    items = Item.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_view_items.html", items=items)


def add_item():
    """Add a new item"""
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
        
        # New universal fields
        weight = request.form.get("weight", type=float)
        is_magic = request.form.get("is_magic") == "on"  # Checkbox returns "on" if checked
        properties_json_str = request.form.get("properties_json", "").strip()
        
        #stock
        stock = request.form.get("stock", type=int)
        if stock is None:
            stock = 0

        #dynamic price
        dynamic_price = request.form.get("dynamic_price", type=float)
        if dynamic_price is None:
            dynamic_price = 0

        # Validate and parse properties_json
        properties_json = None
        if properties_json_str:
            try:
                # Validate JSON by parsing it
                json.loads(properties_json_str)
                properties_json = properties_json_str
            except json.JSONDecodeError:
                flash("Invalid JSON in properties field. Please check your JSON syntax.", "warning")
                properties_json = None

        # Debug print statements
        print("DEBUG: Item Name:", name)
        print("DEBUG: Shop IDs:", shop_ids)
        print("DEBUG: Base Price:", base_price, "| Stock:", stock, "| Dyn Price:", dynamic_price)
        print("DEBUG: Weight:", weight, "| Is Magic:", is_magic)

        try:
            gm_profile_id = current_user.gm_profile.id
            print("DEBUG: GM Profile ID:", gm_profile_id)

            new_item = Item(
                name=name,
                type=item_type,
                rarity=rarity,
                base_price=base_price,
                description=description,
                weight=weight,
                is_magic=is_magic,
                properties_json=properties_json,
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

        return redirect(url_for("gm.gm_view_items"))

    # GET route: Load shops and group them
    shops = Shop.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    grouped_shops = group_shops_for_display(shops)
    return render_template("GM_add_item.html", shops=shops, grouped_shops=grouped_shops)


def edit_item(item_id):
    """Edit an existing item"""
    item = Item.query.get_or_404(item_id)
    
    if request.method == "POST":
        item.name = request.form.get("name")
        item.type = request.form.get("type")
        item.rarity = request.form.get("rarity")
        base_price = request.form.get("base_price", type=float)
        if base_price is not None:
            item.base_price = base_price
        item.description = request.form.get("description")
        
        # Update new universal fields
        weight = request.form.get("weight", type=float)
        item.weight = weight if weight is not None else None
        item.is_magic = request.form.get("is_magic") == "on"  # Checkbox returns "on" if checked
        
        # Handle properties_json
        properties_json_str = request.form.get("properties_json", "").strip()
        if properties_json_str:
            try:
                # Validate JSON by parsing it
                json.loads(properties_json_str)
                item.properties_json = properties_json_str
            except json.JSONDecodeError:
                flash("Invalid JSON in properties field. Item updated but properties_json was not changed.", "warning")
        else:
            item.properties_json = None
        
        try:
            db.session.commit()
            flash("Item updated successfully!", "success")
            return redirect(url_for("gm.gm_view_items"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating item: {e}", "danger")

    # GET route: Load shops and determine which shops have this item
    shops = Shop.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    grouped_shops = group_shops_for_display(shops)
    linked_shop_ids = [inv.shop_id for inv in item.inventory if inv.shop_id]
    return render_template("GM_edit_item.html", item=item, shops=shops, grouped_shops=grouped_shops, linked_shop_ids=linked_shop_ids)


def item_detail(item_id):
    """View detailed information about an item"""
    item = Item.query.get_or_404(item_id)
    return render_template("GM_view_items.html", item=item)


def delete_item(item_id):
    """Delete an item"""
    item = Item.query.get_or_404(item_id)
    try:
        db.session.delete(item)
        db.session.commit()
        flash("Item deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting item: {e}", "danger")
    return redirect(url_for("gm.gm_view_items"))
