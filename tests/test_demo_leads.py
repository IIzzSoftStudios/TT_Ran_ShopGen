"""Demo lead capture + last-step funnel."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import DemoLead
from app.services.demo_leads import touch_last_step, upsert_demo_lead
from app.services.phase_config import PhaseEntitlements, resolve_phase_entitlements_path


@pytest.fixture
def client():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        flask_app.extensions["phase_config"] = PhaseEntitlements(
            resolve_phase_entitlements_path()
        )
        db.create_all()
        yield flask_app.test_client()
        db.session.rollback()
        db.drop_all()


def test_demo_get_shows_lead_form(client):
    resp = client.get("/demo")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Name" in body
    assert "Email" in body
    assert "optional" in body.lower()
    assert "Start Demo" in body


def test_demo_lead_optional_and_last_step(client):
    resp = client.post(
        "/demo/lead",
        data={"contact_name": "Ada", "email": "ada@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    with flask_app.app_context():
        lead = DemoLead.query.filter_by(email="ada@example.com").one()
        assert lead.contact_name == "Ada"
        run_id = lead.demo_run_id
        touch_last_step(demo_run_id=run_id, step_key="welcome")
        db.session.commit()
        lead = DemoLead.query.filter_by(demo_run_id=run_id).one()
        assert lead.last_step_key == "welcome"
        assert lead.last_step_at is not None


def test_demo_lead_allows_blank_name_and_email(client):
    resp = client.post(
        "/demo/lead",
        data={"contact_name": "", "email": ""},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)

    with flask_app.app_context():
        lead = DemoLead.query.one()
        assert lead.contact_name == ""
        assert lead.email == ""
        assert lead.demo_run_id


def test_demo_lead_rejects_bad_email(client):
    resp = client.post(
        "/demo/lead",
        data={"contact_name": "Ada", "email": "not-an-email"},
    )
    assert resp.status_code == 400
    assert b"valid email" in resp.get_data().lower()