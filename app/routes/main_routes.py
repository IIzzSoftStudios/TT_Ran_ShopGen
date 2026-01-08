from flask import Blueprint, render_template, redirect, url_for, session
from flask_login import login_required, current_user
from app.routes.handlers.campaign_selection_handler import select_campaign, load_campaign

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def index():
    return redirect(url_for("auth.login"))

@main_bp.route("/campaigns")
@login_required
def campaigns():
    """Campaign selection page - shows all campaigns the user is in"""
    return select_campaign()

@main_bp.route("/campaigns/load/<int:campaign_id>")
@login_required
def load_campaign_route(campaign_id):
    """Load a specific campaign and redirect to home"""
    return load_campaign(campaign_id)

@main_bp.route("/home")
@login_required
def home():
    """Redirect to campaign selection if no campaign is selected, otherwise go to appropriate home"""
    if 'campaign_id' not in session:
        return redirect(url_for("main.campaigns"))
    
    if current_user.role == "GM":
        return redirect(url_for("gm.gm_home"))
    else:
        return redirect(url_for("player.player_home"))

@main_bp.route("/player_dashboard")
@login_required
def player_dashboard():
    return redirect(url_for("player.player_home"))
