"""Shared helpers for Flask test client sessions."""

from __future__ import annotations

from flask.testing import FlaskClient

from app.models import User


def seed_client_session(client: FlaskClient, user: User | None = None, **keys) -> None:
    """Set login and session keys on the test client in one transaction.

    Splitting ``login_user`` in ``test_request_context`` from a later
    ``session_transaction`` can drop keys when the session backend falls back
    from Redis to signed cookies (Docker/CI).
    """
    with client.session_transaction() as sess:
        if user is not None:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
        for key, value in keys.items():
            sess[key] = value
