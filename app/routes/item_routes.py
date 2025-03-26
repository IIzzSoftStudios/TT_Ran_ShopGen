import logging
from flask import Blueprint, render_template, request, redirect, flash, url_for
from flask_login import login_required, current_user
from app.models import Item, Shop, ShopInventory
from app.extensions import db

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

item_bp = Blueprint("item", __name__)

# View All Items
@item_bp.route("/", methods=["GET"])
@login_required
def view_all_items():
    items = Item.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()  # Fetch all items for current GM
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
    return render_template("GM_view_shop_items.html", items=items, shop=shop, city=city)


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
        stock = request.form.get("stock", default=10, type=int)  # Default stock
        dynamic_price = request.form.get("dynamic_price", default=base_price, type=float)

        # Validate required fields
        if not name or not item_type or not rarity or not base_price:
            flash("All fields except description are required!", "danger")
            return redirect(url_for("item.add_new_item"))

        try:
            with db.session.begin():  # Ensure atomic transaction
                # Create new item
                new_item = Item(
                    name=name,
                    type=item_type,
                    rarity=rarity,
                    base_price=base_price,
                    description=description,
                    gm_profile_id=current_user.gm_profile.id  # Add the GM profile ID
                )
                db.session.add(new_item)
                db.session.flush()  # Ensure item_id is generated

                # Link item to selected shops through ShopInventory
                for shop_id in shop_ids:
                    shop = Shop.query.get(shop_id)
                    if shop:
                        new_inventory_entry = ShopInventory(
                            shop_id=shop.shop_id,
                            item_id=new_item.item_id,
                            stock=stock,
                            dynamic_price=dynamic_price
                        )
                        db.session.add(new_inventory_entry)

            db.session.commit()
            flash(f"Item '{name}' added successfully!", "success")

        except Exception as e:
            db.session.rollback()
            flash(f"Error adding item: {e}", "danger")

        return redirect(url_for("item.view_all_items"))

    shops = Shop.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
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
    shops = Shop.query.all()  # Fetch all shops
    linked_shop_ids = [inv.shop_id for inv in ShopInventory.query.filter_by(item_id=item_id).all()]

    if request.method == "POST":
        try:
            # Update item details
            item.name = request.form.get("name")
            item.type = request.form.get("type")
            item.rarity = request.form.get("rarity")
            item.base_price = request.form.get("base_price")

            # Get selected shops from the form
            selected_shop_ids = request.form.getlist("shop_ids[]")
            selected_shop_ids = [int(shop_id) for shop_id in selected_shop_ids]  # Convert to integers

            # Remove existing shop links
            ShopInventory.query.filter_by(item_id=item_id).delete()

            # Add new shop links
            for shop_id in selected_shop_ids:
                new_inventory_entry = ShopInventory(
                    shop_id=shop_id, item_id=item.item_id, stock=10, dynamic_price=item.base_price
                )
                db.session.add(new_inventory_entry)

            db.session.commit()
            flash(f"Item '{item.name}' updated successfully!", "success")

            return redirect(url_for("item.view_all_items"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating item: {e}", "danger")

    return render_template("GM_edit_item.html", item=item, shops=shops, linked_shop_ids=linked_shop_ids)


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
@login_required
def delete_item(item_id):
    item = Item.query.get_or_404(item_id)
    
    try:
        # Delete all shop inventory references first
        ShopInventory.query.filter_by(item_id=item_id).delete()
        db.session.commit()

        # Now delete the item itself
        db.session.delete(item)
        db.session.commit()

        logger.debug(f"Item {item_id} and related inventory entries deleted successfully.")
        flash(f"Item '{item.name}' deleted successfully!", "success")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting item {item_id}: {e}")
        flash(f"Error deleting item: {e}", "danger")

    return redirect(url_for("item.view_all_items"))
