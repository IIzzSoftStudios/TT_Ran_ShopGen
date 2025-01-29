from flask import Blueprint, render_template, request, redirect, flash, url_for
from app.models import Item, Shop, ShopInventory
from app.extensions import db

item_bp = Blueprint("item", __name__)

# View All Items (without shop filtering)
@item_bp.route("/", methods=["GET"])
def view_all_items():
    items = Item.query.all()  # Fetch all items in the database
    return render_template("view_items.html", items=items)


@item_bp.route("/<int:shop_id>", methods=["GET"])
def view_items_by_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)  # Fetch the shop by its ID
    city = shop.city  # Get the city the shop belongs to
    items = Item.query.filter_by(shop_id=shop_id).all()  # Fetch items for the shop
    return render_template("view_shop_items.html", items=items, shop=shop, city=city)

@item_bp.route("/add_new_item", methods=["GET", "POST"])
def add_new_item():
    if request.method == "POST":
        # Gather data from the form
        name = request.form.get("name")
        item_type = request.form.get("type")
        rarity = request.form.get("rarity")
        base_price = request.form.get("base_price")
        description = request.form.get("description")

        # Validate data
        if not name or not item_type or not rarity or not base_price:
            flash("All fields except description are required!", "danger")
            return redirect(request.referrer)

        # Add the new item
        try:
            new_item = Item(
                name=name,
                type=item_type,
                rarity=rarity,
                base_price=int(base_price),
                description=description,
            )
            db.session.add(new_item)
            db.session.commit()
            flash(f"Item '{name}' added successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding item: {e}", "danger")

        return redirect(url_for("item.view_all_items"))

    # Pass `shop=None` to the template when not adding an item to a specific shop
    return render_template("add_item.html", shop=None)


@item_bp.route("/add_item/<int:shop_id>", methods=["GET", "POST"])
def add_items_to_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)  # Fetch the shop
    items = Item.query.all()  # Get all items from the database

    if request.method == "POST":
        # Get selected items from the form
        selected_item_ids = request.form.getlist("item_ids")

        if not selected_item_ids:
            flash("You must select at least one item!", "danger")
            return render_template("add_item.html", shop=shop, items=items)

        try:
            # Add items to the shop's inventory
            for item_id in selected_item_ids:
                # Check if the item is already in the shop's inventory
                existing_inventory = ShopInventory.query.filter_by(shop_id=shop_id, item_id=item_id).first()
                if not existing_inventory:
                    new_inventory = ShopInventory(shop_id=shop_id, item_id=item_id, stock=0)  # Default stock = 0
                    db.session.add(new_inventory)
            db.session.commit()

            flash("Items successfully added to the shop!", "success")
            return redirect(url_for("shop.city_shops", city_id=shop.city_id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding items to shop: {e}", "danger")

    return render_template("add_item.html", shop=shop, items=items)


@item_bp.route("/edit_item/<int:item_id>", methods=["GET", "POST"])
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
            flash(f"Item '{item.name}' updated successfully!", "success")
            return redirect(url_for("item.view_all_items"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating item: {e}", "danger")

    return render_template("edit_item.html", item=item)

@item_bp.route("/detail/<int:item_id>", methods=["GET", "POST"])
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)  # Get the item by ID

    # Handle form submission for editing details
    if request.method == "POST":
        item.range = request.form.get("range")
        item.damage = request.form.get("damage")
        item.rate_of_fire = request.form.get("rate_of_fire")
        item.min_str = request.form.get("min_str") or "N/A"  # Default to "N/A" if empty
        item.notes = request.form.get("notes")

        try:
            db.session.commit()
            flash(f"Details for '{item.name}' updated successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating item details: {e}", "danger")

    return render_template("item_detail.html", item=item)

@item_bp.route("/delete_item/<int:item_id>", methods=["POST"])
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    try:
        db.session.delete(item)
        db.session.commit()
        flash(f"Item '{item.name}' deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting item: {e}", "danger")
    return redirect(url_for("item.view_all_items"))

