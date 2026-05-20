"""Tests for unified GM + player accounts (capabilities, session_mode, registration)."""

from __future__ import annotations

import pytest

from app import app as flask_app
from tests.session_helpers import seed_client_session
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, GMProfile, Player, User
from app.services.user_capabilities import ensure_gm_profile, has_gm_capability


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _make_user(username: str, role: str = "Both", password: str = "Secret1!") -> User:
    u = User(username=username, password="x", role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u


def _make_gm_campaign(gm_user: User, name: str = "Camp") -> Campaign:
    ensure_gm_profile(gm_user)
    db.session.commit()
    db.session.refresh(gm_user)
    c = Campaign(
        gm_profile_id=gm_user.gm_profile.id,
        name=name,
        system_type="generic",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(c)
    db.session.commit()
    return c


def test_has_gm_capability_requires_profile():
    with flask_app.app_context():
        u = _make_user("no-gm", role="Player")
        assert has_gm_capability(u) is False
        ensure_gm_profile(u)
        db.session.commit()
        db.session.refresh(u)
        assert has_gm_capability(u) is True


def test_unauthorized_gm_mode_returns_403(client):
    with flask_app.app_context():
        owner = _make_user("gm-owner2", role="GM")
        intruder = _make_user("intruder2", role="Player")
        camp = _make_gm_campaign(owner)
        seed_client_session(client, intruder)
        resp = client.get(f"/campaigns/load/{camp.id}?as=gm")
        assert resp.status_code == 403


def test_unauthorized_gm_mode_does_not_set_session(client):
    with flask_app.app_context():
        owner = _make_user("gm-owner", role="GM")
        intruder = _make_user("intruder", role="Player")
        camp = _make_gm_campaign(owner)
        seed_client_session(client, intruder)
        with client.session_transaction() as sess:
            sess.clear()
        client.get(f"/campaigns/load/{camp.id}?as=gm")
        with client.session_transaction() as sess:
            assert sess.get("session_mode") is None
            assert sess.get("campaign_id") is None


def test_player_mode_requires_character_403(client):
    with flask_app.app_context():
        owner = _make_user("gm-owner3", role="GM")
        intruder = _make_user("intruder3", role="Player")
        camp = _make_gm_campaign(owner)
        seed_client_session(client, intruder)
        resp = client.get(f"/campaigns/load/{camp.id}?as=player")
        assert resp.status_code == 403


def test_session_mode_home_routing_gm(client):
    with flask_app.app_context():
        gm = _make_user("gm-home", role="GM")
        camp = _make_gm_campaign(gm)
        seed_client_session(
            client, gm, campaign_id=camp.id, session_mode="gm"
        )
        resp = client.get("/home", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "gm" in (resp.location or "").lower()


def test_mode_guard_gm_on_player_route(client):
    with flask_app.app_context():
        u = _make_user("both-guard", role="Both")
        p = Player(user_id=u.id, campaign_id=None, currency=0, is_npc=False)
        db.session.add(p)
        db.session.commit()
        seed_client_session(client, u, session_mode="gm")
        resp = client.get("/player/home", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "campaigns" in (resp.location or "")


def test_migration_idempotency():
    with flask_app.app_context():
        u = _make_user("legacy-gm", role="GM")
        ensure_gm_profile(u)
        db.session.commit()
        pid = u.gm_profile.id

        targets = User.query.filter(User.role.in_(["GM", "Player"])).all()
        for user in targets:
            user.role = "Both"
            ensure_gm_profile(user)
        db.session.commit()

        db.session.refresh(u)
        assert u.role == "Both"
        assert u.gm_profile.id == pid

        for user in User.query.filter(User.role == "Both").all():
            ensure_gm_profile(user)
        db.session.commit()
        assert GMProfile.query.filter_by(user_id=u.id).count() == 1


def test_registration_password_mismatch(client):
    with flask_app.app_context():
        resp = client.post(
            "/auth/register",
            data={
                "username": "newuser1",
                "password": "ValidPass1!",
                "confirm_password": "Different1!",
                "registration_key": "",
            },
            follow_redirects=True,
        )
        assert User.query.filter_by(username="newuser1").first() is None
        assert resp.status_code == 200


def test_create_character_get_renders_form(client):
    """Template name must match on-disk casing (Linux/GCP is case-sensitive)."""
    from pathlib import Path

    template_path = (
        Path(flask_app.root_path) / "templates" / "Player_Create_Character.html"
    )
    assert template_path.is_file(), f"missing template: {template_path}"

    with flask_app.app_context():
        user = _make_user("char-creator", role="Both")
        seed_client_session(client, user)
        resp = client.get("/player/character/create")
        assert resp.status_code == 200, resp.data[:500]
        body = resp.data
        assert b'name="system_type"' in body
        assert b'id="character_name"' in body
        assert b"Create character" in body or b"Create Character" in body


def test_registration_without_campaign_code_does_not_create_character(client, monkeypatch):
    monkeypatch.delenv("REQUIRE_REGISTRATION_KEY", raising=False)
    with flask_app.app_context():
        resp = client.post(
            "/auth/register",
            data={
                "username": "newuser2",
                "email": "newuser2@example.com",
                "password": "ValidPass1!",
                "confirm_password": "ValidPass1!",
                "registration_key": "",
                "campaign_code": "",
            },
            follow_redirects=False,
        )

        user = User.query.filter_by(username="newuser2").first()
        assert resp.status_code in (302, 303)
        assert user is not None
        assert GMProfile.query.filter_by(user_id=user.id).count() == 1
        assert Player.query.filter_by(user_id=user.id, is_npc=False).count() == 0


def test_user_capabilities_can_redeem():
    with flask_app.app_context():
        from app.services.user_capabilities import can_redeem_campaign_code

        vk = _make_user("vault", role="vault_keeper")
        both = _make_user("both", role="Both")
        assert can_redeem_campaign_code(vk) is False
        assert can_redeem_campaign_code(both) is True
