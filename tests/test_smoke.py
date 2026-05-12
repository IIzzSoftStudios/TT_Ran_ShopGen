"""Smoke tests for CI (Cloud Build ``docker run … pytest``)."""

from __future__ import annotations

import os

import yaml


def test_healthz_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}


def test_phase_entitlements_loadable():
    config_path = "config/phase_entitlements.yaml"
    assert os.path.exists(config_path), f"{config_path} missing from build context"
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data and "phases" in data and "default" in data["phases"]
