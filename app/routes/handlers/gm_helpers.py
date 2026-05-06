"""Shared helpers for GM route handlers."""

from functools import lru_cache

from flask import abort, flash, redirect, url_for, session
from flask_login import current_user
from sqlalchemy import inspect

from app.extensions import db
from app.models import City, Item, Shop, Campaign, Region


def city_for_gm_or_404(city_id: int, gm_profile_id: int) -> City:
    q = City.query.filter_by(city_id=city_id, gm_profile_id=gm_profile_id)
    campaign_id = session.get("campaign_id")
    if campaign_id is not None and campaign_scope_columns_available():
        q = q.filter(City.campaign_id == campaign_id)
    city = q.first()
    if city is None:
        abort(404)
    return city


def city_for_gm_optional(city_id: int, gm_profile_id: int) -> City | None:
    """Same scope as city_for_gm_or_404 but returns None instead of aborting."""
    q = City.query.filter_by(city_id=city_id, gm_profile_id=gm_profile_id)
    campaign_id = session.get("campaign_id")
    if campaign_id is not None and campaign_scope_columns_available():
        q = q.filter(City.campaign_id == campaign_id)
    return q.first()


def shop_for_gm_or_404(shop_id: int, gm_profile_id: int) -> Shop:
    q = Shop.query.filter_by(shop_id=shop_id, gm_profile_id=gm_profile_id)
    campaign_id = session.get("campaign_id")
    if campaign_id is not None and campaign_scope_columns_available():
        q = q.filter(Shop.campaign_id == campaign_id)
    shop = q.first()
    if shop is None:
        abort(404)
    return shop


def item_for_gm_or_404(item_id: int, gm_profile_id: int) -> Item:
    q = Item.query.filter_by(item_id=item_id, gm_profile_id=gm_profile_id)
    campaign_id = session.get("campaign_id")
    if campaign_id is not None and campaign_scope_columns_available():
        q = q.filter(Item.campaign_id == campaign_id)
    item = q.first()
    if item is None:
        abort(404)
    return item


def region_table_exists() -> bool:
    try:
        return bool(inspect(db.engine).has_table("region"))
    except Exception:
        return False


def region_for_gm_or_404(region_id: int, gm_profile_id: int) -> Region:
    q = Region.query.filter_by(id=region_id, gm_profile_id=gm_profile_id)
    campaign_id = session.get("campaign_id")
    if campaign_id is not None and campaign_scope_columns_available():
        q = q.filter(Region.campaign_id == campaign_id)
    region = q.first()
    if region is None:
        abort(404)
    return region


def get_current_gm_profile():
    """
    Returns (gm_profile, None) or (None, redirect_response) if unauthenticated
    or user has no GM profile.
    """
    if not current_user.is_authenticated:
        return None, redirect(url_for("auth.login"))
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        flash("A Game Master profile is required for this page.", "danger")
        return None, redirect(url_for("main.index"))
    return profile, None


def get_campaign_for_gm_session():
    """
    Active campaign from session for the current GM.
    Returns (gm_profile, campaign, None) or (None, None, redirect_response).
    """
    gm_profile, redir = get_current_gm_profile()
    if redir:
        return None, None, redir
    cid = session.get("campaign_id")
    if not cid:
        flash("No campaign selected.", "warning")
        return None, None, redirect(url_for("main.campaigns"))
    campaign = Campaign.query.filter_by(id=cid, gm_profile_id=gm_profile.id).first()
    if not campaign:
        flash("Invalid campaign.", "danger")
        return None, None, redirect(url_for("main.campaigns"))
    return gm_profile, campaign, None


def active_campaign_id():
    """Campaign currently selected in session, if any."""
    return session.get("campaign_id")


@lru_cache(maxsize=1)
def campaign_scope_columns_available() -> bool:
    """True when core world tables expose campaign_id."""
    try:
        inspector = inspect(db.engine)
        city_cols = {c["name"] for c in inspector.get_columns("cities")}
        shop_cols = {c["name"] for c in inspector.get_columns("shops")}
        item_cols = {c["name"] for c in inspector.get_columns("items")}
        return (
            "campaign_id" in city_cols
            and "campaign_id" in shop_cols
            and "campaign_id" in item_cols
        )
    except Exception:
        return False
