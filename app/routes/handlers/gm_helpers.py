"""Shared helpers for GM route handlers."""

from flask import abort, flash, redirect, url_for, session
from flask_login import current_user

from app.models import City, Item, Shop, Campaign


def city_for_gm_or_404(city_id: int, gm_profile_id: int) -> City:
    city = City.query.filter_by(city_id=city_id, gm_profile_id=gm_profile_id).first()
    if city is None:
        abort(404)
    return city


def shop_for_gm_or_404(shop_id: int, gm_profile_id: int) -> Shop:
    shop = Shop.query.filter_by(shop_id=shop_id, gm_profile_id=gm_profile_id).first()
    if shop is None:
        abort(404)
    return shop


def item_for_gm_or_404(item_id: int, gm_profile_id: int) -> Item:
    item = Item.query.filter_by(item_id=item_id, gm_profile_id=gm_profile_id).first()
    if item is None:
        abort(404)
    return item


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
