"""Guardrails that stop sandbox/test Stripe credentials from serving production billing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import StripeWebhookEvent
from app.services.phase_config import PhaseEntitlements, resolve_phase_entitlements_path
from app.services.stripe_client import (
    billing_enabled,
    billing_mode_mismatch,
    stripe_mode,
)
from app.services.stripe_webhooks import process_stripe_event


@pytest.fixture
def app_ctx(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_TIER1_MONTHLY", "price_tier1_m")
    monkeypatch.setenv("STRIPE_PRICE_TIER1_YEARLY", "price_tier1_y")
    monkeypatch.setenv("STRIPE_PRICE_ADVENTURER_MONTHLY", "price_adv_m")
    monkeypatch.setenv("STRIPE_PRICE_ADVENTURER_YEARLY", "price_adv_y")
    monkeypatch.setenv("STRIPE_PRICE_PRO_MONTHLY", "price_pro_m")
    monkeypatch.setenv("STRIPE_PRICE_PRO_YEARLY", "price_pro_y")
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.config["TESTING"] = True
    with flask_app.app_context():
        flask_app.extensions["phase_config"] = PhaseEntitlements(
            resolve_phase_entitlements_path()
        )
        db.create_all()
        yield flask_app
        db.session.rollback()
        db.drop_all()


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def _event(event_id: str, *, livemode=None, event_type="invoice.payment_failed"):
    event = {"id": event_id, "type": event_type, "data": {"object": {}}}
    if livemode is not None:
        event["livemode"] = livemode
    return event


def test_stripe_mode_is_none_when_key_absent(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert stripe_mode() is None
    assert billing_mode_mismatch() is False
    assert billing_enabled() is False


@pytest.mark.parametrize(
    "flask_env,secret_key,expected_mode,expected_enabled",
    [
        ("production", "sk_live_abc", "live", True),
        ("production", "rk_live_abc", "live", True),
        ("production", "sk_test_abc", "test", False),
        ("development", "sk_test_abc", "test", True),
        ("development", "sk_live_abc", "live", False),
    ],
)
def test_billing_enabled_matrix(
    monkeypatch, flask_env, secret_key, expected_mode, expected_enabled
):
    monkeypatch.setenv("FLASK_ENV", flask_env)
    monkeypatch.setenv("STRIPE_SECRET_KEY", secret_key)
    assert stripe_mode() == expected_mode
    assert billing_enabled() is expected_enabled
    assert billing_mode_mismatch() is (not expected_enabled)


def test_sandbox_account_key_is_mismatch_in_production(monkeypatch):
    """Stripe sandbox accounts issue ``sk_test_`` keys and can never take real money."""
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_not_a_real_key")
    assert billing_mode_mismatch() is True
    assert billing_enabled() is False


def test_checkout_blocked_when_production_holds_test_key(client, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_sandbox")
    with patch("app.routes.billing_routes.create_checkout_session") as create:
        resp = client.post(
            "/create-checkout-session",
            data={"price_id": "price_tier1_m", "email": "buyer@example.com"},
            follow_redirects=False,
        )
    assert resp.status_code in (301, 302)
    create.assert_not_called()


def test_checkout_allowed_when_production_holds_live_key(client, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_real")
    with patch(
        "app.routes.billing_routes.create_checkout_session",
        return_value=type("S", (), {"url": "https://checkout.stripe.com/x"})(),
    ) as create:
        resp = client.post(
            "/create-checkout-session",
            data={"price_id": "price_tier1_m", "email": "buyer@example.com"},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    create.assert_called_once()


def test_subscribe_page_hides_plans_on_mode_mismatch(client, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_sandbox")
    resp = client.get("/subscribe")
    assert resp.status_code == 200
    assert b"Billing is not fully configured yet" in resp.data


def test_subscribe_page_offers_plans_on_live_key(client, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_real")
    resp = client.get("/subscribe")
    assert resp.status_code == 200
    assert b"Billing is not fully configured yet" not in resp.data


def test_webhook_rejects_sandbox_event_in_production(app_ctx, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    assert process_stripe_event(_event("evt_sandbox", livemode=False)) is False
    assert db.session.get(StripeWebhookEvent, "evt_sandbox") is None


def test_webhook_rejects_live_event_outside_production(app_ctx, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "development")
    assert process_stripe_event(_event("evt_live_in_dev", livemode=True)) is False
    assert db.session.get(StripeWebhookEvent, "evt_live_in_dev") is None


def test_webhook_accepts_matching_livemode(app_ctx, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    assert process_stripe_event(_event("evt_prod", livemode=True)) is True
    assert db.session.get(StripeWebhookEvent, "evt_prod") is not None

    monkeypatch.setenv("FLASK_ENV", "development")
    assert process_stripe_event(_event("evt_dev", livemode=False)) is True
    assert db.session.get(StripeWebhookEvent, "evt_dev") is not None


def test_webhook_without_livemode_field_is_unchanged(app_ctx, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    assert process_stripe_event(_event("evt_no_livemode")) is True
    assert db.session.get(StripeWebhookEvent, "evt_no_livemode") is not None


def test_webhook_route_acks_rejected_event_so_stripe_stops_retrying(client, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    with patch(
        "app.routes.billing_routes.construct_webhook_event",
        return_value=_event("evt_route_reject", livemode=False),
    ):
        resp = client.post(
            "/webhook/stripe",
            data=b"{}",
            headers={"Stripe-Signature": "t=1,v1=x"},
        )
    assert resp.status_code == 200
    assert db.session.get(StripeWebhookEvent, "evt_route_reject") is None
