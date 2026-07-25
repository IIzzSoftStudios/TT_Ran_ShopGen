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
    jsonify,
    send_file,
    abort,
)
from flask_login import login_user, logout_user, login_required, current_user
from flask_mailman import EmailMessage
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from app.extensions import db
from app.models import (
    User,
    GMProfile,
    RegistrationKey,
    AccessRequest,
    Player,
    UserSubmission,
)
from app.services.schema_compat import ensure_user_password_history_table
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
from app.services.user_capabilities import ensure_gm_profile
from app.services import character_sheet_service
from app.services.submission_ingest import (
    SubmissionValidationError,
    build_submission,
)
from app.services import user_avatar as user_avatar_service

log = logging.getLogger(__name__)


def _is_safe_next(target):
    return bool(target) and target.startswith("/") and not target.startswith("//")


def handle_login():
    next_url = request.args.get("next") or request.form.get("next")

    # Allow credential POST to switch accounts (e.g. leave Try Demo for a real GM).
    if current_user.is_authenticated and request.method != "POST":
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
            from app.services.demo_session import (
                clear_demo_session_flags,
                is_anonymous_demo_user,
            )

            # Real accounts must never inherit a leftover Try Demo walkthrough.
            if not is_anonymous_demo_user(user):
                clear_demo_session_flags()
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
    from app.services.demo_session import clear_demo_session_flags

    clear_demo_session_flags()
    logout_user()
    session.pop("user_id", None)
    session.pop("session_mode", None)
    flash("You have been logged out", "info")
    if _is_safe_next(next_url):
        return redirect(next_url)
    return redirect(url_for("auth.login"))


def _setup_new_unified_user(new_user, campaign_code: str) -> None:
    """Create GM profile and optionally join a campaign for role=Both."""
    ensure_gm_profile(new_user)
    if campaign_code:
        from app.services.join_codes import REDEMPTION_SOURCE_REGISTRATION_WITH_KEY

        redeem_campaign_code(
            new_user,
            campaign_code,
            _commit=False,
            source=REDEMPTION_SOURCE_REGISTRATION_WITH_KEY,
        )


def _register_redirect_fail(registration_key=""):
    key = (registration_key or "").strip()
    if request.args.get("campaign_code") == "1":
        return redirect(url_for("auth.register", campaign_code="1"))
    if key:
        return redirect(url_for("auth.register", vault_key=key))
    return redirect(url_for("auth.register"))


