"""
GM Cities Handler
Handles all city-related business logic for GM routes
"""
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.extensions import db
from app.models.backend import City
from app.services.logging_config import gm_logger
from app.routes.handlers.gm_helpers import get_current_gm_profile


def view_cities():
    """View all cities for the current GM"""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    cities = City.query.filter_by(gm_profile_id=gm_profile.id).all()
    return render_template("GM_view_cities.html", cities=cities)


def add_city():
    """Add a new city"""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    
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
                gm_profile_id=gm_profile.id
            )
            db.session.add(new_city)
            db.session.commit()
            flash(f"City '{name}' added successfully!", "success")
            return redirect(url_for("gm.gm_view_cities"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding city: {e}", "danger")

    return render_template("GM_add_city.html")


def edit_city(city_id):
    """Edit an existing city"""
    city = City.query.get_or_404(city_id)
    
    if request.method == "POST":
        city.name = request.form.get("name")
        city.size = request.form.get("size")
        city.population = request.form.get("population")
        city.region = request.form.get("region")

        try:
            db.session.commit()
            flash("City updated successfully!", "success")
            return redirect(url_for("gm.gm_view_cities"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating city: {e}", "danger")

    return render_template("GM_edit_city.html", city=city)


def delete_city(city_id):
    """Delete a city"""
    city = City.query.get_or_404(city_id)
    try:
        db.session.delete(city)
        db.session.commit()
        flash("City deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting city: {e}", "danger")
    return redirect(url_for("gm.gm_view_cities"))
