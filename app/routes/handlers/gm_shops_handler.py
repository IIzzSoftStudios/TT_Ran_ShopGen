<<<<<<< HEAD
"""
GM Shops Handler
Handles all shop-related business logic for GM routes
"""
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
=======
"""GM shop-related handler utilities and inline shop updates."""

from collections import defaultdict
from functools import lru_cache

from flask import request, redirect, url_for, flash
from sqlalchemy import inspect
>>>>>>> GCP
from sqlalchemy.orm import subqueryload

from app.constants.shops import SHOP_TYPE_DEFAULTS
from app.extensions import db
<<<<<<< HEAD
from app.models.backend import City, Shop, Item, ShopInventory
from app.services.logging_config import gm_logger
from app.routes.handlers.gm_helpers import get_current_gm_profile
from collections import defaultdict


def _normalize_shop_type(raw):
    """Strip and title-case shop type for consistent grouping and display."""
=======
from app.models import City, Shop, ShopInventory, Region, Campaign
from app.routes.handlers.gm_helpers import (
    get_current_gm_profile,
    active_campaign_id,
)


@lru_cache(maxsize=1)
def _region_table_exists() -> bool:
    """True if PostgreSQL has `region` (enables City.region_obj). Cached per process."""
    try:
        return bool(inspect(db.engine).has_table("region"))
    except Exception:
        return False


def _city_region_label(city: City) -> str:
    """Label for grouping/filter: denormalized `city.region`, else FK name, else Unspecified."""
    if city.region:
        s = str(city.region).strip()
        if s:
            return s
    if _region_table_exists():
        ro = getattr(city, "region_obj", None)
        if ro is not None and getattr(ro, "name", None):
            s = (ro.name or "").strip()
            if s:
                return s
    return "Unspecified"


def build_grouped_cities_for_shop_form(cities: list) -> dict:
    """Nested dict region_label -> size_label -> [City, ...] for GM shop city pickers."""
    nested: dict = defaultdict(lambda: defaultdict(list))
    for city in cities:
        region = _city_region_label(city)
        size = (getattr(city, "size", None) or "").strip() or "Unspecified"
        nested[region][size].append(city)
    out = {}
    for region in sorted(nested.keys(), key=lambda s: (s or "").lower()):
        size_map = {}
        for size_name in sorted(nested[region].keys(), key=lambda s: (s or "").lower()):
            size_map[size_name] = sorted(
                nested[region][size_name],
                key=lambda c: ((c.name or "").lower(), c.city_id),
            )
        out[region] = size_map
    return out


def _normalize_shop_type(raw):
>>>>>>> GCP
    if raw is None:
        return ""
    return str(raw).strip().title()


def _normalize_shop_name(raw):
    if raw is None:
        return ""
    return str(raw).strip()


<<<<<<< HEAD
def group_cities_for_display(cities):
    """
    Groups cities by Region -> Size -> List of Cities
    
    Args:
        cities: List of City objects (must have region, size, and name attributes)
    
    Returns:
        dict: Nested dictionary structure: {region: {size: [city1, city2, ...]}}
    """
    grouped = defaultdict(lambda: defaultdict(list))
    
    for city in cities:
        region = city.region or "Unspecified"
        size = city.size or "Unspecified"
        grouped[region][size].append(city)
    
    # Convert defaultdict to regular dict for template rendering
    return {region: dict(sizes) for region, sizes in grouped.items()}


