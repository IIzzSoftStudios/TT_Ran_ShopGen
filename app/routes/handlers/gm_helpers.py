<<<<<<< HEAD
"""
GM Helper Functions
Utility functions for GM-related handlers
"""
from flask import redirect, url_for, flash, session
from flask_login import current_user
from app.models.users import GMProfile
from app.models.campaigns import Campaign

def get_current_gm_profile():
    """
    Get the current GM profile based on the campaign selected in session.
    Returns (gm_profile, redirect_response) tuple.
    If gm_profile is found, redirect_response is None.
    If gm_profile is not found or campaign not selected, redirect_response is a redirect.
    """
    campaign_id = session.get('campaign_id')
    if not campaign_id:
        flash("Please select a campaign first.", "info")
        return None, redirect(url_for("main.campaigns"))
    
    campaign = Campaign.query.filter_by(id=campaign_id).first()
    if not campaign:
        session.pop('campaign_id', None)
        flash("Campaign not found.", "error")
        return None, redirect(url_for("main.campaigns"))
    
    gm_profile = campaign.gm_profile
    if not gm_profile or gm_profile.user_id != current_user.id:
        flash("You do not have access to this campaign.", "error")
        session.pop('campaign_id', None)
        return None, redirect(url_for("main.campaigns"))
    
    return gm_profile, None

=======
"""Shared helpers for GM route handlers."""

from flask import abort, flash, redirect, url_for, session
from flask_login import current_user
from sqlalchemy import inspect

from app.extensions import db
from app.models import (
    City,
    Item,
    Shop,
    Campaign,
    Region,
    RegionalMarket,
    PriceHistory,
    ShopInventory,
    shop_cities,
)


def city_for_campaign_or_404(city_id: int, campaign_id: int) -> City:
    city = City.query.filter_by(city_id=city_id, campaign_id=campaign_id).first()
    if city is None:
        abort(404)
    return city


def city_for_campaign_optional(city_id: int, campaign_id: int) -> City | None:
    """Same scope as ``city_for_campaign_or_404`` but returns ``None``."""
    return City.query.filter_by(city_id=city_id, campaign_id=campaign_id).first()


def purge_shop_dependencies(shop_id: int) -> None:
    """Remove rows that block shop delete on legacy Postgres (no ON DELETE CASCADE).

    Without this, SQLAlchemy tries to NULL ``price_history.shop_id``, which
    violates the NOT NULL constraint.
    """
    db.session.query(PriceHistory).filter_by(shop_id=shop_id).delete(
        synchronize_session=False
    )
    db.session.query(ShopInventory).filter_by(shop_id=shop_id).delete(
        synchronize_session=False
    )
    db.session.execute(
        shop_cities.delete().where(shop_cities.c.shop_id == shop_id)
    )


def purge_city_dependencies(city_id: int) -> None:
    """Remove rows that block city delete on legacy Postgres (no ON DELETE CASCADE).

    Without this, SQLAlchemy tries to NULL ``regional_markets.city_id``, which
    violates the NOT NULL constraint.
    """
    db.session.query(RegionalMarket).filter_by(city_id=city_id).delete(
        synchronize_session=False
    )
    db.session.execute(
        shop_cities.delete().where(shop_cities.c.city_id == city_id)
    )


def shop_for_campaign_or_404(shop_id: int, campaign_id: int) -> Shop:
    shop = Shop.query.filter_by(shop_id=shop_id, campaign_id=campaign_id).first()
    if shop is None:
        abort(404)
    return shop


def item_for_campaign_or_404(item_id: int, campaign_id: int) -> Item:
    item = Item.query.filter_by(item_id=item_id, campaign_id=campaign_id).first()
    if item is None:
        abort(404)
    return item


def region_table_exists() -> bool:
    try:
        return bool(inspect(db.engine).has_table("region"))
    except Exception:
        return False


def region_for_campaign_or_404(region_id: int, campaign_id: int) -> Region:
    region = Region.query.filter_by(id=region_id, campaign_id=campaign_id).first()
    if region is None:
        abort(404)
    return region


_GM_SESSION_ALLOWLIST = frozenset(
    {
        "gm.generate_world_form",
    }
)


def get_current_gm_profile():
    """Return ``(gm_profile, None)`` or ``(None, redirect)``."""
    if not current_user.is_authenticated:
        return None, redirect(url_for("auth.login"))
    from flask import request

    ep = request.endpoint
    if ep not in _GM_SESSION_ALLOWLIST and session.get("session_mode") == "player":
        flash(
            "You are currently viewing a campaign as a player. "
            "Return to the campaign picker to switch views.",
            "info",
        )
        return None, redirect(url_for("main.campaigns"))
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        flash("A Game Master profile is required for this page.", "danger")
        return None, redirect(url_for("main.index"))
    return profile, None


def get_campaign_for_gm_session():
    """Active campaign from session for the current GM.

    Returns ``(gm_profile, campaign, None)`` or ``(None, None, redirect)``.
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


def require_active_campaign(gm_profile):
    """Resolve the session's campaign id and validate GM ownership.

    Returns ``(campaign, None)`` or ``(None, redirect)``.
    """
    if gm_profile is None:
        return None, redirect(url_for("main.index"))
    cid = session.get("campaign_id")
    if not cid:
        flash("Select a campaign before performing this action.", "warning")
        return None, redirect(url_for("main.campaigns"))
    camp = Campaign.query.filter_by(id=cid, gm_profile_id=gm_profile.id).first()
    if not camp:
        flash("That campaign no longer exists.", "danger")
        return None, redirect(url_for("main.campaigns"))
    return camp, None
>>>>>>> GCP
