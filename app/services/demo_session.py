"""Anonymous Demo entry: restore immutable snapshot into a private campaign."""

from __future__ import annotations

import secrets

from flask import current_app, session
from flask_login import login_user
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    Campaign,
    City,
    Item,
    MapCanvas,
    MapMarker,
    MapPointOfInterest,
    Player,
    PlayerCharacterSheet,
    PlayerEquipment,
    PlayerInventory,
    PriceHistory,
    Region,
    Shop,
    ShopInventory,
    User,
    shop_cities,
)
from app.routes.handlers.gm_campaigns_handler import _purge_campaign_dependencies
from app.services.demo_snapshot import load_snapshot_file, resolve_snapshot_path, restore_demo_snapshot
from app.services.demo_tutorial import default_demo_step_id
from app.services.user_capabilities import ensure_gm_profile
from app.services.world_setup_state import (
    redirect_for_setup_stage,
    settings_for_campaign,
)

DEMO_SYSTEM_USERNAME = "ef_demo_system"
DEMO_ANON_PREFIX = "ef_demo_anon_"


def is_anonymous_demo_user(user) -> bool:
    """True only for ephemeral Try Demo GM accounts (``ef_demo_anon_*``)."""
    if user is None:
        return False
    username = getattr(user, "username", None) or ""
    return isinstance(username, str) and username.startswith(DEMO_ANON_PREFIX)


def clear_demo_session_flags() -> None:
    """Strip demo walkthrough flags so they cannot leak into real GM sessions."""
    session.pop("demo_mode", None)
    session.pop("demo_step", None)
    session.pop("demo_run_id", None)
    # Keep demo_anon_id so re-entry to /demo can reuse the same ephemeral user.
    session.modified = True


def active_demo_mode_for_user(user) -> bool:
    """Gate demo UI: session flag alone is never enough.

    If a stale ``demo_mode`` flag is present for a real account, clear it.
    """
    flagged = bool(session.get("demo_mode"))
    if not flagged:
        return False
    if not is_anonymous_demo_user(user):
        clear_demo_session_flags()
        return False
    return True


