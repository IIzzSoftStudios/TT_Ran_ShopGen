"""Pytest fixtures; env must be set before importing ``app`` (import-time ``create_app()``)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("SECRET_KEY", "ci-testing-secret-key")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
os.environ.setdefault("SESSION_REDIS_FALLBACK", "true")
# Pytest/CI has no Redis; filesystem sessions avoid split-transaction key loss.
os.environ.setdefault("TRSG_TEST_FILESYSTEM_SESSION", "1")

from flask import Flask

from app import app as flask_app
from app.services.phase_config import PhaseEntitlements

_PHASES_TEST_YAML = """\
phases:
  default:
    label: "Def"
    prefix: "DEF"
    campaign_limit: 1
    seat_limit: 2
  alpha:
    label: "Alpha"
    prefix: "AL"
    campaign_limit: 3
    seat_limit: 6
  test:
    label: "Test"
    prefix: "T"
    campaign_limit: 1
    seat_limit: 1
"""


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def phase_yaml_path(tmp_path):
    """Minimal phase YAML matching ``test_phase_config`` / ``test_billing_phase`` expectations."""
    path = tmp_path / "phase_entitlements_test.yaml"
    path.write_text(_PHASES_TEST_YAML, encoding="utf-8")
    return str(path)


@pytest.fixture
def app_with_phases(phase_yaml_path):
    """Lightweight Flask app with only ``phase_config`` (no DB) for billing unit tests."""
    app = Flask(__name__)
    app.extensions["phase_config"] = PhaseEntitlements(phase_yaml_path)
    return app
