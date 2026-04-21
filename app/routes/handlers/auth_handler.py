"""Auth: login, logout, registration (vault key + legacy), password reset stubs."""

import logging
import os
from datetime import datetime

from flask import (
    render_template,
    redirect,
    url_for,
    flash,
    request,
    session,
    current_app,
)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import db
from app.models import (
    User,
    Player,
    GMProfile,
    RegistrationKey,
    AccessRequest,
    Campaign,
    CampaignPlayer,
)
from app.utils.validators import is_password_strong
from app.services.billing_rules import can_add_player_to_campaign

log = logging.getLogger(__name__)


def _is_safe_next(target):
    return bool(target) and target.startswith("/") and not target.startswith("//")


def handle_login():
    next_url = request.args.get("next") or request.form.get("next")

    if current_user.is_authenticated:
        if _is_safe_next(next_url):
            return redirect(next_url)
        if current_user.role == "vault_keeper":
            return redirect(url_for("admin.keys_overview"))
        if current_user.role == "GM":
            return redirect(url_for("main.campaigns"))
        return redirect(url_for("main.campaigns"))

    if request.method == "POST":
        identifier = (request.form.get("username") or "").strip()
        password = request.form.get("password")
        user = None
        if identifier:
            user = User.query.filter_by(username=identifier).first()
            if not user and identifier:
                user = User.query.filter_by(email=identifier.lower()).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            if getattr(user, "last_active", None) is not None:
                user.last_active = datetime.utcnow()
                db.session.commit()
            flash("Login successful", "success")
            if _is_safe_next(next_url):
                return redirect(next_url)
            if user.role == "vault_keeper":
                return redirect(url_for("admin.keys_overview"))
            return redirect(url_for("main.campaigns"))
        flash("Invalid username or password", "danger")

    return render_template("login.html", next=next_url)


@login_required
def handle_logout():
    next_url = request.args.get("next")
    logout_user()
    session.pop("user_id", None)
    flash("You have been logged out", "info")
    if _is_safe_next(next_url):
        return redirect(next_url)
    return redirect(url_for("auth.login"))


def _register_redirect_fail(registration_key=""):
    key = (registration_key or "").strip()
    if key:
        return redirect(url_for("auth.register", vault_key=key))
    return redirect(url_for("auth.register"))


def _add_player_to_gm_campaigns(player, gm_profile):
    existing_campaigns = Campaign.query.filter_by(
        gm_profile_id=gm_profile.id, is_active=True
    ).all()
    for campaign in existing_campaigns:
        can_add, _ = can_add_player_to_campaign(campaign)
        if not can_add:
            continue
        if not CampaignPlayer.query.filter_by(
            campaign_id=campaign.id, player_id=player.id
        ).first():
            db.session.add(
                CampaignPlayer(
                    campaign_id=campaign.id,
                    player_id=player.id,
                    status="active",
                    is_active=True,
                )
            )


def handle_register():
    require_key = os.getenv("REQUIRE_REGISTRATION_KEY", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        gm_id = request.form.get("gm_id") if role == "Player" else None
        registration_key = (
            request.form.get("registration_key", "").strip().replace("_", "-").upper()
        )
        if not registration_key:
            registration_key = (
                (request.args.get("vault_key") or "").strip().replace("_", "-").upper()
            )

        if not username or not password or not role:
            flash("All fields are required!", "warning")
            return _register_redirect_fail(registration_key)

        is_strong, msg = is_password_strong(password)
        if not is_strong:
            flash(msg, "danger")
            return _register_redirect_fail(registration_key)

        if role not in ["GM", "Player"]:
            flash("Invalid role selected!", "warning")
            return _register_redirect_fail(registration_key)

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "warning")
            return _register_redirect_fail(registration_key)

        email = (request.form.get("email") or "").strip().lower() or None
        if email and User.query.filter_by(email=email).first():
            flash("That email is already registered.", "warning")
            return _register_redirect_fail(registration_key)

        # Keyed registration
        if registration_key or require_key:
            if not registration_key:
                flash("Registration key is required.", "warning")
                return redirect(url_for("auth.register"))

            key_row = RegistrationKey.query.filter_by(
                key_code=registration_key
            ).with_for_update().first()

            if not key_row or key_row.is_used:
                db.session.rollback()
                flash("Invalid or already used registration key.", "danger")
                return _register_redirect_fail(registration_key)

            key_email_norm = (key_row.email or "").strip().lower()
            if key_row.email:
                if not email or key_email_norm != email:
                    db.session.rollback()
                    flash(
                        "Registration key email mismatch. Use the same email you used on the access request.",
                        "danger",
                    )
                    return _register_redirect_fail(registration_key)

            try:
                new_user = User(username=username, role=role, email=email)
                new_user.set_password(password)
                db.session.add(new_user)
                db.session.flush()

                key_row.is_used = True
                key_row.user_id = new_user.id
                key_row.used_at = datetime.utcnow()

                if key_row.email:
                    ar = AccessRequest.query.filter_by(vault_key=key_row.key_code).first()
                    if ar:
                        ar.vault_key_used = True
                        ar.vault_key_used_at = datetime.utcnow()

                if role == "GM":
                    gm_profile = GMProfile(user_id=new_user.id)
                    db.session.add(gm_profile)
                else:
                    gm = User.query.get(gm_id)
                    if not gm or gm.role != "GM":
                        raise ValueError("Invalid GM selected")
                    gm_profile = GMProfile.query.filter_by(user_id=gm.id).first()
                    if not gm_profile:
                        raise ValueError("GM profile not found")
                    player = Player(
                        user_id=new_user.id,
                        gm_profile_id=gm_profile.id,
                        currency=0,
                    )
                    db.session.add(player)
                    db.session.flush()
                    _add_player_to_gm_campaigns(player, gm_profile)

                db.session.commit()
                flash(
                    "Account created! Log in with your username (not email) and password.",
                    "success",
                )
                return redirect(url_for("auth.login"))
            except (IntegrityError, OperationalError, ValueError) as e:
                db.session.rollback()
                log.exception("Registration failed: %s", e)
                flash("A database error occurred. Please try again later.", "danger")
                return _register_redirect_fail(registration_key)

        # Legacy open registration (no key)
        try:
            new_user = User(username=username, role=role, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()

            if role == "GM":
                gm_profile = GMProfile(user_id=new_user.id)
                db.session.add(gm_profile)
            else:
                gm = User.query.get(gm_id)
                if not gm or gm.role != "GM":
                    raise ValueError("Invalid GM selected")
                gm_profile = GMProfile.query.filter_by(user_id=gm.id).first()
                if not gm_profile:
                    raise ValueError("GM profile not found")
                player = Player(
                    user_id=new_user.id,
                    gm_profile_id=gm_profile.id,
                    currency=0,
                )
                db.session.add(player)
                db.session.flush()
                _add_player_to_gm_campaigns(player, gm_profile)

            db.session.commit()
            flash("Account created! You can now log in.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            log.exception("Registration error: %s", e)
            flash(f"Error creating account: {str(e)}", "danger")
            return redirect(url_for("auth.register"))

    gms = User.query.filter_by(role="GM").all()
    vault_key = request.args.get("vault_key")
    return render_template("register.html", gms=gms, vault_key=vault_key)


def handle_forgot_password():
    flash(
        "Password reset is not configured. Contact your administrator.",
        "info",
    )
    return redirect(url_for("auth.login"))


def handle_reset_password():
    flash(
        "Password reset is not configured. Contact your administrator.",
        "info",
    )
    return redirect(url_for("auth.login"))
