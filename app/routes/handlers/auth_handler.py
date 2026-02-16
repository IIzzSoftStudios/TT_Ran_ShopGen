from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime

from app.extensions import db, bcrypt  # bcrypt kept for potential future use
from app.models.users import User, Player, GMProfile
from app.services.logging_config import auth_logger


def handle_login():
    """Handle user login logic."""
    print(f"DEBUG: Request method: {request.method}")

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        print(f"DEBUG: Attempting login for {username}")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            try:
                # Login user - Flask-Login will handle session management
                login_user(user, remember=True)

                # Update activity after login
                user.last_active = datetime.utcnow()
                db.session.commit()

                print(f"DEBUG: User authenticated, ID: {user.id}, Role: {user.role}")
                print(f"DEBUG: Current user authenticated: {current_user.is_authenticated}")
                flash("Logged in successfully.", "success")
                # Redirect to campaign selection page
                print("DEBUG: Redirecting to campaign selection")
                return redirect(url_for("main.campaigns"))
            except Exception as e:
                flash(f"An error occurred: {str(e)}", "danger")
                print(f"DEBUG: Exception during login: {str(e)}")
                return redirect(url_for("auth.login"))
        else:
            flash("Invalid username or password.", "error")
            print("DEBUG: Invalid credentials")

    print("DEBUG: Rendering login.html")
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

        auth_logger.debug(
            f"Registration attempt - Username: {username}, Role: {role}, GM ID: {gm_id}"
        )

        # Validate required fields
        if not username or not password or not role:
            auth_logger.warning(
                f"Registration failed - Missing required fields. Username: {username}, Role: {role}"
            )
            flash("All fields are required!", "warning")
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

        try:
            auth_logger.debug("Starting user creation process")
            # Create the user
            new_user = User(username=username, role=role)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()  # This assigns the ID to new_user
            auth_logger.debug(f"Created new user with ID: {new_user.id}")

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
                auth_logger.debug(f"Created Player profile for user ID: {new_user.id}")

            # Commit the transaction
            db.session.commit()
            auth_logger.info(
                f"Successfully registered new user: {username} with role: {role}"
            )
            flash("Account created! You can now log in.", "success")
            return redirect(url_for("auth.login"))

        except Exception as e:
            db.session.rollback()
            auth_logger.error(f"Error during registration: {str(e)}", exc_info=True)
            flash(f"Error creating account: {str(e)}", "danger")
            return redirect(url_for("auth.register"))

    # GET request - show registration form
    # Get list of GMs for the dropdown
    gms = User.query.filter_by(role="GM").all() if request.method == "GET" else []
    auth_logger.debug(f"Rendering registration form with {len(gms)} GMs available")
    return render_template("register.html", gms=gms)


def handle_forgot_password():
    """Handle password reset requests."""
    if request.method == "POST":
        username = request.form.get("username")
        auth_logger.info(f"Password reset requested for username: {username}")

        if not username:
            flash("Username is required!", "warning")
            return redirect(url_for("auth.forgot_password"))

        user = User.query.filter_by(username=username).first()
        if user:
            # Generate reset token
            token = user.generate_reset_token()
            auth_logger.info(f"Generated reset token for user: {username}")

            # For now, we'll show the token on the page (in production, this would be emailed)
            flash(
                f"Password reset token generated! Use this token to reset your password: {token}",
                "info",
            )
            return redirect(url_for("auth.reset_password", token=token))
        else:
            # Don't reveal if username exists for security
            flash(
                "If the username exists, a password reset token has been generated.",
                "info",
            )
            return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


def handle_reset_password(token):
    """Handle password reset with token."""
    if request.method == "POST":
        new_password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not new_password or not confirm_password:
            flash("All fields are required!", "warning")
            return redirect(url_for("auth.reset_password", token=token))

        if new_password != confirm_password:
            flash("Passwords do not match!", "warning")
            return redirect(url_for("auth.reset_password", token=token))

        # Find user with this token
        user = User.query.filter_by(reset_token=token).first()
        if not user or not user.verify_reset_token(token):
            flash("Invalid or expired reset token!", "error")
            return redirect(url_for("auth.forgot_password"))

        # Update password
        user.set_password(new_password)
        user.clear_reset_token()
        auth_logger.info(f"Password reset successful for user: {user.username}")
        flash("Password updated successfully! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    # GET request - show reset form
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        flash("Invalid or expired reset token!", "error")
        return redirect(url_for("auth.forgot_password"))

    return render_template("reset_password.html", token=token)


def handle_admin_reset():
    """Admin utility to generate reset token for testing."""
    auth_logger.info(f"Admin reset called with method: {request.method}")
    auth_logger.info(f"Form data: {request.form}")
    auth_logger.info(f"Args data: {request.args}")

    if request.method == "POST":
        username = request.form.get("username")
        auth_logger.info(f"POST - Username from form: {username}")
    else:
        username = request.args.get("username")
        auth_logger.info(f"GET - Username from args: {username}")

    if not username:
        auth_logger.warning("No username provided")
        flash("Username is required!", "warning")
        return redirect(url_for("gm.gm_home"))

    user = User.query.filter_by(username=username).first()
    if not user:
        auth_logger.warning(f"User not found: {username}")
        flash(f"User '{username}' not found!", "error")
        return redirect(url_for("gm.gm_home"))

    token = user.generate_reset_token()
    auth_logger.info(f"Admin generated reset token for user: {username}")
    flash(f"Reset token for {username}: {token}", "info")
    return redirect(url_for("auth.reset_password", token=token))

