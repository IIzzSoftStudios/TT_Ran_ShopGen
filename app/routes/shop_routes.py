from flask import Blueprint, render_template, request, redirect, flash, url_for
from app.models import Shop, City, ShopInventory, shop_cities
from app.extensions import db
from sqlalchemy.orm import joinedload

shop_bp = Blueprint("shop", __name__)

@shop_bp.route("/")
def view_all_shops():
    shops = Shop.query.all()
    return render_template("view_shops.html", shops=shops)

@shop_bp.route("/city_shops/<int:city_id>")
def city_shops(city_id):
    city = City.query.get_or_404(city_id)
    
    # Correct query for many-to-many relationship
    shops = Shop.query.join(shop_cities).filter(shop_cities.c.city_id == city_id).all()

    return render_template("city_shops.html", city=city, shops=shops)

@shop_bp.route("/add_shop", methods=["GET", "POST"])
def add_shop():
    cities = City.query.all()  # Fetch all cities

    if request.method == "POST":
        print("\n=== DEBUG: FORM SUBMISSION ===")
        print("Received Form Data:", request.form)

        name = request.form.get("name")
        shop_type = request.form.get("type")
        city_ids = request.form.getlist("cities")  # Retrieve list of selected cities

        print("Shop Name:", name)
        print("Shop Type:", shop_type)
        print("Selected city IDs:", city_ids)

        if not name or not shop_type:
            flash("Shop name and type are required!", "danger")
            return render_template("add_shop.html", cities=cities)

        try:
            # Create new shop and add to DB
            new_shop = Shop(name=name, type=shop_type)
            db.session.add(new_shop)
            db.session.flush()  # Ensure shop_id is generated

            # Associate shop with selected cities
            for city_id in city_ids:
                city = City.query.get(int(city_id))
                if city:
                    print(f"Associating {new_shop.name} with {city.name}")  # Debugging
                    new_shop.cities.append(city)

            db.session.commit()  # Commit shop + relationships
            flash(f"Shop '{name}' added successfully!", "success")
            return redirect(url_for("shop.view_all_shops"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error adding shop: {e}", "danger")
            print(f"Error: {e}")

    return render_template("add_shop.html", cities=cities)




@shop_bp.route("/edit_shop/<int:shop_id>", methods=["GET", "POST"])
def edit_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    cities = City.query.all()  # Fetch all cities

    if request.method == "POST":
        shop.name = request.form.get("name")
        shop.type = request.form.get("type")
        shop.city_id = request.form.get('city_id')
        selected_city_ids = request.form.getlist("city_ids")  # Multiple selection

        if not shop.name or not shop.type:
            flash("Shop name and type are required!", "danger")
            return render_template("edit_shop.html", shop=shop, cities=cities)

        try:
            # Clear old city-shop relationships
            db.session.execute(shop_cities.delete().where(shop_cities.c.shop_id == shop_id))

            # Add new relationships
            for city_id in selected_city_ids:
                db.session.execute(shop_cities.insert().values(shop_id=shop_id, city_id=int(city_id)))

            db.session.commit()
            flash(f"Shop '{shop.name}' updated successfully!", "success")
            return redirect(url_for("shop.view_all_shops"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating shop: {e}", "danger")

    return render_template("edit_shop.html", shop=shop, cities=cities)

@shop_bp.route("/delete_shop/<int:shop_id>", methods=["POST"])
def delete_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)

    try:
        # Remove shop-city links first
        db.session.execute(shop_cities.delete().where(shop_cities.c.shop_id == shop_id))

        # Delete the shop itself
        db.session.delete(shop)
        db.session.commit()
        flash(f"Shop '{shop.name}' deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting shop: {e}", "danger")

    return redirect(url_for("shop.view_all_shops"))
