from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, User 
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
                target = "main.gm_dashboard" if user.role == "GM" else "main.player_dashboard"
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

@auth.route("/debug_user")
@login_required
def debug_user():
    print(f"DEBUG: Session data: {session.items()}")
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    return f"User ID from session: {user_id}, User from DB: {user}"


@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "warning")
            return redirect(url_for("auth.register"))

        new_user = User(username=username, role=role)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash("Account created! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")

