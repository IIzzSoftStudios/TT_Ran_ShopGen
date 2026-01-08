"""
Auth Registration Handler
Handles user registration functionality
"""
from flask import render_template, redirect, url_for, flash, request, current_app
from app.extensions import db
from app.models.users import User, Player, GMProfile
from app.services.logging_config import auth_logger
from app.services.email_service import send_verification_email
import re


def validate_email(email):
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def handle_register():
    """Handle user registration"""
    auth_logger.info("Registration route accessed")
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")
        gm_id = request.form.get("gm_id") if role == "Player" else None

        auth_logger.debug(f"Registration attempt - Username: {username}, Email: {email}, Role: {role}, GM ID: {gm_id}")

        # Validate required fields
        if not username or not email or not password or not role:
            auth_logger.warning(f"Registration failed - Missing required fields. Username: {username}, Email: {email}, Role: {role}")
            flash("All fields are required!", "warning")
            return redirect(url_for("auth.register"))

        # Validate email format
        if not validate_email(email):
            auth_logger.warning(f"Registration failed - Invalid email format: {email}")
            flash("Please enter a valid email address!", "warning")
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
        
        if User.query.filter_by(email=email).first():
            auth_logger.warning(f"Registration failed - Email already exists: {email}")
            flash("Email address already registered!", "warning")
            return redirect(url_for("auth.register"))

        try:
            auth_logger.debug("Starting user creation process")
            # Create the user
            new_user = User(username=username, email=email, role=role, email_verified=False)
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
                    currency=0
                )
                db.session.add(player)
                auth_logger.debug(f"Created Player profile for user ID: {new_user.id}")

            # Commit the transaction
            db.session.commit()
            
            # Send verification email
            try:
                if send_verification_email(new_user):
                    auth_logger.info(f"Verification email sent to {email}")
                    if current_app.config.get('REQUIRE_EMAIL_VERIFICATION', False):
                        flash("Account created! Please check your email to verify your account before logging in.", "success")
                    else:
                        flash("Account created! A verification email has been sent. You can log in now, but please verify your email soon.", "success")
                else:
                    auth_logger.warning(f"Failed to send verification email to {email}")
                    flash("Account created, but we couldn't send the verification email. Please contact support.", "warning")
            except Exception as e:
                auth_logger.error(f"Error sending verification email: {str(e)}", exc_info=True)
                flash("Account created, but there was an error sending the verification email. Please contact support.", "warning")
            
            auth_logger.info(f"Successfully registered new user: {username} with role: {role}")
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

