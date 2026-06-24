"""Creator partnership intake — email only, no persistence."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import app as flask_app


@pytest.fixture(autouse=True)
def _disable_csrf():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    yield
    flask_app.config["WTF_CSRF_ENABLED"] = True


def _creator_form(**overrides):
    base = {
        "full_name": "Casey Creator",
        "email": "casey@ttrpgmedia.com",
        "primary_platform": "youtube_shorts",
        "channel_url": "https://youtube.com/@caseygm",
        "audience_size": "10k_50k",
        "content_focus": ["ttrpg", "gm_advice"],
        "avg_views_note": "Average 8k views per Short",
        "partnership_type": "product_exchange",
        "campaign_pitch": "Weekly actual-play clips showing market day ticks after player loot dumps.",
    }
    base.update(overrides)
    return base


def test_creator_partnership_get(client):
    resp = client.get("/creator-partnership")
    assert resp.status_code == 200
    assert b"Creator / Sponsor Partnership" in resp.data


@patch("app.routes.main_routes.send_creator_partnership_emails")
def test_creator_submit_sends_email(mock_send, client):
    resp = client.post("/creator-partnership", data=_creator_form(), follow_redirects=False)
    assert resp.status_code == 302
    assert "/creator-partnership-thanks" in resp.location
    mock_send.assert_called_once()
    assert mock_send.call_args[0][0]["audience_size"] == "10k_50k"


@patch("app.routes.main_routes.send_creator_partnership_emails")
def test_paid_sponsorship_requires_rate(mock_send, client):
    resp = client.post(
        "/creator-partnership",
        data=_creator_form(partnership_type="paid_sponsorship", rate_or_cpm=""),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"rate" in resp.data.lower() or b"CPM" in resp.data
    mock_send.assert_not_called()


@patch("app.routes.main_routes.send_creator_partnership_emails")
def test_content_focus_required(mock_send, client):
    resp = client.post(
        "/creator-partnership",
        data=_creator_form(content_focus=[]),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    mock_send.assert_not_called()


def test_landing_has_creators_button(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Creators" in resp.data
