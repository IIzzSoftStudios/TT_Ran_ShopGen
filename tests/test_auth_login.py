"""Authentication route regressions."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import User


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def test_login_with_invalid_stored_password_hash_returns_invalid_login(client):
    with flask_app.app_context():
        db.session.add(User(username="bad-hash", password="not-a-bcrypt-hash", role="GM"))
        db.session.commit()

    response = client.post(
        "/auth/login",
        data={"username": "bad-hash", "password": "correct-info"},
    )

    assert response.status_code == 200
    assert b"Invalid username or password" in response.data