def _handle_campaign_code_register(username: str, password: str, confirm_password: str,
                                   email: str | None, campaign_code: str):
    """Create a player-only account from a GM's CAMP code."""
    if not campaign_code:
        flash("Campaign code is required.", "warning")
        return redirect(url_for("auth.register", campaign_code="1"))

    if not username or not password or not confirm_password:
        flash("All fields are required!", "warning")
        return redirect(url_for("auth.register", campaign_code="1"))

    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("auth.register", campaign_code="1"))

    is_strong, msg = is_password_strong(password)
    if not is_strong:
        flash(msg, "danger")
        return redirect(url_for("auth.register", campaign_code="1"))

    if User.query.filter_by(username=username).first():
        flash("Username already exists!", "warning")
        return redirect(url_for("auth.register", campaign_code="1"))

    if email and User.query.filter_by(email=email).first():
        flash("That email is already registered.", "warning")
        return redirect(url_for("auth.register", campaign_code="1"))

    try:
        new_user = User(username=username, role="Player", email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush()
        from app.services.join_codes import REDEMPTION_SOURCE_REGISTRATION

        campaign = redeem_campaign_code(
            new_user,
            campaign_code,
            _commit=False,
            source=REDEMPTION_SOURCE_REGISTRATION,
        )
        player = Player.query.filter_by(
            user_id=new_user.id,
            campaign_id=campaign.id,
            is_npc=False,
        ).first()
        if player is None:
            raise ValueError("Campaign join did not create a player character.")
        character_sheet_service.ensure_initial_campaign_sheet(player, campaign)
        db.session.commit()
        from app.services.demo_session import clear_demo_session_flags

        clear_demo_session_flags()
        login_user(new_user, remember=True)
        session["session_mode"] = "player"
        session["campaign_id"] = campaign.id
        session["player_id"] = player.id
        session["system_type"] = campaign.system_type
        session.permanent = True
        session.modified = True
        flash(
            "Player account created. Finish setting up your campaign character next.",
            "success",
        )
        return redirect(url_for("player.character_dashboard", player_id=player.id))
    except (InvalidCodeError, SeatCapError, WrongRoleError, JoinCodeError) as e:
        db.session.rollback()
        flash(
            getattr(e, "args", [None])[0]
            or "Could not join with that campaign code.",
            "danger",
        )
        return redirect(url_for("auth.register", campaign_code="1"))
    except (IntegrityError, OperationalError, ValueError) as e:
        db.session.rollback()
        log.exception("Campaign-code registration failed: %s", e)
        flash("Something went wrong creating your account. Please try again.", "danger")
        return redirect(url_for("auth.register", campaign_code="1"))


def handle_register():
    require_key = os.getenv("REQUIRE_REGISTRATION_KEY", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    if request.method == "POST":
        username_raw = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        campaign_code = (request.form.get("campaign_code") or "").strip()
        campaign_code_mode = request.args.get("campaign_code") == "1"
        registration_key = (
            request.form.get("registration_key", "").strip().replace("_", "-").upper()
        )
        username = (username_raw or "").strip()
        email = (request.form.get("email") or "").strip().lower() or None

        if campaign_code_mode:
            return _handle_campaign_code_register(
                username,
                password,
                confirm_password,
                email,
                campaign_code,
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

        if not username or not password or not confirm_password:
            if keyed:
                db.session.rollback()
            flash("All fields are required!", "warning")
            return _register_redirect_fail(registration_key)

        if password != confirm_password:
            if keyed:
                db.session.rollback()
            flash("Passwords do not match.", "danger")
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

        if User.query.filter_by(username=username).first():
            if keyed:
                db.session.rollback()
            flash("Username already exists!", "warning")
            return _register_redirect_fail(registration_key)

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
                new_user = User(username=username, role="Both", email=email)
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

                try:
                    _setup_new_unified_user(new_user, campaign_code)
                except (InvalidCodeError, SeatCapError, WrongRoleError, JoinCodeError) as e:
                    db.session.rollback()
                    flash(
                        getattr(e, "args", [None])[0]
                        or "Could not join with that campaign code.",
                        "danger",
                    )
                    return _register_redirect_fail(registration_key)

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
            new_user = User(username=username, role="Both", email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()

            try:
                _setup_new_unified_user(new_user, campaign_code)
            except (InvalidCodeError, SeatCapError, WrongRoleError, JoinCodeError) as e:
                db.session.rollback()
                flash(
                    getattr(e, "args", [None])[0]
                    or "Could not join with that campaign code.",
                    "danger",
                )
                return redirect(url_for("auth.register"))

            db.session.commit()
            flash("Account created! You can now log in.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            log.exception("Registration error: %s", e)
            flash(f"Error creating account: {str(e)}", "danger")
            return redirect(url_for("auth.register"))

    vault_key = request.args.get("vault_key")
    email = (request.args.get("email") or "").strip().lower()
    campaign_code_mode = request.args.get("campaign_code") == "1"
    return render_template(
        "register.html",
        vault_key=vault_key,
        email=email,
        campaign_code_mode=campaign_code_mode,
    )


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

    otp_ok = False
    if user:
        try:
            otp_ok = user.verify_reset_otp(otp_code)
        except (ValueError, TypeError) as e:
            log.warning("Reset OTP verify failed: %s", e)
            otp_ok = False

    if not (user and otp_ok):
        flash("Invalid or expired reset code.", "danger")
        return render_template("reset_password.html")

    # Prod skips runtime schema bootstrap; password reuse helpers require this table.
    try:
        ensure_user_password_history_table()
    except Exception as e:
        log.warning("ensure_user_password_history_table: %s", e)
        try:
            db.session.rollback()
        except Exception:
            pass

    try:
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
        db.session.commit()
    except (OperationalError, ProgrammingError) as e:
        db.session.rollback()
        log.exception("Reset password database error: %s", e)
        flash("Something went wrong. Please try again.", "danger")
        return render_template("reset_password.html")
    except Exception as e:
        db.session.rollback()
        log.exception("Reset password error: %s", e)
        flash("Something went wrong. Please try again.", "danger")
        return render_template("reset_password.html")

    flash("Password reset successful. You may now log in.", "success")
    return redirect(url_for("auth.login"))


@login_required
def handle_post_submission():
    data = request.get_json(silent=True) or {}
    result = build_submission(data, current_user, session)
    if isinstance(result, SubmissionValidationError):
        return jsonify({"error": result.message}), result.status_code
    prompted_key = (result.extra or {}).get("prompted_key")
    existing = None
    if prompted_key:
        candidates = UserSubmission.query.filter_by(
            user_id=current_user.id,
            kind=result.kind,
            title=result.title,
        ).all()
        existing = next(
            (
                row
                for row in candidates
                if isinstance(row.extra, dict)
                and row.extra.get("prompted_key") == prompted_key
            ),
            None,
        )
    if existing is not None:
        existing.category = result.category
        existing.body = result.body
        existing.extra = result.extra
        existing.page_url = result.page_url
        existing.campaign_id = result.campaign_id
        existing.submitted_session_mode = result.submitted_session_mode
        existing.account_role = result.account_role
        existing.username_snapshot = result.username_snapshot
        existing.status = "pending"
        existing.created_at = datetime.utcnow()
    else:
        db.session.add(result)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("user_submission commit failed")
        return jsonify({"error": "Could not save submission."}), 500
    if existing is not None:
        return jsonify(
            {"success": True, "message": "Submission updated successfully."}
        ), 200
    return jsonify(
        {"success": True, "message": "Submission received successfully."}
    ), 201


@login_required
def handle_get_avatar():
    path = user_avatar_service.avatar_path_for_user(current_user.id)
    if not path.exists():
        abort(404)
    return send_file(path, mimetype="image/webp")


@login_required
def handle_upload_avatar():
    if "avatar" not in request.files:
        return jsonify({"error": "No file provided."}), 400
    file = request.files["avatar"]
    if not file or not file.filename:
        return jsonify({"error": "Empty filename."}), 400
    try:
        user_avatar_service.save_avatar(current_user.id, file)
        ts = user_avatar_service.touch_avatar_timestamp(current_user)
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "avatar_url": f"{url_for('auth.account_avatar')}?t={int(ts.timestamp())}",
            }
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        db.session.rollback()
        log.exception("avatar upload failed")
        return jsonify({"error": "Could not process image."}), 500
