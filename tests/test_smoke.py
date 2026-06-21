"""Smoke tests for CI (Cloud Build ``docker run … pytest``)."""

from __future__ import annotations

import os

import yaml


def test_healthz_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}


def test_changelog_redirects_to_docs(client):
    response = client.get("/changelog", follow_redirects=False)
    assert response.status_code in (301, 302)
    assert "changelog" in (response.location or "")


def test_ready_route_exists(client):
    """Smoke: /ready returns structured JSON (may be 503 without Redis in CI)."""
    response = client.get("/ready")
    assert response.status_code in (200, 503)
    data = response.get_json()
    assert data is not None
    assert "ok" in data
    assert "redis" in data
    assert "db" in data


def test_phase_entitlements_loadable():
    config_path = "config/phase_entitlements.yaml"
    assert os.path.exists(config_path), f"{config_path} missing from build context"
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data and "phases" in data and "default" in data["phases"]


def test_smoke_base_routes_structural(client):
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/access-request").status_code == 200


def test_smoke_register_redirect_behavior(client):
    response = client.get("/register", follow_redirects=False)
    assert response.status_code in (301, 302)
    assert "register" in (response.location or "").lower()
