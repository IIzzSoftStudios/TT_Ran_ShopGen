from flask import Blueprint, render_template, request, redirect, flash
from app.models import City
from app import db

city_bp = Blueprint("city", __name__)

@city_bp.route("/")
def home():
    cities = City.query.all()
    return render_template("home.html", cities=cities)

@city_bp.route("/add_city", methods=["GET", "POST"])
def add_city():
    if request.method == "POST":
        name = request.form.get("name")
        size = request.form.get("size")
        population = request.form.get("population")
        region = request.form.get("region")

        if not name or not size or not population or not region:
            flash("All fields are required!", "danger")
            return render_template("add_city.html")

        try:
            new_city = City(
                name=name,
                size=size,
                population=int(population),
                region=region
            )
            db.session.add(new_city)
            db.session.commit()
            flash(f"City '{name}' added successfully!", "success")
            return redirect("/cities")
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding city: {e}", "danger")

    return render_template("add_city.html")

@city_bp.route("/edit_city/<int:city_id>", methods=["GET", "POST"])
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
            return redirect("/cities")
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating city: {e}", "danger")
    return render_template("edit_city.html", city=city)


@city_bp.route("/delete_city/<int:city_id>", methods=["POST"])
def delete_city(city_id):
    city = City.query.get_or_404(city_id)
    try:
        db.session.delete(city)
        db.session.commit()
        flash("City deleted successfully!", "success")
        return redirect("/")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting city: {e}", "danger")
        return redirect("/")
