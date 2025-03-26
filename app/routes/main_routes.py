from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def index():
    return redirect(url_for("auth.login"))

@main_bp.route("/home")
@login_required
def home():
    if current_user.role == "GM":
        return redirect(url_for("main.gm_dashboard"))
    else:
        return redirect(url_for("main.player_dashboard"))

@main_bp.route("/gm_dashboard")
@login_required
def gm_dashboard():
    return render_template("GM_Home.html")

@main_bp.route("/player_dashboard")
@login_required
def player_dashboard():
    return redirect(url_for("player.player_home"))
