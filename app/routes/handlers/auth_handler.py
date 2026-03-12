from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import db, bcrypt  # bcrypt kept for potential future use
from app.models.users import User, Player, GMProfile, RegistrationKey
from app.utils.validators import is_password_strong
from app.services.logging_config import auth_logger


def handle_login():
    """Handle user login logic."""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            try:
                # Login user - Flask-Login will handle session management
                login_user(user, remember=True)

                # Update activity after login
                user.last_active = datetime.utcnow()
                db.session.commit()

                # Decide redirect target based on role
                target_endpoint = "main.campaigns"
                if user.role == "vault_keeper":
                    target_endpoint = "admin.keys_overview"

                flash("Logged in successfully.", "success")
                return redirect(url_for(target_endpoint))
            except Exception as e:
                flash(f"An error occurred: {str(e)}", "danger")
                return redirect(url_for("auth.login"))
        else:
            flash("Invalid username or password.", "error")

    return render_template("login.html")


@login_required
def handle_logout():
    """Handle user logout logic."""
    if current_user.is_authenticated:
        # Update last active timestamp before logout
        current_user.update_activity()
    logout_user()
    flash("Logged out successfully.", "success")
    return redirect(url_for("auth.login"))


def handle_register():
    """Handle user registration logic."""
    auth_logger.info("Registration route accessed")

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        gm_id = request.form.get("gm_id") if role == "Player" else None
        registration_key = request.form.get("registration_key", "").strip().replace("_", "-").upper()

        auth_logger.debug(
            f"Registration attempt - Username: {username}, Role: {role}, GM ID: {gm_id}"
        )

        # Validate required fields
        if not username or not password or not role or not registration_key:
            auth_logger.warning(
                f"Registration failed - Missing required fields. Username: {username}, Role: {role}"
            )
            flash("All fields are required!", "warning")
            return redirect(url_for("auth.register"))

        # Password complexity (Wave 5)
        is_strong, msg = is_password_strong(password)
        if not is_strong:
            auth_logger.warning(f"Registration failed - Weak password for user: {username}")
            flash(msg, "danger")
            return redirect(url_for("auth.register"))

        # Validate role
        if role not in ["GM", "Player"]:
            auth_logger.warning(f"Registration failed - Invalid role: {role}")
            flash("Invalid role selected!", "warning")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(username=username).first():
            auth_logger.warning(f"Registration failed - Username already exists: {username}")
            flash("Username already exists!", "warning")
            return redirect(url_for("auth.register"))

        email = (request.form.get("email") or "").strip().lower() or None
        if email and User.query.filter_by(email=email).first():
            flash("That email is already registered.", "warning")
            return redirect(url_for("auth.register"))

        try:
            # Lock the key row (SELECT FOR UPDATE) to prevent concurrent use of the same key
            key_row = RegistrationKey.query.filter_by(key_code=registration_key).with_for_update().first()
            if not key_row or key_row.is_used:
                db.session.rollback()
                auth_logger.warning(f"Registration failed - Invalid or used key for user: {username}")
                flash("Invalid or already used registration key.", "danger")
                return redirect(url_for("auth.register"))

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
            auth_logger.info(
                f"Successfully registered new user: {username} with role: {role}"
            )
            flash("Account created! You can now log in.", "success")
            return redirect(url_for("auth.login"))

        except (IntegrityError, OperationalError, ValueError) as e:
            db.session.rollback()
            auth_logger.error(f"Database/validation error during registration: {e}", exc_info=True)
            flash("A database error occurred. Please try again later.", "danger")
            return redirect(url_for("auth.register"))
        except Exception as e:
            db.session.rollback()
            auth_logger.error(f"Error during registration: {str(e)}", exc_info=True)
            flash("Error creating account. Please try again.", "danger")
            return redirect(url_for("auth.register"))

    # GET request - show registration form
    # Get list of GMs for the dropdown
    gms = User.query.filter_by(role="GM").all() if request.method == "GET" else []
    auth_logger.debug(f"Rendering registration form with {len(gms)} GMs available")
    return render_template("register.html", gms=gms)


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

