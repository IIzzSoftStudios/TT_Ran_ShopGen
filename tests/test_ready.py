"""Readiness probe tests for /ready."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

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


def test_ready_ok_when_redis_and_db_healthy(client):
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    with patch(
        "app.routes.main_routes.get_redis_client", return_value=mock_redis
    ):
        resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["redis"] == "ok"
    assert data["db"] == "ok"


def test_ready_503_when_redis_fails(client):
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = ConnectionError("redis down")
    with patch(
        "app.routes.main_routes.get_redis_client", return_value=mock_redis
    ):
        resp = client.get("/ready")
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["ok"] is False
    assert data["redis"] == "error"


def test_ready_503_when_db_fails(client):
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    with patch(
        "app.routes.main_routes.get_redis_client", return_value=mock_redis
    ):
        with patch(
            "app.routes.main_routes.db.session.execute",
            side_effect=OperationalError("stmt", {}, Exception("db down")),
        ):
            resp = client.get("/ready")
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["ok"] is False
    assert data["db"] == "error"


def test_ready_503_when_both_redis_and_db_fail(client):
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = ConnectionError("redis down")
    with patch(
        "app.routes.main_routes.get_redis_client", return_value=mock_redis
    ):
        with patch(
            "app.routes.main_routes.db.session.execute",
            side_effect=OperationalError("stmt", {}, Exception("db down")),
        ):
            resp = client.get("/ready")
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["ok"] is False
    assert data["redis"] == "error"
    assert data["db"] == "error"
    err = data.get("error") or ""
    assert "redis: ConnectionError" in err
    assert "db: OperationalError" in err


def test_ready_503_when_ping_returns_falsy(client):
    mock_redis = MagicMock()
    mock_redis.ping.return_value = False
    with patch(
        "app.routes.main_routes.get_redis_client", return_value=mock_redis
    ):
        resp = client.get("/ready")
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["ok"] is False
    assert data["redis"] == "error"
    assert "redis: RuntimeError" in (data.get("error") or "")


def test_healthz_ok_without_touching_redis_or_db(client):
    with patch(
        "app.routes.main_routes.get_redis_client",
        side_effect=AssertionError("Redis should not be touched by /healthz"),
    ):
        with patch(
            "app.routes.main_routes.db.session.execute",
            side_effect=AssertionError("Database should not be touched by /healthz"),
        ):
            resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
