from flask import render_template, request, redirect, flash
from app import app, db
from app.models import City
import random

# Define population ranges for each city size
population_ranges = {
    "Hamlet": (1, 200),
    "Village": (200, 1000),
    "Small Town": (1000, 5000),
    "Large Town": (5000, 20000),
    "Small City": (20000, 50000),
    "Medium City": (50000, 200000),
    "Large City": (200000, 1000000),
    "Metropolis": (1000000, 10000000),
    "Megaplex": (10000000, 50000000),
}

@app.route("/")
def home():
    # Query all cities to display on the home page
    cities = City.query.all()
    return render_template("home.html", cities=cities)

@app.route("/add_city", methods=["GET", "POST"])
def add_city():
    if request.method == "POST":
        # Get form data
        name = request.form.get("name")
        size = request.form.get("size")
        region = request.form.get("region")
        population = request.form.get("population")

        # Validate input
        if not name or not size or not region:
            flash("All fields are required!", "danger")
            return render_template("add_city.html")

        # Generate random population if not manually entered
        if not population:
            population = random.randint(*population_ranges[size])

        try:
            # Add new city to the database
            new_city = City(
                name=name,
                size=size,
                population=int(population),
                region=region
            )
            db.session.add(new_city)
            db.session.commit()
            flash(f"City '{name}' added successfully!", "success")
            return redirect("/")
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding city: {e}", "danger")

    # Render the form to add a new city
    return render_template("add_city.html")

@app.route("/edit_city/<int:city_id>", methods=["GET", "POST"])
def edit_city(city_id):
    # Fetch the city by ID
    city = City.query.get_or_404(city_id)

    if request.method == "POST":
        # Update city data from the form
        city.name = request.form.get("name")
        city.size = request.form.get("size")
        city.region = request.form.get("region")
        city.population = int(request.form.get("population", city.population))  # Keep current population if not provided

        try:
            # Commit changes to the database
            db.session.commit()
            flash(f"City '{city.name}' updated successfully!", "success")
            return redirect("/")
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating city: {e}", "danger")

    # Render the edit form with the current city values
    return render_template("edit_city.html", city=city)

@app.route("/delete_city/<int:city_id>", methods=["POST"])
def delete_city(city_id):
    # Fetch the city by ID
    city = City.query.get_or_404(city_id)
    try:
        # Delete the city and commit the change
        db.session.delete(city)
        db.session.commit()
        flash(f"City '{city.name}' deleted successfully!", "success")
        return redirect("/")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting city: {e}", "danger")
        return redirect("/")

