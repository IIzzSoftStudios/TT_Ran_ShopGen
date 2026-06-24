"""Investor deck request funnel — email only, no persistence."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import app as flask_app


@pytest.fixture(autouse=True)
def _disable_csrf():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    yield
    flask_app.config["WTF_CSRF_ENABLED"] = True


def _investor_form(**overrides):
    base = {
        "full_name": "Alex Investor",
        "email": "alex@forgeventures.com",
        "company_fund_name": "Forge Ventures",
        "fund_website": "https://www.forgeventures.com",
        "investor_status": "accredited",
        "check_size": "25000_50000",
        "prior_saas_gaming_invest": "yes",
        "confidentiality_ack": "yes",
    }
    base.update(overrides)
    return base


def test_investor_deck_request_get(client):
    resp = client.get("/investor-deck-request")
    assert resp.status_code == 200
    assert b"Request Investor Deck" in resp.data
    assert b"confidentiality" in resp.data.lower()


def test_public_deck_serves_pdf(client):
    resp = client.get("/public-deck")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"


@patch("app.routes.main_routes.send_investor_request_emails")
def test_investor_submit_sends_email_and_thanks(mock_send, client):
    resp = client.post("/investor-deck-request", data=_investor_form(), follow_redirects=False)
    assert resp.status_code == 302
    assert "/investor-deck-thanks" in resp.location
    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    assert payload["email"] == "alex@forgeventures.com"
    assert payload["investor_status"] == "accredited"


@patch("app.routes.main_routes.send_investor_request_emails")
def test_fund_website_accepts_bare_domain(mock_send, client):
    resp = client.post(
        "/investor-deck-request",
        data=_investor_form(fund_website="www.forgeventures.com"),
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/investor-deck-thanks" in resp.location
    payload = mock_send.call_args[0][0]
    assert payload["fund_website"] == "https://www.forgeventures.com"


@patch("app.routes.main_routes.send_investor_request_emails")
def test_investor_submit_thanks_page_renders(mock_send, client):
    resp = client.post("/investor-deck-request", data=_investor_form(), follow_redirects=True)
    assert resp.status_code == 200
    assert b"Request received" in resp.data


@patch("app.routes.main_routes.send_investor_request_emails")
def test_invalid_investor_status_rejected(mock_send, client):
    resp = client.post(
        "/investor-deck-request",
        data=_investor_form(investor_status="gm_player_alpha"),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    mock_send.assert_not_called()


def test_consumer_email_requires_fund_website(client):
    resp = client.post(
        "/investor-deck-request",
        data=_investor_form(email="angel@gmail.com", fund_website=""),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"fund website" in resp.data.lower() or b"Personal email" in resp.data


def test_confidentiality_required_for_investors(client):
    resp = client.post(
        "/investor-deck-request",
        data=_investor_form(confidentiality_ack=""),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"confidentiality" in resp.data.lower()


def test_landing_has_deck_buttons(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Public Deck" in resp.data
    assert b"Request Investor Deck" in resp.data
    assert b"Creators" in resp.data
