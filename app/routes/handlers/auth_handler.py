"""Auth: login, logout, registration (vault key + legacy), forgot/reset password (email OTP)."""

import logging
import os
import secrets
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
from flask_mailman import EmailMessage
from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import db
from app.models import (
    User,
    GMProfile,
    RegistrationKey,
    AccessRequest,
    Player,
)
from app.services.billing_rules import can_add_player_profile
from app.utils.validators import (
    is_password_strong,
    PASSWORD_REUSE_FORBIDDEN_DAYS,
)
from app.services.join_codes import (
    redeem_campaign_code,
    InvalidCodeError,
    SeatCapError,
    WrongRoleError,
    JoinCodeError,
)
from app.services.player_resolution import user_has_player_profile

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
            if user.role == "Player" and not user_has_player_profile(user):
                flash("Enter your campaign code below to join a game.", "info")
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


def handle_register():
    require_key = os.getenv("REQUIRE_REGISTRATION_KEY", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    if request.method == "POST":
        username_raw = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        campaign_code = (request.form.get("campaign_code") or "").strip()
        registration_key = (
            request.form.get("registration_key", "").strip().replace("_", "-").upper()
        )
        if not registration_key:
            registration_key = (
                (request.args.get("vault_key") or "").strip().replace("_", "-").upper()
            )

        keyed = bool(registration_key) or require_key
        key_row = None
        registration_relaxed = False

        if keyed:
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
            registration_relaxed = bool(key_row.is_admin_test_key)

        username = (username_raw or "").strip()
        if not username or not password or not role:
            if keyed:
                db.session.rollback()
            flash("All fields are required!", "warning")
            return _register_redirect_fail(registration_key)

        if registration_relaxed:
            if len(username) < 1 or len(username) > 100:
                db.session.rollback()
                flash("Username must be 1–100 characters.", "warning")
                return _register_redirect_fail(registration_key)
        else:
            is_strong, msg = is_password_strong(password)
            if not is_strong:
                if keyed:
                    db.session.rollback()
                flash(msg, "danger")
                return _register_redirect_fail(registration_key)

        if role not in ["GM", "Player"]:
            if keyed:
                db.session.rollback()
            flash("Invalid role selected!", "warning")
            return _register_redirect_fail(registration_key)

        if User.query.filter_by(username=username).first():
            if keyed:
                db.session.rollback()
            flash("Username already exists!", "warning")
            return _register_redirect_fail(registration_key)

        email = (request.form.get("email") or "").strip().lower() or None
        if registration_relaxed:
            email = None
        elif email and User.query.filter_by(email=email).first():
            if keyed:
                db.session.rollback()
            flash("That email is already registered.", "warning")
            return _register_redirect_fail(registration_key)

        # Keyed registration
        if registration_key or require_key:
            if not registration_relaxed and key_row.email:
                key_email_norm = (key_row.email or "").strip().lower()
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

                if key_row.email and not registration_relaxed:
                    ar = AccessRequest.query.filter_by(vault_key=key_row.key_code).first()
                    if ar:
                        ar.vault_key_used = True
                        ar.vault_key_used_at = datetime.utcnow()

                if role == "GM":
                    gm_profile = GMProfile(user_id=new_user.id)
                    db.session.add(gm_profile)
                elif campaign_code:
                    try:
                        redeem_campaign_code(new_user, campaign_code, _commit=False)
                    except (InvalidCodeError, SeatCapError, WrongRoleError, JoinCodeError) as e:
                        db.session.rollback()
                        flash(
                            getattr(e, "args", [None])[0]
                            or "Could not join with that campaign code.",
                            "danger",
                        )
                        return _register_redirect_fail(registration_key)
                elif role == "Player":
                    okp, _ = can_add_player_profile(new_user)
                    if okp:
                        db.session.add(
                            Player(
                                user_id=new_user.id,
                                campaign_id=None,
                                currency=0,
                                is_npc=False,
                            )
                        )

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

        # Legacy open registration (no key) — same password rules as keyed registration
        is_strong_legacy, msg_legacy = is_password_strong(password)
        if not is_strong_legacy:
            flash(msg_legacy, "danger")
            return _register_redirect_fail(registration_key)

        try:
            new_user = User(username=username, role=role, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()

            if role == "GM":
                gm_profile = GMProfile(user_id=new_user.id)
                db.session.add(gm_profile)
            elif campaign_code:
                try:
                    redeem_campaign_code(new_user, campaign_code, _commit=False)
                except (InvalidCodeError, SeatCapError, WrongRoleError, JoinCodeError) as e:
                    db.session.rollback()
                    flash(
                        getattr(e, "args", [None])[0]
                        or "Could not join with that campaign code.",
                        "danger",
                    )
                    return redirect(url_for("auth.register"))
            elif role == "Player":
                okp, _ = can_add_player_profile(new_user)
                if okp:
                    db.session.add(
                        Player(
                            user_id=new_user.id,
                            campaign_id=None,
                            currency=0,
                            is_npc=False,
                        )
                    )

            db.session.commit()
            flash("Account created! You can now log in.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            log.exception("Registration error: %s", e)
            flash(f"Error creating account: {str(e)}", "danger")
            return redirect(url_for("auth.register"))

    vault_key = request.args.get("vault_key")
    return render_template("register.html", vault_key=vault_key)


def handle_forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")

    email = (request.form.get("email") or "").strip().lower()
    success_msg = "If an account exists for that email, a reset code has been sent."
    user = User.query.filter_by(email=email).first() if email else None

    if user and user.email:
        otp = "".join(secrets.choice("0123456789") for _ in range(6))
        user.set_reset_otp(otp)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            log.exception("Forgot-password persist error: %s", e)
            flash("Something went wrong. Please try again.", "danger")
            return redirect(url_for("auth.forgot_password"))

        try:
            sender = current_app.config.get(
                "MAIL_DEFAULT_SENDER", "noreply@example.com"
            )
            subject = "Your password reset code"
            body = (
                f"Your 6-digit reset code is: {otp}. It expires in 10 minutes.\n\n"
                "If you did not request this, you can ignore this email."
            )
            msg = EmailMessage(subject, body, sender, [user.email])
            msg.send()
        except Exception as e:
            log.warning("Password reset email failed: %s", e)
            user.clear_reset_otp()
            try:
                db.session.commit()
            except Exception as commit_err:
                db.session.rollback()
                log.exception("Clear OTP after mail failure: %s", commit_err)
            flash("Error sending email. Please try again later.", "danger")
            return redirect(url_for("auth.forgot_password"))

    flash(success_msg, "info")
    return redirect(url_for("auth.reset_password"))


def handle_reset_password():
    if request.method == "GET":
        return render_template("reset_password.html")

    email = (request.form.get("email") or "").strip().lower()
    otp_code = (request.form.get("otp_code") or "").strip()
    password = request.form.get("password")
    confirm = request.form.get("confirm_password")

    if password != confirm:
        flash("Passwords do not match.", "danger")
        return render_template("reset_password.html")

    is_strong, strong_msg = is_password_strong(password or "")
    if not is_strong:
        flash(strong_msg, "danger")
        return render_template("reset_password.html")

    user = User.query.filter_by(email=email).first() if email else None

    if user and user.verify_reset_otp(otp_code):
        if user.plaintext_matches_recent_password(password):
            flash(
                f"You cannot reuse a password from the last {PASSWORD_REUSE_FORBIDDEN_DAYS} days. "
                "Choose a different password.",
                "danger",
            )
            return render_template("reset_password.html")
        user.prune_password_history_older_than()
        user.archive_password_hash_before_change()
        user.set_password(password)
        user.clear_reset_otp()
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            log.exception("Reset password commit error: %s", e)
            flash("Something went wrong. Please try again.", "danger")
            return render_template("reset_password.html")
        flash("Password reset successful. You may now log in.", "success")
        return redirect(url_for("auth.login"))

    flash("Invalid or expired reset code.", "danger")
    return render_template("reset_password.html")
