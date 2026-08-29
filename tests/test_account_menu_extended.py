"""Account menu, avatar, and user submissions."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from flask_login import login_user
from PIL import Image

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, GMProfile, Player, User, UserSubmission
from app.services.user_capabilities import ensure_gm_profile


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _login_as(user: User):
    with flask_app.test_request_context():
        login_user(user)


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


def _tiny_png() -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(buf, format="PNG")
    buf.seek(0)
    return buf


def _oversized_upload() -> io.BytesIO:
    buf = io.BytesIO(b"x" * (512 * 1024 + 1))
    buf.seek(0)
    return buf


def test_account_menu_visible_on_campaigns_not_on_login(client):
    with flask_app.app_context():
        user = _make_user("menu-user", role="Player")
        _login_as(user)
        ok = client.get("/campaigns")
        assert ok.status_code == 200
        assert b"accountMenuWrapper" in ok.data
        assert b"tt-account-menu-config" in ok.data

        client.get("/auth/logout")
        login_page = client.get("/auth/login")
        assert login_page.status_code == 200
        assert b"accountMenuWrapper" not in login_page.data


def test_campaign_counts_in_menu_config(client):
    with flask_app.app_context():
        user = _make_user("counts-user", role="Both")
        camp = _make_gm_campaign(user)
        p = Player(user_id=user.id, campaign_id=camp.id, currency=0, is_npc=False)
        db.session.add(p)
        db.session.commit()
        _login_as(user)
        resp = client.get("/campaigns")
        assert resp.status_code == 200
        assert b'"gm_count": 1' in resp.data or b'"gm_count":1' in resp.data
        assert b'"player_count": 1' in resp.data or b'"player_count":1' in resp.data


def test_submission_polymorphic_bug_report(client):
    with flask_app.app_context():
        user = _make_user("submitter", role="Player")
        _login_as(user)
        payload = {
            "kind": "bug_report",
            "category": "UI & display",
            "title": "Broken panel",
            "what_happened": "Panel did not open",
            "severity": "Major",
            "steps_to_reproduce": "Click avatar",
            "expected_behavior": "Popover opens",
            "page_url": "/campaigns",
            "evil_key": "should not persist",
        }
        resp = client.post(
            "/auth/account/submissions",
            json=payload,
            content_type="application/json",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
                )
            },
        )
        assert resp.status_code == 201
        row = UserSubmission.query.filter_by(user_id=user.id).one()
        assert row.kind == "bug_report"
        assert row.body == "Panel did not open"
        assert row.client_browser == "Chrome"
        assert row.client_os == "Android"
        assert row.client_device_type == "mobile"
        assert "evil_key" not in row.extra
        assert row.extra.get("severity") == "Major"


def test_submission_invalid_category_rejected(client):
    with flask_app.app_context():
        user = _make_user("bad-cat", role="Player")
        _login_as(user)
        resp = client.post(
            "/auth/account/submissions",
            json={
                "kind": "bug_report",
                "category": "Not A Real Category",
                "title": "x",
                "what_happened": "y",
                "severity": "Minor",
            },
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert UserSubmission.query.count() == 0


def test_prompted_import_submission_updates_existing_file_type(client):
    with flask_app.app_context():
        user = _make_user("prompted-importer", role="GM")
        _login_as(user)
        payload = {
            "kind": "suggestion",
            "category": "Reports & exports",
            "title": "Monster import request",
            "description": "Please add import support for: CSV",
            "frequency": "Once",
            "beta_test": True,
            "prompted_key": "monster_import",
            "file_type": "CSV",
            "page_url": "/gm/",
        }
        first = client.post(
            "/auth/account/submissions",
            json=payload,
            content_type="application/json",
        )
        assert first.status_code == 201

        payload["description"] = "Please add import support for: JSON"
        payload["file_type"] = "JSON"
        second = client.post(
            "/auth/account/submissions",
            json=payload,
            content_type="application/json",
        )
        assert second.status_code == 200

        row = UserSubmission.query.filter_by(user_id=user.id).one()
        assert row.body == "Please add import support for: JSON"
        assert row.extra["prompted_key"] == "monster_import"
        assert row.extra["file_type"] == "JSON"


def test_avatar_upload_rejects_oversized_file(client):
    with flask_app.app_context():
        user = _make_user("avatar-user", role="Player")
        _login_as(user)
        big = _oversized_upload()
        resp = client.post(
            "/auth/account/avatar",
            data={"avatar": (big, "big.bin")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert b"512" in resp.data or b"max" in resp.data.lower()


def test_avatar_upload_accepts_small_png(client):
    with flask_app.app_context():
        user = _make_user("avatar-ok", role="Player")
        _login_as(user)
        small = _tiny_png()
        resp = client.post(
            "/auth/account/avatar",
            data={"avatar": (small, "tiny.png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True
        db.session.refresh(user)
        assert user.avatar_updated_at is not None


def test_submission_commit_rollback_on_db_error(client):
    with flask_app.app_context():
        user = _make_user("rollback-user", role="Player")
        _login_as(user)
        payload = {
            "kind": "feedback",
            "category": "General / other",
            "trying_to_do": "Testing rollback",
        }
        with patch.object(db.session, "commit", side_effect=RuntimeError("db down")):
            resp = client.post(
                "/auth/account/submissions",
                json=payload,
                content_type="application/json",
            )
        assert resp.status_code == 500
        assert UserSubmission.query.count() == 0


def test_vault_keeper_can_triage_submission(client):
    with flask_app.app_context():
        submitter = _make_user("player-sub", role="Player")
        keeper = _make_user("keeper", role="vault_keeper")
        sub = UserSubmission(
            kind="bug_report",
            user_id=submitter.id,
            username_snapshot=submitter.username,
            submitted_session_mode="hub",
            account_role=submitter.role,
            category="Other",
            title="Triage me",
            body="Body",
            extra={"severity": "Minor"},
            page_url="/",
            status="pending",
        )
        db.session.add(sub)
        db.session.commit()
        sub_id = sub.id

        _login_as(keeper)
        resp = client.post(f"/admin/vault/submissions/{sub_id}/review")
        assert resp.status_code == 200
        assert resp.get_json().get("new_status") == "reviewed"


def test_review_rejects_non_pending_submission(client):
    with flask_app.app_context():
        submitter = _make_user("player-reviewed", role="Player")
        keeper = _make_user("keeper-review", role="vault_keeper")
        sub = UserSubmission(
            kind="bug_report",
            user_id=submitter.id,
            username_snapshot=submitter.username,
            submitted_session_mode="hub",
            account_role=submitter.role,
            category="Other",
            title="Already reviewed",
            body="Body",
            extra={"severity": "Minor"},
            page_url="/",
            status="reviewed",
        )
        db.session.add(sub)
        db.session.commit()
        sub_id = sub.id

        _login_as(keeper)
        resp = client.post(f"/admin/vault/submissions/{sub_id}/review")
        assert resp.status_code == 409
        assert resp.get_json().get("error")
        db.session.refresh(sub)
        assert sub.status == "reviewed"


def test_gm_admin_cannot_triage_submission(client):
    with flask_app.app_context():
        submitter = _make_user("player-sub2", role="Player")
        gm = _make_user("gm-admin", role="GM")
        _make_gm_campaign(gm)
        sub = UserSubmission(
            kind="suggestion",
            user_id=submitter.id,
            username_snapshot=submitter.username,
            submitted_session_mode="hub",
            account_role=submitter.role,
            category="Other",
            title="No triage",
            body="Desc",
            extra={},
            page_url="/",
            status="pending",
        )
        db.session.add(sub)
        db.session.commit()
        sub_id = sub.id

        _login_as(gm)
        resp = client.post(f"/admin/vault/submissions/{sub_id}/review")
        assert resp.status_code == 404
