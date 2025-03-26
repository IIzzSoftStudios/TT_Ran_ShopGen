from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import db, City, Shop, Item, ShopInventory

gm_bp = Blueprint("gm", __name__, url_prefix="/gm")

@gm_bp.route("/")
@login_required
def home():
    return render_template("GM_Home.html")

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

@gm_bp.route("/shops/")
@login_required
def view_shops():
    shops = Shop.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_view_shops.html", shops=shops)

@gm_bp.route("/shops/add", methods=["GET", "POST"])
@login_required
def add_shop():
    if request.method == "POST":
        shop_name = request.form["name"]
        shop_type = request.form["type"]
        city_ids = request.form.getlist("city_ids")

        try:
            with db.session.begin():
                new_shop = Shop(
                    name=shop_name,
                    type=shop_type,
                    gm_profile_id=current_user.gm_profile.id
                )
                db.session.add(new_shop)
                db.session.flush()

                for city_id in city_ids:
                    city = City.query.get(city_id)
                    if city:
                        new_shop.cities.append(city)

            flash(f"Shop '{shop_name}' added successfully!", "success")
        except Exception as e:
            flash(f"Error adding shop: {e}", "danger")

        return redirect(url_for("gm.view_shops"))

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

@gm_bp.route("/items/")
@login_required
def view_items():
    items = Item.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    return render_template("GM_view_items.html", items=items)

@gm_bp.route("/items/add", methods=["GET", "POST"])
@login_required
def add_item():
    if request.method == "POST":
        name = request.form.get("name")
        item_type = request.form.get("type")
        rarity = request.form.get("rarity")
        base_price = request.form.get("base_price")
        description = request.form.get("description")
        shop_ids = request.form.getlist("shop_ids")
        stock = request.form.get("stock", type=int)
        dynamic_price = request.form.get("dynamic_price", type=float)

        try:
            with db.session.begin():
                new_item = Item(
                    name=name,
                    type=item_type,
                    rarity=rarity,
                    base_price=base_price,
                    description=description,
                    gm_profile_id=current_user.gm_profile.id
                )
                db.session.add(new_item)
                db.session.flush()

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

        return redirect(url_for("gm.view_items"))

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
    return render_template("GM_item_detail.html", item=item)

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