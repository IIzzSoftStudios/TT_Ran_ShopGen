from flask import Blueprint, render_template, request, redirect, flash
from app.models import Shop, City
from app import db

shop_bp = Blueprint("shop", __name__)

@shop_bp.route("/city_shops/<int:city_id>")
def city_shops(city_id):
    city = City.query.get_or_404(city_id)
    shops = Shop.query.filter_by(city_id=city_id).all()
    return render_template("city_shops.html", city=city, shops=shops)

@shop_bp.route("/add_shop/<int:city_id>", methods=["GET", "POST"])
def add_shop(city_id):
    city = City.query.get_or_404(city_id)
    if request.method == "POST":
        shop_name = request.form.get("name")
        shop_type = request.form.get("type")
        shop_inventory = request.form.get("inventory")
        if not shop_name or not shop_type or not shop_inventory:
            flash("All fields are required!", "danger")
            return render_template("add_shop.html", city=city)
        new_shop = Shop(city_id=city_id, name=shop_name, type=shop_type, inventory=shop_inventory)
        db.session.add(new_shop)
        db.session.commit()
        flash(f"Shop '{shop_name}' added to {city.name}!", "success")
        return redirect(f"/city_shops/{city_id}")
    return render_template("add_shop.html", city=city)

@shop_bp.route("/edit_shop/<int:shop_id>", methods=["GET", "POST"])
def edit_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    if request.method == "POST":
        shop.name = request.form.get("name")
        shop.type = request.form.get("type")
        shop.inventory = request.form.get("inventory")
        if not shop.name or not shop.type or not shop.inventory:
            flash("All fields are required!", "danger")
            return render_template("edit_shop.html", shop=shop)
        db.session.commit()
        flash(f"Shop '{shop.name}' updated successfully!", "success")
        return redirect(f"/city_shops/{shop.city_id}")
    return render_template("edit_shop.html", shop=shop)

@shop_bp.route("/delete_shop/<int:shop_id>", methods=["POST"])
def delete_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    try:
        db.session.delete(shop)
        db.session.commit()
        flash(f"Shop '{shop.name}' deleted successfully!", "success")
    except Exception as e:
        db.session.rollba
