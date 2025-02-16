import logging
from flask import Blueprint, render_template, request, redirect, flash, url_for
from app.models import Item, Shop, ShopInventory
from app.extensions import db

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

item_bp = Blueprint("item", __name__)

# View All Items
@item_bp.route("/", methods=["GET"])
def view_all_items():
    items = Item.query.all()  # Fetch all items
    logger.debug(f"Fetched {len(items)} items from the database.")
    return render_template("GM_view_items.html", items=items)

@item_bp.route("/<int:shop_id>", methods=["GET"])
def view_items_by_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    city = shop.city

    # Fetch items linked to the shop through ShopInventory
    shop_inventory = ShopInventory.query.filter_by(shop_id=shop_id).all()

    # Fetch corresponding items
    item_ids = [inv.item_id for inv in shop_inventory]
    items = Item.query.filter(Item.item_id.in_(item_ids)).all()

    logger.debug(f"Shop ID: {shop_id}, Items in Shop: {len(items)}")
    return render_template("view_shop_items.html", items=items, shop=shop, city=city)


# Add a New Item
@item_bp.route("/add_new_item", methods=["GET", "POST"])
def add_new_item():
    if request.method == "POST":
        # Gather form data
        name = request.form.get("name")
        item_type = request.form.get("type")
        rarity = request.form.get("rarity")
        base_price = request.form.get("base_price")
        description = request.form.get("description")
        shop_ids = request.form.getlist("shop_ids[]")  # List of selected shops

        logger.debug(f"Form Data - Name: {name}, Type: {item_type}, Rarity: {rarity}, Base Price: {base_price}, Shop IDs: {shop_ids}")

        # Validate required fields
        if not name or not item_type or not rarity or not base_price:
            flash("All fields except description are required!", "danger")
            logger.warning("Validation failed: Missing required fields.")
            return redirect(request.referrer)

        try:
            # Create the new item
            new_item = Item(
                name=name,
                type=item_type,
                rarity=rarity,
                base_price=int(base_price),
                description=description,
            )
            db.session.add(new_item)
            db.session.commit()  # Commit to generate item_id

            logger.debug(f"Item created successfully with ID {new_item.item_id}")

            # Link the new item to selected shops
            if shop_ids:
                for shop_id in shop_ids:
                    try:
                        logger.debug(f"Attempting to add Item {new_item.item_id} to Shop {shop_id}")
                        shop_inventory = ShopInventory(shop_id=int(shop_id), item_id=new_item.item_id, stock=10)
                        db.session.add(shop_inventory)
                    except Exception as e:
                        logger.error(f"Error linking item {new_item.item_id} to shop {shop_id}: {e}")

                db.session.commit()
                logger.debug("Item successfully linked to selected shops.")
            else:
                logger.warning("No shops were selected for linking.")

            flash(f"Item '{name}' added successfully and linked to selected shops!", "success")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding item: {e}")
            flash(f"Error adding item: {e}", "danger")

        return redirect(url_for("item.view_all_items"))

    # Fetch all shops
    shops = Shop.query.all()
    logger.debug(f"Fetched {len(shops)} shops for item linking.")
    return render_template("GM_add_item.html", shops=shops)

# Add Items to a Shop
@item_bp.route("/add_item/<int:shop_id>", methods=["GET", "POST"])
def add_items_to_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    items = Item.query.all()

    if request.method == "POST":
        selected_item_ids = request.form.getlist("item_ids")

        if not selected_item_ids:
            flash("You must select at least one item!", "danger")
            logger.warning(f"No items were selected for Shop {shop_id}")
            return render_template("add_item.html", shop=shop, items=items)

        try:
            for item_id in selected_item_ids:
                existing_inventory = ShopInventory.query.filter_by(shop_id=shop_id, item_id=item_id).first()
                if not existing_inventory:
                    new_inventory = ShopInventory(shop_id=shop_id, item_id=item_id, stock=0)
                    db.session.add(new_inventory)
                    logger.debug(f"Added Item {item_id} to Shop {shop_id}")
            db.session.commit()

            flash("Items successfully added to the shop!", "success")
            return redirect(url_for("shop.city_shops", city_id=shop.city_id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding items to shop: {e}")
            flash(f"Error adding items to shop: {e}", "danger")

    return render_template("GM_add_item.html", shop=shop, items=items)

# Edit an Item
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
            logger.debug(f"Item {item_id} updated successfully.")
            flash(f"Item '{item.name}' updated successfully!", "success")
            return redirect(url_for("item.view_all_items"))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating item {item_id}: {e}")
            flash(f"Error updating item: {e}", "danger")

    return render_template("GM_edit_item.html", item=item)

# Item Detail
@item_bp.route("/detail/<int:item_id>", methods=["GET", "POST"])
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)

    if request.method == "POST":
        item.range = request.form.get("range")
        item.damage = request.form.get("damage")
        item.rate_of_fire = request.form.get("rate_of_fire")
        item.min_str = request.form.get("min_str") or "N/A"
        item.notes = request.form.get("notes")

        try:
            db.session.commit()
            logger.debug(f"Details updated for Item {item_id}.")
            flash(f"Details for '{item.name}' updated successfully!", "success")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating item details {item_id}: {e}")
            flash(f"Error updating item details: {e}", "danger")

    return render_template("GM_item_detail.html", item=item)

# Delete an Item
@item_bp.route("/delete_item/<int:item_id>", methods=["POST"])
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    try:
        db.session.delete(item)
        db.session.commit()
        logger.debug(f"Item {item_id} deleted successfully.")
        flash(f"Item '{item.name}' deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting item {item_id}: {e}")
        flash(f"Error deleting item: {e}", "danger")
    return redirect(url_for("item.view_all_items"))
