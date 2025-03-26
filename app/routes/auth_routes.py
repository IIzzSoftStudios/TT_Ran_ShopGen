from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User, Player, GMProfile
from app.extensions import bcrypt

auth = Blueprint("auth", __name__)

@auth.route("/login", methods=["GET", "POST"])
def login():
    print(f"DEBUG: Request method: {request.method}")
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        print(f"DEBUG: Attempting login for {username}")
        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            try:
                login_user(user)
                session["user_id"] = user.id  # Force session set
                session.modified = True       # Ensure it saves
                print(f"DEBUG: User authenticated, ID: {user.id}, Role: {user.role}")
                print(f"DEBUG: Current user: {current_user.is_authenticated}")
                flash("Login successful", "success")
                # Fix the endpoint names here
                target = "gm.home" if user.role == "GM" else "player.player_home"
                print(f"DEBUG: Redirecting to {target}")
                return redirect(url_for(target))
            except Exception as e:
                flash(f"An error occurred: {str(e)}", "danger")
                print(f"DEBUG: Exception during login: {str(e)}")
                return redirect(url_for("auth.login"))
        else:
            flash("Invalid username or password", "danger")
            print("DEBUG: Invalid credentials")
    
    print("DEBUG: Rendering login.html")
    return render_template("login.html")

@auth.route("/logout")
def logout():
    logout_user()
    session.pop("user_id", None) 
    flash("You have been logged out", "info")
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
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        gm_id = request.form.get("gm_id") if role == "Player" else None

        # Validate required fields
        if not username or not password or not role:
            flash("All fields are required!", "warning")
            return redirect(url_for("auth.register"))

        # Validate role
        if role not in ["GM", "Player"]:
            flash("Invalid role selected!", "warning")
            return redirect(url_for("auth.register"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "warning")
            return redirect(url_for("auth.register"))

        try:
            # Create the user
            new_user = User(username=username, role=role)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.flush()  # This assigns the ID to new_user

            if role == "GM":
                # Create GM Profile
                gm_profile = GMProfile(user_id=new_user.id)
                db.session.add(gm_profile)
            else:  # Player
                # Get the GM's profile
                gm = User.query.get(gm_id)
                if not gm or gm.role != "GM":
                    raise ValueError("Invalid GM selected")
                
                gm_profile = GMProfile.query.filter_by(user_id=gm.id).first()
                if not gm_profile:
                    raise ValueError("GM profile not found")

                # Create Player profile linked to GM
                player = Player(
                    user_id=new_user.id,
                    gm_profile_id=gm_profile.id,
                    currency=0
                )
                db.session.add(player)

            # Commit the transaction
            db.session.commit()
            flash("Account created! You can now log in.", "success")
            return redirect(url_for("auth.login"))

        except Exception as e:
            db.session.rollback()
            print(f"Error during registration: {str(e)}")  # Add debug logging
            flash(f"Error creating account: {str(e)}", "danger")
            return redirect(url_for("auth.register"))

    # GET request - show registration form
    # Get list of GMs for the dropdown
    gms = User.query.filter_by(role="GM").all() if request.method == "GET" else []
    return render_template("register.html", gms=gms)

