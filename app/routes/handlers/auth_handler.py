from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
import json
from pathlib import Path
from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import db, bcrypt  # bcrypt kept for potential future use
from app.models.users import User, Player, GMProfile, RegistrationKey, AccessRequest
from app.utils.validators import is_password_strong
from app.services.logging_config import auth_logger


def _debug_log(hypothesis_id, location, message, data, run_id="pre_fix"):
    """
    Minimal NDJSON logging for debug mode.
    Avoid secrets (vault keys) and personal data (email addresses).
    """
    # Repo-relative path (no machine-specific absolute Windows path).
    # File ends up at: <project_root>/debug-a4354b.log
    log_path = Path(__file__).resolve().parents[4] / "debug-a4354b.log"
    payload = {
        "sessionId": "a4354b",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(__import__("time").time() * 1000),
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def handle_login():
    """Handle user login logic."""
    # If the user is already authenticated, respect any explicit next parameter
    # or fall back to the standard post-login targets.
    next_url = request.args.get("next") or request.form.get("next")
    if not next_url:
        # One-time carry-over from a forced logout performed by hitting
        # `/auth/login` while authenticated.
        next_url = session.pop("post_login_next", None)
    if current_user.is_authenticated:
        # UX fix: if a user is already authenticated and returns to /auth/login,
        # force a clean logout + re-auth flow to avoid "stuck" session/redirect loops.
        logout_user()
        # Hard-reset any stale session state; flash must be added after this.
        session.clear()
        flash("You have been logged out for security.", "info")
        # Preserve `next` across this forced logout.
        if next_url and next_url.startswith("/"):
            session["post_login_next"] = next_url

        # Break any redirect loop by sending the user elsewhere.
        response = redirect(url_for("main.index"))

        # Extra safety: clear "remember me" so the user isn't still
        # treated as authenticated on the next request.
        try:
            # Flask-Login defaults:
            # - cookie name: "remember_token"
            # - cookie path: defaults to "/" if not overridden.
            remember_cookie_name = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
            remember_cookie_path = current_app.config.get(
                "REMEMBER_COOKIE_PATH",
                current_app.config.get("SESSION_COOKIE_PATH", "/"),
            )

            # Delete at the configured remember cookie path, and also
            # attempt "/" as a fallback for environments that hard-set "/".
            response.delete_cookie(remember_cookie_name, path=remember_cookie_path)
            if remember_cookie_path != "/":
                response.delete_cookie(remember_cookie_name, path="/")
        except Exception:
            pass

        return response

    if request.method == "POST":
        identifier = (request.form.get("username") or "").strip()
        password = request.form.get("password")
        user = None
        matched_by = None  # for logging only; do not log the identifier itself

        # Support logging in with either username or email.
        if identifier:
            user = User.query.filter_by(username=identifier).first()
            if user:
                matched_by = "username"
            else:
                email = identifier.lower()
                user = User.query.filter_by(email=email).first()
                if user:
                    matched_by = "email"

        if user and user.check_password(password):
            try:
                # Login user - Flask-Login will handle session management
                login_user(user, remember=True)

                # Update activity after login
                user.last_active = datetime.utcnow()
                db.session.commit()

                # If we were sent here from a protected endpoint, honor the
                # original destination when it is a local URL.
                if next_url and next_url.startswith("/"):
                    flash("Logged in successfully.", "success")
                    return redirect(next_url)

                # Decide redirect target based on role
                target_endpoint = "main.campaigns"
                if user.role == "vault_keeper":
                    target_endpoint = "admin.keys_overview"

                flash("Logged in successfully.", "success")
                return redirect(url_for(target_endpoint))
            except Exception as e:
                auth_logger.error("Login failed during session setup.", exc_info=True)
                flash(f"An error occurred: {str(e)}", "danger")
                return redirect(url_for("auth.login"))
        else:
            if user:
                auth_logger.warning(
                    "Login failed | password_mismatch=true "
                    f"| matched_by={matched_by or 'unknown'}"
                )
                flash("Wrong password.", "error")
            else:
                auth_logger.warning(
                    "Login failed | no_user_found=true | matched_by=none"
                )
                flash("Wrong email or username.", "error")

    # GET request or failed POST: render login form, preserving any next param
    return render_template("login.html", next=next_url)


@login_required
def handle_logout():
    """Handle user logout logic."""
    if current_user.is_authenticated:
        # Update last active timestamp before logout
        current_user.update_activity()
    logout_user()
    flash("Logged out successfully.", "success")
    return redirect(url_for("auth.login"))


def _register_redirect_fail(registration_key=""):
    """Preserve vault_key in URL so users don't lose the key after a failed POST."""
    key = (registration_key or "").strip()
    if key:
        return redirect(url_for("auth.register", vault_key=key))
    return redirect(url_for("auth.register"))


def handle_register():
    """Handle user registration logic."""
    auth_logger.info("Registration route accessed")

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        gm_id = request.form.get("gm_id") if role == "Player" else None
        registration_key = request.form.get("registration_key", "").strip().replace("_", "-").upper()
        # Query string can carry vault_key on POST (browser keeps ?vault_key= on same-URL submit)
        if not registration_key:
            registration_key = (request.args.get("vault_key") or "").strip().replace("_", "-").upper()

        auth_logger.debug(
            f"Registration attempt - Username: {username}, Role: {role}, GM ID: {gm_id}"
        )

        # #region agent log
        _debug_log(
            hypothesis_id="H1",
            location="auth_handler:handle_register:post_entry",
            message="Registration POST received",
            data={
                "registration_key_len": len(registration_key),
                "registration_key_from_form": bool(request.form.get("registration_key", "").strip()),
                "registration_key_from_query": bool((request.args.get("vault_key") or "").strip()),
                "role": role,
                "has_username": bool(username),
                "has_password": bool(password),
            },
        )
        # #endregion

        # Validate required fields
        if not username or not password or not role or not registration_key:
            auth_logger.warning(
                f"Registration failed - Missing required fields. Username: {username}, Role: {role}"
            )
            # #region agent log
            _debug_log(
                hypothesis_id="H1",
                location="auth_handler:handle_register:missing_fields",
                message="Registration blocked: missing required fields",
                data={"registration_key_len": len(registration_key or "")},
            )
            # #endregion
            flash("All fields are required!", "warning")
            return _register_redirect_fail(registration_key)

        # Password complexity (Wave 5)
        is_strong, msg = is_password_strong(password)
        if not is_strong:
            auth_logger.warning(f"Registration failed - Weak password for user: {username}")
            flash(msg, "danger")
            return _register_redirect_fail(registration_key)

        # Validate role
        if role not in ["GM", "Player"]:
            auth_logger.warning(f"Registration failed - Invalid role: {role}")
            flash("Invalid role selected!", "warning")
            return _register_redirect_fail(registration_key)

        if User.query.filter_by(username=username).first():
            auth_logger.warning(f"Registration failed - Username already exists: {username}")
            flash("Username already exists!", "warning")
            return _register_redirect_fail(registration_key)

        email = (request.form.get("email") or "").strip().lower() or None
        if email and User.query.filter_by(email=email).first():
            flash("That email is already registered.", "warning")
            return _register_redirect_fail(registration_key)

        key_row = None
        try:
            # Lock the key row (SELECT FOR UPDATE) to prevent concurrent use of the same key
            key_row = RegistrationKey.query.filter_by(key_code=registration_key).with_for_update().first()

            # #region auth_logger log
            auth_logger.info(
                "Register: key lookup | "
                f"registration_key_len={len(registration_key or '')} "
                f"key_row_found={bool(key_row)} "
                f"key_row_id={key_row.id if key_row else None} "
                f"key_row_is_used={key_row.is_used if key_row else None} "
                f"key_row_email_set={bool(key_row.email) if key_row else False}"
            )
            # #endregion

            # #region agent log
            _debug_log(
                hypothesis_id="E",
                location="auth_handler:handle_register:lookup_registration_key",
                message="Registration key lookup completed",
                data={
                    "key_row_found": bool(key_row),
                    "key_row_is_used": bool(key_row.is_used) if key_row else None,
                    "key_row_email_is_set": bool(key_row.email) if key_row else False,
                },
            )
            # #endregion

            if not key_row or key_row.is_used:
                db.session.rollback()
                auth_logger.warning(f"Registration failed - Invalid or used key for user: {username}")
                flash("Invalid or already used registration key.", "danger")
                return _register_redirect_fail(registration_key)

            # URL-guessing defense: if the key is tied to an applicant email,
            # enforce that the user registers with the same email.
            # (Frontend may prefill the key from query params; backend is source of truth.)
            key_email_norm = (key_row.email or "").strip().lower()
            if key_row.email:
                if not email or key_email_norm != email:
                    db.session.rollback()

                    # #region agent log
                    _debug_log(
                        hypothesis_id="H2",
                        location="auth_handler:handle_register:email_mismatch_block",
                        message="Registration blocked due to email mismatch for keyed access",
                        data={
                            "email_mismatch": True,
                            "key_row_email_is_set": True,
                            "submitted_email_nonempty": bool(email),
                        },
                    )
                    # #endregion

                    flash(
                        "Registration key email mismatch. Use the same email you used on the access request.",
                        "danger",
                    )
                    return _register_redirect_fail(registration_key)
            else:
                # #region agent log
                _debug_log(
                    hypothesis_id="E",
                    location="auth_handler:handle_register:email_validation_skipped",
                    message="Email mismatch defense skipped (registration key not tied to applicant email)",
                    data={"key_row_email_is_set": False},
                )
                # #endregion

            auth_logger.debug("Starting user creation process (atomic handshake)")
            # 1. Create the user
            new_user = User(username=username, role=role, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()  # Get ID without committing
            auth_logger.debug(f"Created new user with ID: {new_user.id}")

            # 2. Consume the registration key
            key_row.is_used = True
            key_row.user_id = new_user.id
            key_row.used_at = datetime.utcnow()

            # #region auth_logger log
            auth_logger.info(
                "Register: key consumed pre-commit | "
                f"key_row_id={key_row.id} "
                f"key_row_user_id={key_row.user_id} "
                f"key_row_used_at_set={key_row.used_at is not None}"
            )
            # #endregion

            # If this registration key came from an AccessRequest, mark it as used.
            if key_row.email:
                ar = AccessRequest.query.filter_by(vault_key=key_row.key_code).first()
                if ar:
                    ar.vault_key_used = True
                    ar.vault_key_used_at = datetime.utcnow()

            if role == "GM":
                auth_logger.debug("Creating GM Profile")
                # Create GM Profile
                gm_profile = GMProfile(user_id=new_user.id)
                db.session.add(gm_profile)
                auth_logger.debug(f"Created GM Profile for user ID: {new_user.id}")
            else:  # Player
                auth_logger.debug(f"Creating Player profile with GM ID: {gm_id}")
                # Get the GM's profile
                gm = User.query.get(gm_id)
                if not gm or gm.role != "GM":
                    auth_logger.error(f"Invalid GM selected: {gm_id}")
                    raise ValueError("Invalid GM selected")

                gm_profile = GMProfile.query.filter_by(user_id=gm.id).first()
                if not gm_profile:
                    auth_logger.error(f"GM profile not found for GM ID: {gm.id}")
                    raise ValueError("GM profile not found")

                # Create Player profile linked to GM
                player = Player(
                    user_id_player=new_user.id,
                    gm_profile_id=gm_profile.id,
                    user_id_gm=gm.id,
                    currency=0,
                )
                db.session.add(player)
                db.session.flush()  # Get player.id before committing
                auth_logger.debug(f"Created Player profile for user ID: {new_user.id}")
                
                # Automatically add this new player to all existing active campaigns for this GM
                from app.models.campaigns import Campaign, CampaignPlayer
                from app.services.billing_rules import can_add_player_to_campaign
                
                existing_campaigns = Campaign.query.filter_by(
                    gm_profile_id=gm_profile.id,
                    is_active=True
                ).all()
                
                campaigns_added = 0
                for campaign in existing_campaigns:
                    can_add, _ = can_add_player_to_campaign(campaign)
                    if can_add:
                        # Check if membership already exists
                        existing_membership = CampaignPlayer.query.filter_by(
                            campaign_id=campaign.id,
                            player_id=player.id
                        ).first()
                        if not existing_membership:
                            membership = CampaignPlayer(
                                campaign_id=campaign.id,
                                player_id=player.id,
                                status="active",
                                is_active=True,
                            )
                            db.session.add(membership)
                            campaigns_added += 1
                
                if campaigns_added > 0:
                    auth_logger.debug(f"Added new player to {campaigns_added} existing campaign(s)")

            # 4. Commit the transaction (atomic handshake)
            db.session.commit()

            # Post-commit verification: re-read key row state from DB.
            # This also guards against any unexpected session/transaction behavior.
            consumed_check = RegistrationKey.query.filter_by(key_code=registration_key).first()
            auth_logger.info(
                "Register: post-commit key state | "
                f"key_row_found={bool(consumed_check)} "
                f"key_row_id={consumed_check.id if consumed_check else None} "
                f"key_row_is_used={consumed_check.is_used if consumed_check else None} "
                f"key_row_user_id={consumed_check.user_id if consumed_check else None} "
                f"key_row_used_at_set={consumed_check.used_at is not None if consumed_check else None}"
            )

            auth_logger.info(
                f"Successfully registered new user: {username} with role: {role}"
            )
            # #region agent log
            _debug_log(
                hypothesis_id="H5",
                location="auth_handler:handle_register:commit_success",
                message="Registration committed",
                data={"new_user_id": new_user.id, "role": role},
            )
            # #endregion
            flash(
                "Account created! Log in with your username (not email) and password.",
                "success",
            )
            return redirect(url_for("auth.login"))

        except (IntegrityError, OperationalError, ValueError) as e:
            db.session.rollback()
            auth_logger.error(f"Database/validation error during registration: {e}", exc_info=True)

            auth_logger.info(
                "Register: rollback (validation/db error) | "
                f"key_row_found={bool(key_row)} "
                f"key_row_id={key_row.id if key_row else None} "
                f"key_row_is_used_before_rollback={key_row.is_used if key_row else None} "
                f"key_row_user_id_before_rollback={key_row.user_id if key_row else None}"
            )
            # #region agent log
            _debug_log(
                hypothesis_id="H3",
                location="auth_handler:handle_register:db_error",
                message="Registration rolled back",
                data={"exc_type": e.__class__.__name__},
            )
            # #endregion
            flash("A database error occurred. Please try again later.", "danger")
            return _register_redirect_fail(registration_key)
        except Exception as e:
            db.session.rollback()
            auth_logger.error(f"Error during registration: {str(e)}", exc_info=True)

            auth_logger.info(
                "Register: rollback (generic error) | "
                f"key_row_found={bool(key_row)} "
                f"key_row_id={key_row.id if key_row else None} "
                f"key_row_is_used_before_rollback={key_row.is_used if key_row else None} "
                f"key_row_user_id_before_rollback={key_row.user_id if key_row else None}"
            )
            # #region agent log
            _debug_log(
                hypothesis_id="H3",
                location="auth_handler:handle_register:generic_error",
                message="Registration rolled back",
                data={"exc_type": e.__class__.__name__},
            )
            # #endregion
            flash("Error creating account. Please try again.", "danger")
            return _register_redirect_fail(registration_key)

    # GET request - show registration form
    # Get list of GMs for the dropdown
    gms = User.query.filter_by(role="GM").all() if request.method == "GET" else []
    auth_logger.debug(f"Rendering registration form with {len(gms)} GMs available")

    # Optional: pre-fill a vault key from approval link.
    vault_key_prefill = (request.args.get("vault_key") or "").strip().upper()

    # #region agent log
    _debug_log(
        hypothesis_id="D",
        location="auth_handler:handle_register:prefill_vault_key",
        message="Register prefill evaluated",
        data={
            "vault_key_prefill_present": bool(vault_key_prefill),
            "vault_key_prefill_len": len(vault_key_prefill),
        },
    )
    # #endregion

    return render_template("register.html", gms=gms, vault_key_prefill=vault_key_prefill)


def handle_forgot_password():
    """Handle password reset requests. Send 6-digit OTP via email (or log to console if SMTP not configured)."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        auth_logger.info(f"Password reset requested for email: {email}")

        if not email:
            flash("Email is required!", "warning")
            return redirect(url_for("auth.forgot_password"))

        user = User.query.filter_by(email=email).first()
        if user:
            import secrets
            code = "".join(secrets.choice("0123456789") for _ in range(6))
            user.set_reset_otp(code)
            db.session.commit()
            auth_logger.info(f"Generated OTP for user: {user.username}")

            try:
                from app.extensions import mail
                from flask_mailman import EmailMessage
                sender = current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@example.com")
                msg = EmailMessage(
                    "Your password reset code",
                    f"Your one-time password reset code is: {code}\n\nIt expires in 10 minutes.",
                    sender,
                    [email],
                )
                msg.send()
            except Exception as e:
                auth_logger.warning(f"Could not send OTP email: {e}. Logging code to console for testing.")
                print(f"[Auth] OTP for {email} (use within 10 min): {code}")

        # Always respond generically to avoid user enumeration
        flash(
            "If an account exists for that email, we sent a 6-digit code. Check your email (or server console for local testing).",
            "info",
        )
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


def handle_reset_password():
    """Handle password reset with email + OTP code. New password must pass is_password_strong."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        otp_code = request.form.get("otp_code", "").strip()
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not otp_code or not new_password or not confirm_password:
            flash("All fields are required!", "warning")
            return redirect(url_for("auth.reset_password"))

        if new_password != confirm_password:
            flash("Passwords do not match!", "warning")
            return redirect(url_for("auth.reset_password"))

        user = User.query.filter_by(email=email).first()
        if not user or not user.verify_reset_otp(otp_code):
            flash("Invalid or expired reset code. Request a new code from the forgot password page.", "error")
            return redirect(url_for("auth.forgot_password"))

        is_strong, msg = is_password_strong(new_password)
        if not is_strong:
            flash(msg, "danger")
            return redirect(url_for("auth.reset_password"))

        user.set_password(new_password)
        user.clear_reset_otp()
        db.session.commit()
        auth_logger.info(f"Password reset successful for user: {user.username}")
        flash("Password updated successfully! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html")


# handle_admin_reset removed: endpoint disabled (returns 404) to prevent token exposure.
# For local testing, use forgot-password; token is printed to server console.

