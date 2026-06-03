"""Phase 2 branding: changelog, retired routes, thank-you redirect, copy markers."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, GMProfile, Player, User
from tests.session_helpers import seed_client_session


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _player_with_campaign():
    gm_user = User(username="gm-p2", password="x", role="GM")
    gm_user.set_password("Secret1!")
    db.session.add(gm_user)
    db.session.flush()
    gm_profile = GMProfile(user_id=gm_user.id)
    db.session.add(gm_profile)
    db.session.flush()
    campaign = Campaign(
        gm_profile_id=gm_profile.id,
        name="Brand Camp",
        system_type="generic",
        is_active=True,
    )
    db.session.add(campaign)
    db.session.flush()
    player_user = User(username="player-p2", password="x", role="Player")
    player_user.set_password("Secret1!")
    db.session.add(player_user)
    db.session.flush()
    player = Player(
        user_id=player_user.id,
        campaign_id=campaign.id,
        is_npc=False,
        currency=100,
    )
    db.session.add(player)
    db.session.commit()
    return player_user, player, campaign


def test_docs_changelog_section_renders(client):
    resp = client.get("/docs?section=changelog")
    assert resp.status_code == 200
    assert b'id="section-changelog"' in resp.data
    assert b"Patch Notes" in resp.data
    assert b"Alpha 1.0" in resp.data
    assert b"Release notes for Econo-Forge Alpha" in resp.data
    assert b"Alpha status" in resp.data
    assert b"Alpha 1.0 keys now support up to 99 active campaigns." in resp.data


def test_thank_you_redirects_to_access_request(client):
    resp = client.get("/thank-you", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/access-request" in (resp.location or "")


def test_legacy_player_routes_redirect_to_home(client):
    user, player, _campaign = _player_with_campaign()
    seed_client_session(
        client,
        user,
        campaign_id=player.campaign_id,
        player_id=player.id,
        session_mode="player",
    )
    for path in ("/player/shops", "/player/cities", "/player/market"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (301, 302)
        assert "/player/home" in (resp.location or "")


def test_player_home_uses_browse_shops_not_market_route(client):
    user, player, _campaign = _player_with_campaign()
    seed_client_session(
        client,
        user,
        campaign_id=player.campaign_id,
        player_id=player.id,
        session_mode="player",
    )
    resp = client.get("/player/home")
    assert resp.status_code == 200
    assert b"Browse Shops" in resp.data
    assert b"#player-shops-browse" in resp.data
    assert b"player.view_market" not in resp.data


def test_404_page_shows_econo_forge_branding(client):
    resp = client.get("/this-route-does-not-exist-phase2")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data
    assert b"Econo-Forge" in resp.data or b"Back to home" in resp.data


def test_access_request_copy_uses_registration_key(client):
    resp = client.get("/access-request")
    assert resp.status_code == 200
    assert b"registration key" in resp.data.lower()


def test_docs_faq_explains_auto_access_vs_admin_triage(client):
    resp = client.get("/docs?section=faq")
    assert resp.status_code == 200
    assert b"auto-issues your registration key" in resp.data.lower() or b"auto-issues" in resp.data.lower()
    assert b"Manual Triage" in resp.data or b"admin triage" in resp.data.lower()