def get_shop_city_panel_context(gm_profile):
    """
    Build city_data and type_suggestions for the nested shops-by-city UI.
    Used by GM View Shops and the GM Home dashboard.
    """
    cities = (
        City.query.filter_by(gm_profile_id=gm_profile.id)
        .options(subqueryload(City.shops))
        .order_by(City.name)
        .all()
    )

    discovered_rows = (
        db.session.query(Shop.type)
        .filter_by(gm_profile_id=gm_profile.id)
=======
def _shop_type_rows_for_shops(shops) -> list:
    """Group shops by normalized type for nested type-block UI."""
    by_type = {}
    for shop in sorted(shops, key=lambda s: (s.name or "").lower()):
        type_key = _normalize_shop_type(shop.type) or "Unspecified"
        by_type.setdefault(type_key, []).append(shop)
    rows = [
        {
            "type": type_key,
            "count": len(type_shops),
            "shops": sorted(type_shops, key=lambda s: (s.name or "").lower()),
        }
        for type_key, type_shops in by_type.items()
    ]
    rows.sort(key=lambda r: (-r["count"], r["type"].lower()))
    return rows


_ORPHAN_SHOPS_REGION_LABEL = "Unspecified"


def get_shop_city_panel_context(gm_profile, *, include_nav_toggles: bool = False):
    """Build city_data, region_labels, and type_suggestions for the shops-by-city UI.

    When ``include_nav_toggles`` is True and a campaign is active, also passes
    ``campaign`` and ``supply_demand_enabled`` for ``gm_world_quick_nav.html``.
    """
    campaign_id = active_campaign_id()
    if not campaign_id:
        base = {
            "city_data": [],
            "region_groups": [],
            "region_labels": [],
            "campaign_regions": [],
            "type_suggestions": sorted(SHOP_TYPE_DEFAULTS),
        }
        if include_nav_toggles:
            base["campaign"] = None
            base["supply_demand_enabled"] = True
            base["market_volatility"] = 5
        return base

    q = City.query.filter_by(campaign_id=campaign_id).options(
        subqueryload(City.shops)
    )
    if _region_table_exists():
        q = q.options(subqueryload(City.region_obj))
    cities = q.order_by(City.name).all()

    discovered_rows = (
        db.session.query(Shop.type)
        .filter_by(campaign_id=campaign_id)
>>>>>>> GCP
        .distinct()
        .all()
    )
    discovered_normalized = {
        _normalize_shop_type(row[0]) for row in discovered_rows if row[0]
    }
    discovered_normalized.discard("")
    type_suggestions = sorted(SHOP_TYPE_DEFAULTS | discovered_normalized)

    city_data = []
    for city in cities:
<<<<<<< HEAD
        by_type = {}
        for shop in sorted(city.shops, key=lambda s: (s.name or "").lower()):
            type_key = _normalize_shop_type(shop.type) or "Unspecified"
            by_type.setdefault(type_key, []).append(shop)
        shop_type_rows = [
            {
                "type": type_key,
                "count": len(shops),
                "shops": sorted(shops, key=lambda s: (s.name or "").lower()),
            }
            for type_key, shops in by_type.items()
        ]
        shop_type_rows.sort(key=lambda r: (-r["count"], r["type"].lower()))
        city_data.append(
            {
                "city": city,
=======
        shop_type_rows = _shop_type_rows_for_shops(city.shops)
        region_label = _city_region_label(city)
        city_data.append(
            {
                "city": city,
                "region_label": region_label,
>>>>>>> GCP
                "shop_count": len(city.shops),
                "shop_type_rows": shop_type_rows,
            }
        )

<<<<<<< HEAD
    return {"city_data": city_data, "type_suggestions": type_suggestions}


def view_shops():
    """View shops grouped by city for nested card UI."""
    try:
        gm_profile, redirect_response = get_current_gm_profile()
        if redirect_response:
            return redirect_response
        gm_logger.info(f"view_shops called for user: {current_user.username}, GM Profile ID: {gm_profile.id}")

        ctx = get_shop_city_panel_context(gm_profile)
        gm_logger.info(
            f"view_shops: {len(ctx['city_data'])} cities, {len(ctx['type_suggestions'])} type suggestions"
        )
        return render_template(
            "GM_view_shops.html",
            **ctx,
        )
    except Exception as e:
        gm_logger.error(f"Error in view_shops: {str(e)}", exc_info=True)
        flash(f"Error loading shops: {str(e)}", "danger")
        return redirect(url_for("gm.gm_home"))


def add_shop():
    """Add a new shop"""
    if request.method == "POST":
        shop_name = _normalize_shop_name(request.form.get("name"))
        shop_type = _normalize_shop_type(request.form.get("type"))
        city_ids = request.form.getlist("city_ids")

        print("DEBUG: Shop Name:", shop_name)
        print("DEBUG: Shop Type:", shop_type)
        print("DEBUG: City IDs:", city_ids)

        gm_profile, redirect_response = get_current_gm_profile()
        if redirect_response:
            return redirect_response

        if not shop_name or not shop_type:
            flash("Shop name and type are required.", "warning")
            return redirect(url_for("gm.gm_add_shop"))
        
        try:
            gm_profile_id = gm_profile.id
            print("DEBUG: GM Profile ID:", gm_profile_id)

            new_shop = Shop(
                name=shop_name,
                type=shop_type,
                gm_profile_id=gm_profile_id
            )
            db.session.add(new_shop)
            db.session.flush()  # Ensures new_shop gets an ID

            for city_id in city_ids:
                try:
                    city = City.query.get(int(city_id))
                    if city:
                        new_shop.cities.append(city)
                    else:
                        print(f"[WARNING] City ID {city_id} not found.")
                except ValueError:
                    print(f"[ERROR] Invalid city_id value: {city_id}")

            db.session.commit()
            flash(f"Shop '{shop_name}' added successfully!", "success")

        except Exception as e:
            db.session.rollback()
            print("[ERROR] Exception occurred while adding shop:")
            import traceback
            traceback.print_exc()
            flash(f"Error adding shop: {e}", "danger")

        return redirect(url_for("gm.gm_view_shops"))

    # GET request: render form
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    cities = City.query.filter_by(gm_profile_id=gm_profile.id).all()
    return render_template("GM_add_shop.html", cities=cities)


def edit_shop(shop_id):
    """Edit an existing shop"""
    shop = Shop.query.get_or_404(shop_id)
    
    if request.method == "POST":
        shop.name = _normalize_shop_name(request.form.get("name"))
        shop.type = _normalize_shop_type(request.form.get("type"))
        if not shop.name or not shop.type:
            flash("Name and type are required.", "warning")
            return redirect(url_for("gm.gm_edit_shop", shop_id=shop_id))

        # Handle city associations
        city_ids = request.form.getlist("city_ids")
        # Get current city associations
        current_city_ids = {city.city_id for city in shop.cities}
        new_city_ids = {int(cid) for cid in city_ids if cid}
        
        # Remove cities that are no longer selected
        for city in shop.cities[:]:  # Use slice to create a copy for iteration
            if city.city_id not in new_city_ids:
                shop.cities.remove(city)
        
        # Add new city associations
        for city_id in new_city_ids:
            if city_id not in current_city_ids:
                city = City.query.get(city_id)
                if city:
                    shop.cities.append(city)
        
        try:
            db.session.commit()
            flash("Shop updated successfully!", "success")
            return redirect(url_for("gm.gm_view_shops"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating shop: {e}", "danger")

    # GET route: Load cities and determine which cities have this shop
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    cities = City.query.filter_by(gm_profile_id=gm_profile.id).all()
    grouped_cities = group_cities_for_display(cities)
    linked_city_ids = [city.city_id for city in shop.cities]
    return render_template("GM_edit_shop.html", shop=shop, cities=cities, grouped_cities=grouped_cities, linked_city_ids=linked_city_ids)


def update_shop_basic(shop_id):
    """Update shop name and type only; preserves city M2M links."""
=======
    region_groups_by_key = {}
    if _region_table_exists() and campaign_id is not None:
        for reg in Region.query.filter_by(campaign_id=campaign_id).order_by(Region.name).all():
            key = f"fk:{reg.id}"
            region_groups_by_key[key] = {
                "label": reg.name,
                "region_id": reg.id,
                "cities": [],
            }

    for row in city_data:
        city = row["city"]
        if getattr(city, "region_id", None):
            key = f"fk:{city.region_id}"
        else:
            key = f"label:{row['region_label']}"
        group = region_groups_by_key.setdefault(
            key,
            {
                "label": row["region_label"],
                "region_id": getattr(city, "region_id", None),
                "cities": [],
            },
        )
        group["cities"].append(row)

    region_groups = sorted(
        region_groups_by_key.values(),
        key=lambda g: ((g["label"] or "").lower(), g["region_id"] or 0),
    )
    orphan_shops = (
        Shop.query.filter_by(campaign_id=campaign_id)
        .filter(~Shop.cities.any())
        .order_by(Shop.name)
        .all()
    )
    orphan_shop_type_rows = _shop_type_rows_for_shops(orphan_shops)
    if orphan_shop_type_rows:
        orphan_group = region_groups_by_key.setdefault(
            f"label:{_ORPHAN_SHOPS_REGION_LABEL}",
            {
                "label": _ORPHAN_SHOPS_REGION_LABEL,
                "region_id": None,
                "cities": [],
            },
        )
        orphan_group["orphan_shop_type_rows"] = orphan_shop_type_rows
        region_groups = sorted(
            region_groups_by_key.values(),
            key=lambda g: ((g["label"] or "").lower(), g["region_id"] or 0),
        )

    for group in region_groups:
        group["city_count"] = len(group["cities"])
        group["shop_count"] = sum(row["shop_count"] for row in group["cities"])
        group["shop_count"] += sum(
            row["count"] for row in group.get("orphan_shop_type_rows", [])
        )
        group.setdefault("orphan_shop_type_rows", [])

    region_labels = sorted(
        {row["region_label"] for row in city_data},
        key=lambda s: (s or "").lower(),
    )

    campaign_regions = []
    if _region_table_exists() and campaign_id is not None:
        campaign_regions = (
            Region.query.filter_by(campaign_id=campaign_id)
            .order_by(Region.name)
            .all()
        )

    out = {
        "city_data": city_data,
        "region_groups": region_groups,
        "region_labels": region_labels,
        "campaign_regions": campaign_regions,
        "type_suggestions": type_suggestions,
    }
    if include_nav_toggles:
        from app.services.world_generator.campaign_settings import (
            read_market_volatility,
            read_supply_demand_flag,
        )

        out["campaign"] = Campaign.query.filter_by(id=campaign_id).first()
        out["supply_demand_enabled"] = read_supply_demand_flag(campaign_id)
        out["market_volatility"] = read_market_volatility(campaign_id)
    return out


def get_grouped_shops(gm_profile):
    """
    Materialized dict: city_name -> { shop_type -> [Shop, ...] }, plus per-city
    metadata for shop-picker summaries (region, size, counts) aligned with the
    GM shops-by-city panel.

    Returns:
        tuple: (grouped_shops, city_shop_meta) where city_shop_meta maps city_name
        to dict keys: region_label, size, shop_count.
    """
    campaign_id = active_campaign_id()
    if not campaign_id:
        return {}, {}
    q = City.query.filter_by(campaign_id=campaign_id)
    q = q.options(subqueryload(City.shops))
    if _region_table_exists():
        q = q.options(subqueryload(City.region_obj))
    cities = q.order_by(City.name).all()

    grouped = {}
    city_meta = {}
    for city in cities:
        by_type = {}
        for shop in sorted(city.shops, key=lambda s: (s.name or "").lower()):
            type_key = _normalize_shop_type(shop.type) or "Unspecified"
            by_type.setdefault(type_key, []).append(shop)
        city_name = city.name or "Unknown"
        grouped[city_name] = by_type
        shop_count = sum(len(shops) for shops in by_type.values())
        city_meta[city_name] = {
            "region_label": _city_region_label(city),
            "size": (city.size or "").strip(),
            "shop_count": shop_count,
        }
    return grouped, city_meta


def get_linked_shop_ids_for_item(item_id: int) -> set:
    """Distinct shop_ids from shop_inventory for this item (single source of truth)."""
    rows = (
        db.session.query(ShopInventory.shop_id)
        .filter(
            ShopInventory.item_id == item_id,
            ShopInventory.shop_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def update_shop_basic(shop_id):
    """Update shop name and type from dashboard inline form; redirect to GM home."""
>>>>>>> GCP
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    shop = Shop.query.get_or_404(shop_id)
<<<<<<< HEAD
    if shop.gm_profile_id != gm_profile.id:
        flash("You don't have permission to update this shop.", "danger")
        return redirect(url_for("gm.gm_view_shops"))
=======
    owning_campaign = Campaign.query.filter_by(
        id=shop.campaign_id, gm_profile_id=gm_profile.id
    ).first()
    if owning_campaign is None:
        flash("You don't have permission to update this shop.", "danger")
        return redirect(url_for("gm.home"))
>>>>>>> GCP

    new_name = _normalize_shop_name(request.form.get("name"))
    new_type = _normalize_shop_type(request.form.get("type"))

    if not new_name or not new_type:
        flash("Name and type are required.", "warning")
<<<<<<< HEAD
        return redirect(url_for("gm.gm_view_shops"))
=======
        return redirect(url_for("gm.home"))
>>>>>>> GCP

    try:
        shop.name = new_name
        shop.type = new_type
        db.session.commit()
        flash(f"Updated {shop.name}.", "success")
    except Exception as e:
        db.session.rollback()
<<<<<<< HEAD
        gm_logger.error(f"update_shop_basic failed: {e}", exc_info=True)
        flash(f"Error updating shop: {e}", "danger")

    return redirect(url_for("gm.gm_view_shops"))


def delete_shop(shop_id):
    """Delete a shop"""
    shop = Shop.query.get_or_404(shop_id)
    try:
        db.session.delete(shop)
        db.session.commit()
        flash("Shop deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting shop: {e}", "danger")
    return redirect(url_for("gm.gm_view_shops"))


def view_city_shops(city_id):
    """View all shops in a specific city"""
    city = City.query.get_or_404(city_id)
    shops = city.shops
    return render_template("GM_view_city_shops.html", city=city, shops=shops)


def view_shop_items(shop_id):
    """View all items in a specific shop"""
    try:
        gm_logger.info(f"view_shop_items called for shop_id: {shop_id}, user: {current_user.username}")
        
        shop = Shop.query.get_or_404(shop_id)
        gm_logger.info(f"Shop found: {shop.name} (ID: {shop.shop_id}), GM Profile ID: {shop.gm_profile_id}")
        
        # Verify shop belongs to current user's GM profile
        gm_profile, redirect_response = get_current_gm_profile()
        if redirect_response:
            return redirect_response
        if shop.gm_profile_id != gm_profile.id:
            gm_logger.warning(f"Access denied: Shop {shop_id} does not belong to user {current_user.username}")
            flash("You don't have permission to view this shop.", "danger")
            return redirect(url_for("gm.gm_view_shops"))
        
        city = shop.cities[0] if shop.cities else None
        gm_logger.info(f"City: {city.name if city else 'None'}")
        
        shop_inventory = ShopInventory.query.filter_by(shop_id=shop_id).all()
        gm_logger.info(f"Found {len(shop_inventory)} inventory entries")
        
        item_ids = [inv.item_id for inv in shop_inventory]
        items = Item.query.filter(Item.item_id.in_(item_ids)).all() if item_ids else []
        gm_logger.info(f"Found {len(items)} items")
        
        # Log inventory details
        for inv in shop_inventory:
            gm_logger.debug(f"Inventory entry: item_id={inv.item_id}, stock={inv.stock}, price={inv.dynamic_price}")
        
        gm_logger.info(f"Rendering template GM_view_shop_items.html with shop_id={shop_id}")
        return render_template("GM_view_shop_items.html", items=items, shop=shop, city=city)
        
    except Exception as e:
        gm_logger.error(f"Error in view_shop_items for shop_id {shop_id}: {str(e)}", exc_info=True)
        flash(f"Error loading shop items: {str(e)}", "danger")
        return redirect(url_for("gm.gm_view_shops"))


def remove_item_from_shop(shop_id, item_id):
    """Remove an item from a shop's inventory"""
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
    return redirect(url_for("gm.gm_view_shop_items", shop_id=shop_id))
=======
        flash(f"Error updating shop: {e}", "danger")

    return redirect(url_for("gm.home"))
>>>>>>> GCP
