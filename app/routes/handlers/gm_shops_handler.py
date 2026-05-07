"""GM shop-related handler utilities and inline shop updates."""

from collections import defaultdict
from functools import lru_cache

from flask import request, redirect, url_for, flash
from sqlalchemy import inspect
from sqlalchemy.orm import subqueryload

from app.constants.shops import SHOP_TYPE_DEFAULTS
from app.extensions import db
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
    if raw is None:
        return ""
    return str(raw).strip().title()


def _normalize_shop_name(raw):
    if raw is None:
        return ""
    return str(raw).strip()


def get_shop_city_panel_context(gm_profile):
    """Build city_data, region_labels, and type_suggestions for the shops-by-city UI."""
    campaign_id = active_campaign_id()
    if not campaign_id:
        return {
            "city_data": [],
            "region_labels": [],
            "campaign_regions": [],
            "type_suggestions": sorted(SHOP_TYPE_DEFAULTS),
        }

    q = City.query.filter_by(campaign_id=campaign_id).options(
        subqueryload(City.shops)
    )
    if _region_table_exists():
        q = q.options(subqueryload(City.region_obj))
    cities = q.order_by(City.name).all()

    discovered_rows = (
        db.session.query(Shop.type)
        .filter_by(campaign_id=campaign_id)
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
        region_label = _city_region_label(city)
        city_data.append(
            {
                "city": city,
                "region_label": region_label,
                "shop_count": len(city.shops),
                "shop_type_rows": shop_type_rows,
            }
        )

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

    return {
        "city_data": city_data,
        "region_labels": region_labels,
        "campaign_regions": campaign_regions,
        "type_suggestions": type_suggestions,
    }


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
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    shop = Shop.query.get_or_404(shop_id)
    owning_campaign = Campaign.query.filter_by(
        id=shop.campaign_id, gm_profile_id=gm_profile.id
    ).first()
    if owning_campaign is None:
        flash("You don't have permission to update this shop.", "danger")
        return redirect(url_for("gm.home"))

    new_name = _normalize_shop_name(request.form.get("name"))
    new_type = _normalize_shop_type(request.form.get("type"))

    if not new_name or not new_type:
        flash("Name and type are required.", "warning")
        return redirect(url_for("gm.home"))

    try:
        shop.name = new_name
        shop.type = new_type
        db.session.commit()
        flash(f"Updated {shop.name}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating shop: {e}", "danger")

    return redirect(url_for("gm.home"))
