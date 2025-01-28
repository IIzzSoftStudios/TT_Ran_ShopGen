from flask import Blueprint, render_template, request, redirect, flash, url_for
from app.models import Shop, City
from app.extensions import db

shop_bp = Blueprint("shop", __name__)

@shop_bp.route("/")
def view_all_shops():
    shops = Shop.query.all()  # Query all shops
    return render_template("view_shops.html", shops=shops)  # Pass shops to template

@shop_bp.route("/city_shops/<int:city_id>")
def city_shops(city_id):
    city = City.query.get_or_404(city_id)
    shops = Shop.query.filter_by(city_id=city_id).all()
    return render_template("city_shops.html", city=city, shops=shops)

@shop_bp.route("/add_shop", methods=["GET", "POST"])
def add_shop():
    if request.method == "POST":
        name = request.form.get("name")
        shop_type = request.form.get("type")
        city_id = request.form.get("city_id")  # Optional field

        if not name or not shop_type:
            flash("Shop name and type are required!", "danger")
            return render_template("add_shop.html")

        try:
            # Allow city_id to be NULL
            city_id = int(city_id) if city_id else None

            new_shop = Shop(
                name=name,
                type=shop_type,
                city_id=city_id
            )
            db.session.add(new_shop)
            db.session.commit()
            flash(f"Shop '{name}' added successfully!", "success")
            return redirect(url_for("shop.view_all_shops"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding shop: {e}", "danger")

    cities = City.query.all()  # Pass cities to the template for optional selection
    return render_template("add_shop.html", cities=cities)



@shop_bp.route("/edit_shop/<int:shop_id>", methods=["GET", "POST"])
def edit_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    cities = City.query.all()  # Fetch all cities for the checkboxes

    if request.method == "POST":
        # Retrieve form data
        shop.name = request.form.get("name")
        shop.type = request.form.get("type")
        selected_city_id = request.form.get("cities")  # Get the selected city for the shop

        # Validate form data
        if not shop.name or not shop.type:
            flash("Shop name and type are required!", "danger")
            return render_template("edit_shop.html", shop=shop, cities=cities)

        # Update city assignment (optional)
        shop.city_id = int(selected_city_id) if selected_city_id else None

        try:
            db.session.commit()  # Save changes
            flash(f"Shop '{shop.name}' updated successfully!", "success")
            return redirect(url_for("shop.view_all_shops"))  # Redirect to all shops
        except Exception as e:
            db.session.rollback()  # Rollback on error
            flash(f"Error saving changes: {e}", "danger")
            return render_template("edit_shop.html", shop=shop, cities=cities)

    return render_template("edit_shop.html", shop=shop, cities=cities)




@shop_bp.route("/delete_shop/<int:shop_id>", methods=["POST"])
def delete_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)  # Retrieve the shop by ID
    try:
        db.session.delete(shop)  # Attempt to delete the shop
        db.session.commit()  # Commit the changes
        flash(f"Shop '{shop.name}' deleted successfully!", "success")
        return redirect(url_for("shop.view_all_shops"))  # Redirect to the list of shops
    except Exception as e:
        db.session.rollback()  # Rollback if there’s an error
        flash(f"Error deleting shop: {e}", "danger")
        return redirect(url_for("shop.view_all_shops"))  # Redirect even on failure
