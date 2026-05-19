"""GM market overview API."""

from flask import jsonify
from flask_login import login_required

from app.routes.handlers.gm_helpers import get_current_gm_profile, require_active_campaign
from app.services.market_overview import build_market_overview_payload


@login_required
def get_market_overview_data():
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    campaign, redirect_response = require_active_campaign(gm_profile)
    if redirect_response:
        return redirect_response

    return jsonify(build_market_overview_payload(campaign.id))
