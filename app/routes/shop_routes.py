from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import db, Shop, City, ShopInventory
from sqlalchemy.orm import joinedload

# Define blueprint for shop-related routes
shop_bp = Blueprint("shop", __name__)

@shop_bp.route('/')
@login_required
def view_all_shops():
    print("[DEBUG] Fetching all shops")
    shops = Shop.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    print(f"[DEBUG] Found {len(shops)} shops")
    return render_template('GM_view_shops.html', shops=shops)

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
                new_shop = Shop(
                    name=shop_name, 
                    type=shop_type,
                    gm_profile_id=current_user.gm_profile.id  # Add the GM profile ID
                )
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

    cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
    print(f"[DEBUG] Fetching cities: {len(cities)} cities available")
    return render_template('GM_add_shop.html', cities=cities)

@shop_bp.route('/edit/<int:shop_id>', methods=['GET', 'POST'])
def edit_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)

    if request.method == 'POST':
        try:
            # Get updated form data
            shop.name = request.form['name']
            shop.type = request.form['type']
            city_ids = request.form.getlist('city_ids')  # List of selected cities

            print(f"[DEBUG] Editing shop ID {shop_id}, New Name: {shop.name}, New Type: {shop.type}")

            # Fetch valid cities before clearing the existing ones
            new_cities = [City.query.get(city_id) for city_id in city_ids if City.query.get(city_id)]

            # Clear existing links and update with new cities
            shop.cities.clear()
            shop.cities.extend(new_cities)

            print(f"[DEBUG] Updated city links for Shop ID {shop.shop_id}: {city_ids}")

            db.session.commit()  # Save changes

            print("[DEBUG] Shop details and city links updated successfully")
            flash("Shop updated successfully!", "success")

            return redirect(url_for('shop.view_all_shops'))

        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Failed to update shop: {e}")
            flash(f"Error updating shop: {e}", "danger")

    # Fetch cities for form population
    cities = City.query.all()
    linked_city_ids = [city.city_id for city in shop.cities]
    print(f"[DEBUG] Shop linked to cities: {linked_city_ids}")

    return render_template('GM_edit_shop.html', shop=shop, cities=cities, linked_city_ids=linked_city_ids)


@shop_bp.route('/delete/<int:shop_id>', methods=['POST'])
def delete_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    print(f"[DEBUG] Deleting shop ID {shop_id}")

    try:
        # Explicitly handle the transaction
        shop.cities.clear()  # Clear links to cities first
        db.session.delete(shop)  # Delete the shop
        db.session.commit()  # Commit the changes
        print("[DEBUG] Shop and relationships deleted successfully")
        flash("Shop deleted successfully!", "success")

    except Exception as e:
        db.session.rollback()  # Roll back if an error occurs
        print(f"[ERROR] Failed to delete shop: {e}")
        flash(f"Error deleting shop: {e}", "danger")

    return redirect(url_for('shop.view_all_shops'))

# route for viewing city-specific shops
@shop_bp.route('/city/<int:city_id>/shops', methods=['GET'])
@login_required
def view_city_shops(city_id):
    city = City.query.get_or_404(city_id)
    shops = city.shops  # Assuming a relationship exists between City and Shop

    print(f"[DEBUG] Displaying {len(shops)} shops for city ID {city_id}")
    return render_template('GM_view_city_shops.html', city=city, shops=shops)

@shop_bp.route('/<int:shop_id>/items', methods=['GET'])
def view_items_by_shop(shop_id):
    shop = Shop.query.get_or_404(shop_id)

    # Query for inventory with item relationships
    inventory = db.session.query(ShopInventory).filter_by(shop_id=shop_id).options(
        joinedload(ShopInventory.item)
    ).all()

    print(f"Shop: {shop.name}, Found {len(inventory)} inventory items.")

    # Debug individual inventory entries
    for entry in inventory:
        print(f"Inventory Entry -> Item ID: {entry.item_id}, Stock: {entry.stock}, Price: {entry.dynamic_price}")
        print(f"Linked Item -> Name: {entry.item.name if entry.item else 'None'}")

    return render_template('GM_view_shop_items.html', shop=shop, inventory=inventory)

@shop_bp.route("/remove_item/<int:shop_id>/<int:item_id>", methods=["POST"])
def remove_item_from_shop(shop_id, item_id):
    try:
        # Remove the item from the shop inventory
        ShopInventory.query.filter_by(shop_id=shop_id, item_id=item_id).delete()
        db.session.commit()
        flash("Item removed from shop successfully!", "success")

        # Ensure the redirect goes to the correct route
        return redirect(url_for("shop.view_items_by_shop", shop_id=shop_id))

    except Exception as e:
        db.session.rollback()
        flash(f"Error removing item from shop: {e}", "danger")

    return redirect(url_for("shop.view_all_shops"))  # Fallback redirect
