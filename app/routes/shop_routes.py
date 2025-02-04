from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Shop, City

# Define blueprint for shop-related routes
shop_bp = Blueprint("shop", __name__)

@shop_bp.route('/')
def view_all_shops():
    print("[DEBUG] Fetching all shops")
    shops = Shop.query.all()
    print(f"[DEBUG] Found {len(shops)} shops")
    return render_template('view_shops.html', shops=shops)

@shop_bp.route('/add', methods=['GET', 'POST'])
def add_shop():
    if request.method == 'POST':
        shop_name = request.form['name']
        shop_type = request.form['type']
        city_ids = request.form.getlist('city_ids')  # Get selected cities

        print(f"[DEBUG] Adding shop: {shop_name} of type: {shop_type}")
        print(f"[DEBUG] Selected cities: {city_ids}")

        try:
            with db.session.begin():  # Transaction ensures atomicity
                # Create new shop
                new_shop = Shop(name=shop_name, type=shop_type)
                db.session.add(new_shop)
                db.session.flush()  # Ensure shop_id is generated before linking cities

                # Link shop to selected cities using the relationship
                for city_id in city_ids:
                    city = City.query.get(city_id)
                    if city:
                        print(f"[DEBUG] Linking shop ID {new_shop.shop_id} to city ID {city_id}")
                        new_shop.cities.append(city)

            print("[DEBUG] Shop and city links committed to database")
            flash(f"Shop '{shop_name}' added successfully!", "success")

        except Exception as e:
            print(f"[ERROR] Failed to add shop: {e}")
            flash(f"Error adding shop: {e}", "danger")

        return redirect(url_for('shop.view_all_shops'))

    cities = City.query.all()
    print(f"[DEBUG] Fetching cities: {len(cities)} cities available")
    return render_template('add_shop.html', cities=cities)

@shop_bp.route('/edit/<int:shop_id>', methods=['GET', 'POST'])
def edit_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)

    if request.method == 'POST':
        shop.name = request.form['name']
        shop.type = request.form['type']
        city_ids = request.form.getlist('city_ids')  # Get selected cities

        print(f"[DEBUG] Editing shop ID {shop_id}, new name: {shop.name}, new type: {shop.type}")

        try:
            with db.session.begin():  # Transaction ensures atomicity
                # Update shop details
                db.session.commit()
                print("[DEBUG] Shop details updated")

                # Clear and reassign cities using relationships
                shop.cities.clear()  # Clear existing links
                for city_id in city_ids:
                    city = City.query.get(city_id)
                    if city:
                        print(f"[DEBUG] Linking shop ID {shop.shop_id} to city ID {city_id}")
                        shop.cities.append(city)

            print("[DEBUG] Updated city links committed to database")
            flash("Shop updated successfully!", "success")

        except Exception as e:
            print(f"[ERROR] Failed to update shop: {e}")
            flash(f"Error updating shop: {e}", "danger")

        return redirect(url_for('shop.view_all_shops'))

    cities = City.query.all()
    linked_cities = [city.city_id for city in shop.cities]
    print(f"[DEBUG] Shop linked to cities: {linked_cities}")
    return render_template('edit_shop.html', shop=shop, cities=cities, linked_cities=linked_cities)

@shop_bp.route('/delete/<int:shop_id>', methods=['POST'])
def delete_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    print(f"[DEBUG] Deleting shop ID {shop_id}")

    try:
        with db.session.begin():  # Ensure cascading deletion is handled properly
            shop.cities.clear()  # Clear links to cities
            db.session.delete(shop)
        print("[DEBUG] Shop and relationships deleted successfully")
        flash("Shop deleted successfully!", "success")

    except Exception as e:
        print(f"[ERROR] Failed to delete shop: {e}")
        flash(f"Error deleting shop: {e}", "danger")

    return redirect(url_for('shop.view_all_shops'))
