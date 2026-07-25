"""Public /access-request now redirects to paid /subscribe (no free auto-keys)."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def test_access_request_get_redirects_to_subscribe(client):
    resp = client.get("/access-request", follow_redirects=False)
    assert resp.status_code == 302
    assert "/subscribe" in (resp.location or "")


def test_access_request_post_redirects_to_subscribe(client):
    resp = client.post(
        "/access-request",
        data={
            "contact_name": "Auto User",
            "email": "auto@example.com",
            "user_role": "GM",
            "player_count": "3",
            "primary_ruleset": "Pathfinder",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/subscribe" in (resp.location or "")
