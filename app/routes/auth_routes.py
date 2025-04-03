from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, bcrypt
from app.models.users import User, Player, GMProfile
from app.services.logging_config import auth_logger

auth = Blueprint("auth", __name__)

@auth.route("/login", methods=["GET", "POST"])
def login():
    print(f"DEBUG: Request method: {request.method}")
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        print(f"DEBUG: Attempting login for {username}")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            try:
                login_user(user)
                user.update_activity()  # Update last active timestamp
                session["user_id"] = user.id  # Force session set
                session.modified = True       # Ensure it saves
                print(f"DEBUG: User authenticated, ID: {user.id}, Role: {user.role}")
                print(f"DEBUG: Current user: {current_user.is_authenticated}")
                flash("Logged in successfully.", "success")
                # Fix the endpoint names here
                target = "gm.home" if user.role == "GM" else "player.player_home"
                print(f"DEBUG: Redirecting to {target}")
                return redirect(url_for(target))
            except Exception as e:
                flash(f"An error occurred: {str(e)}", "danger")
                print(f"DEBUG: Exception during login: {str(e)}")
                return redirect(url_for("auth.login"))
        else:
            flash("Invalid username or password.", "error")
            print("DEBUG: Invalid credentials")
    
    print("DEBUG: Rendering login.html")
    return render_template("login.html")

@auth.route("/logout")
@login_required
def logout():
    if current_user.is_authenticated:
        current_user.update_activity()  # Update last active timestamp before logout
    logout_user()
    session.pop("user_id", None) 
    flash("Logged out successfully.", "success")
    return redirect(url_for("auth.login"))

# @auth.route("/debug_user")
# @login_required
# def debug_user():
#     print(f"DEBUG: Session data: {session.items()}")
#     user_id = session.get("user_id")
#     user = db.session.get(User, user_id) if user_id else None
#     return f"User ID from session: {user_id}, User from DB: {user}"


@auth.route("/register", methods=["GET", "POST"])
def register():
    auth_logger.info("Registration route accessed")
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        gm_id = request.form.get("gm_id") if role == "Player" else None

        auth_logger.debug(f"Registration attempt - Username: {username}, Role: {role}, GM ID: {gm_id}")

        # Validate required fields
        if not username or not password or not role:
            auth_logger.warning(f"Registration failed - Missing required fields. Username: {username}, Role: {role}")
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
                    user_id=new_user.id,
                    gm_profile_id=gm_profile.id,
                    currency=0
                )
                db.session.add(player)
                auth_logger.debug(f"Created Player profile for user ID: {new_user.id}")

            # Commit the transaction
            db.session.commit()
            auth_logger.info(f"Successfully registered new user: {username} with role: {role}")
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

