"""
Auth Login Handler
Handles user login and logout functionality
"""
from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, current_user
from app.models.users import User
from app.services.logging_config import auth_logger


def handle_login():
    """Handle user login"""
    auth_logger.debug(f"Login route accessed - Method: {request.method}")
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        auth_logger.debug(f"Login attempt for username: {username}")
        
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            # Check email verification if required
            require_verification = current_app.config.get('REQUIRE_EMAIL_VERIFICATION', False)
            if require_verification and not user.email_verified:
                flash("Please verify your email address before logging in. Check your inbox for the verification link.", "warning")
                auth_logger.warning(f"Login blocked - Email not verified for user: {username}")
                return redirect(url_for("auth.resend_verification"))
            
            # Check if 2FA is enabled
            require_2fa = current_app.config.get('REQUIRE_2FA', False)
            if user.two_factor_enabled or require_2fa:
                # Store user ID in session for 2FA verification
                session["2fa_user_id"] = user.id
                auth_logger.debug(f"2FA required for user: {username}")
                return render_template("2fa_verify.html", user_id=user.id)
            
            # No 2FA required, proceed with login
            try:
                login_user(user)
                user.update_activity()
                session["user_id"] = user.id
                session.modified = True
                auth_logger.info(f"User logged in successfully: {username}")
                flash("Logged in successfully.", "success")
                target = "gm.gm_home" if user.role == "GM" else "player.player_home"
                return redirect(url_for(target))
            except Exception as e:
                auth_logger.error(f"Error during login: {str(e)}", exc_info=True)
                flash(f"An error occurred: {str(e)}", "danger")
                return redirect(url_for("auth.login"))
        else:
            auth_logger.warning(f"Invalid login attempt for username: {username}")
            flash("Invalid username or password.", "error")
    
    return render_template("login.html")


def handle_logout():
    """Handle user logout"""
    if current_user.is_authenticated:
        current_user.update_activity()  # Update last active timestamp before logout
    logout_user()
    session.pop("user_id", None) 
    flash("Logged out successfully.", "success")
    return redirect(url_for("auth.login"))

