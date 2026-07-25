"""Register form retains non-secret fields after validation errors."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app import app as flask_app
from app.extensions import db
from app.models import RegistrationKey
from app.services.key_generator import generate_secure_code


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def test_register_password_error_keeps_email_and_username(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_REGISTRATION_KEY", "true")
    with flask_app.app_context():
        key_code = generate_secure_code("ALPHA")
        db.session.add(
            RegistrationKey(
                key_code=key_code,
                email="keeper@example.com",
                is_used=False,
                is_admin_test_key=False,
                key_phase="alpha",
            )
        )
        db.session.commit()

        resp = client.post(
            f"/auth/register?vault_key={key_code}&email=keeper@example.com",
            data={
                "registration_key": key_code,
                "username": "vault-user",
                "email": "keeper@example.com",
                "password": "short",
                "confirm_password": "short",
            },
            follow_redirects=False,
        )

        assert resp.status_code in (302, 303)
        location = resp.location or ""
        query = parse_qs(urlparse(location).query)
        assert query.get("email") == ["keeper@example.com"]
        assert query.get("username") == ["vault-user"]
        assert query.get("vault_key") == [key_code]

        follow = client.get(location, follow_redirects=True)
        assert follow.status_code == 200
        html = follow.data.decode("utf-8")
        assert 'value="keeper@example.com"' in html
        assert 'value="vault-user"' in html
        assert "Password must be at least 8 characters long." in html


def test_register_email_mismatch_keeps_typed_email(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_REGISTRATION_KEY", "true")
    with flask_app.app_context():
        key_code = generate_secure_code("ALPHA")
        db.session.add(
            RegistrationKey(
                key_code=key_code,
                email="access@example.com",
                is_used=False,
                is_admin_test_key=False,
                key_phase="alpha",
            )
        )
        db.session.commit()

        resp = client.post(
            f"/auth/register?vault_key={key_code}",
            data={
                "registration_key": key_code,
                "username": "mismatch-user",
                "email": "wrong@example.com",
                "password": "ValidPass1!",
                "confirm_password": "ValidPass1!",
            },
            follow_redirects=False,
        )

        assert resp.status_code in (302, 303)
        location = resp.location or ""
        query = parse_qs(urlparse(location).query)
        assert query.get("email") == ["wrong@example.com"]
        assert query.get("username") == ["mismatch-user"]

        follow = client.get(location, follow_redirects=True)
        html = follow.data.decode("utf-8")
        assert 'value="wrong@example.com"' in html
        assert "Registration key email mismatch" in html