def resolve_template_campaign_id() -> int | None:
    """Operator export source only (optional). Not used for visitor provision."""
    raw = (current_app.config.get("DEMO_TEMPLATE_CAMPAIGN_ID") or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def snapshot_is_configured() -> bool:
    try:
        path = resolve_snapshot_path()
    except Exception:
        return False
    return path.is_file()


def ensure_demo_system_user() -> User:
    """Idempotent system owner for optional live template export source."""
    user = User.query.filter_by(username=DEMO_SYSTEM_USERNAME).first()
    if user is None:
        user = User(
            username=DEMO_SYSTEM_USERNAME,
            password="!",
            role="Both",
            email=None,
        )
        user.set_password(secrets.token_urlsafe(48))
        db.session.add(user)
        db.session.flush()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    return user


def _anon_id_for_session() -> str:
    token = session.get("demo_anon_id")
    if not token or not isinstance(token, str) or len(token) < 8:
        token = secrets.token_hex(16)
        session["demo_anon_id"] = token
        session.modified = True
    return token


def ensure_anonymous_demo_user() -> User:
    """Session-scoped ephemeral Demo GM (unusable password)."""
    anon = _anon_id_for_session()
    username = f"{DEMO_ANON_PREFIX}{anon}"
    user = User.query.filter_by(username=username).first()
    if user is None:
        user = User(
            username=username,
            password="!",
            role="Both",
            email=None,
        )
        user.set_password(secrets.token_urlsafe(48))
        db.session.add(user)
        db.session.flush()
    ensure_gm_profile(user)
    db.session.flush()
    db.session.refresh(user)
    return user


def _destroy_campaign_rows(campaign: Campaign) -> None:
    """Delete a personal demo campaign."""
    cid = campaign.id
    canvas_ids = db.session.query(MapCanvas.id).filter_by(campaign_id=cid)
    MapMarker.query.filter(MapMarker.canvas_id.in_(canvas_ids)).delete(
        synchronize_session=False
    )
    MapPointOfInterest.query.filter(
        MapPointOfInterest.canvas_id.in_(canvas_ids)
    ).delete(synchronize_session=False)
    MapMarker.query.filter_by(campaign_id=cid).delete(synchronize_session=False)
    MapPointOfInterest.query.filter_by(campaign_id=cid).delete(
        synchronize_session=False
    )
    MapCanvas.query.filter_by(campaign_id=cid).delete(synchronize_session=False)

    shop_ids = db.session.query(Shop.shop_id).filter_by(campaign_id=cid)
    city_ids = db.session.query(City.city_id).filter_by(campaign_id=cid)
    db.session.execute(
        shop_cities.delete().where(
            or_(
                shop_cities.c.shop_id.in_(shop_ids),
                shop_cities.c.city_id.in_(city_ids),
            )
        )
    )
    # shop_inventory / price_history FK shops without always-on CASCADE — must go first.
    ShopInventory.query.filter_by(campaign_id=cid).delete(synchronize_session=False)
    PriceHistory.query.filter_by(campaign_id=cid).delete(synchronize_session=False)
    Shop.query.filter_by(campaign_id=cid).delete(synchronize_session=False)
    City.query.filter_by(campaign_id=cid).delete(synchronize_session=False)
    Region.query.filter_by(campaign_id=cid).delete(synchronize_session=False)

    campaign_item_ids = db.session.query(Item.item_id).filter(Item.campaign_id == cid)
    PlayerInventory.query.filter(
        PlayerInventory.item_id.in_(campaign_item_ids)
    ).delete(synchronize_session=False)
    PlayerEquipment.query.filter(
        PlayerEquipment.item_id.in_(campaign_item_ids)
    ).update({PlayerEquipment.item_id: None}, synchronize_session=False)
    PlayerCharacterSheet.query.filter_by(campaign_id=cid).delete(
        synchronize_session=False
    )
    Player.query.filter_by(campaign_id=cid).update(
        {Player.campaign_id: None}, synchronize_session=False
    )
    _purge_campaign_dependencies(cid)
    db.session.expire(campaign, ["simulation_state", "world_state"])
    db.session.delete(campaign)
    db.session.flush()


def _clear_personal_demo_campaigns(gm_profile_id: int) -> None:
    rows = (
        Campaign.query.filter_by(gm_profile_id=gm_profile_id, is_active=True)
        .order_by(Campaign.id.asc())
        .all()
    )
    for camp in rows:
        _destroy_campaign_rows(camp)
    db.session.expire_all()


def enter_demo_gm_session(campaign: Campaign, demo_user: User) -> object | None:
    """Bind Flask-Login + GM session to a private demo campaign at step 1."""
    login_user(demo_user, remember=False)
    session["session_mode"] = "gm"
    session["campaign_id"] = campaign.id
    session["system_type"] = campaign.system_type
    session["demo_mode"] = True
    session["demo_step"] = default_demo_step_id()
    session.pop("demo_email", None)
    session.pop("player_id", None)
    session.permanent = True
    session.modified = True
    return redirect_for_setup_stage(settings_for_campaign(campaign))


def start_anonymous_demo() -> tuple[Campaign | None, object | None, str | None]:
    """Restore snapshot for this browser session and open demo GM home.

    Returns ``(campaign, setup_redirect_or_None, error_message_or_None)``.
    """
    if not snapshot_is_configured():
        return (
            None,
            None,
            "Demo is not configured yet. Add a demo snapshot file (DEMO_SNAPSHOT_PATH).",
        )

    try:
        snapshot = load_snapshot_file()
    except (OSError, ValueError, FileNotFoundError) as exc:
        return None, None, f"Demo world is not available. ({exc})"

    user = ensure_anonymous_demo_user()
    profile = user.gm_profile
    if profile is None:
        profile = ensure_gm_profile(user)
        db.session.flush()
        db.session.refresh(user)
        profile = user.gm_profile

    _clear_personal_demo_campaigns(profile.id)
    personal = restore_demo_snapshot(
        snapshot,
        gm_profile_id=profile.id,
        name="Demo World",
    )
    db.session.commit()

    setup_redirect = enter_demo_gm_session(personal, user)
    try:
        from app.services.demo_analytics import (
            EVENT_DEMO_START,
            current_demo_run_id,
            mint_demo_run_id,
            record_demo_event,
        )

        run_id = current_demo_run_id() or mint_demo_run_id()
        anon_id = session.get("demo_anon_id") or _anon_id_for_session()
        record_demo_event(
            event_type=EVENT_DEMO_START,
            demo_run_id=run_id,
            demo_anon_id=str(anon_id),
            user_id=getattr(user, "id", None),
            commit=True,
        )
    except Exception:
        from app.services.logging_config import gm_logger

        gm_logger.exception("Demo analytics demo_start failed")
    return personal, setup_redirect, None
