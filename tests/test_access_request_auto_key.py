from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
from app.models import AccessRequest, RegistrationKey


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _access_request_payload(**overrides):
    payload = {
        "contact_name": "Auto User",
        "email": "auto@example.com",
        "user_role": "GM",
        "player_count": "3",
        "total_expected_users": "4",
        "is_homebrew": "no",
        "primary_ruleset": "Pathfinder",
        "discovery_source": "friend",
        "notes": "Testing auto access",
    }
    payload.update(overrides)
    return payload


def test_access_request_records_info_and_auto_issues_registration_key(client):
    resp = client.post(
        "/access-request",
        data=_access_request_payload(),
        follow_redirects=False,
    )

    assert resp.status_code in (302, 303)
    assert "/register?vault_key=" in (resp.location or "")
    assert "email=auto@example.com" in (resp.location or "")

    access_request = AccessRequest.query.one()
    reg_key = RegistrationKey.query.one()

    assert access_request.status == "approved"
    assert access_request.email == "auto@example.com"
    assert access_request.contact_name == "Auto User"
    assert access_request.user_role == "GM"
    assert access_request.player_count == 3
    assert access_request.total_expected_users == 4
    assert access_request.discovery_source == "friend"
    assert access_request.notes == "Testing auto access"
    assert access_request.processed_at is not None
    assert access_request.vault_key == reg_key.key_code
    assert access_request.vault_key_used is False

    assert reg_key.email == access_request.email
    assert reg_key.key_phase == "default"
    assert reg_key.is_used is False
    assert reg_key.is_admin_test_key is False
    assert reg_key.key_code in (resp.location or "")

    register_resp = client.get(resp.location, follow_redirects=True)
    assert register_resp.status_code == 200
    assert b'value="auto@example.com"' in register_resp.data
    assert reg_key.key_code.encode("utf-8") in register_resp.data


def test_player_access_request_auto_key_does_not_require_player_count(client):
    resp = client.post(
        "/access-request",
        data=_access_request_payload(
            user_role="Player",
            player_count="0",
            total_expected_users="1",
        ),
        follow_redirects=False,
    )

    assert resp.status_code in (302, 303)
    access_request = AccessRequest.query.one()
    reg_key = RegistrationKey.query.one()
    assert access_request.player_count == 0
    assert access_request.vault_key == reg_key.key_code
