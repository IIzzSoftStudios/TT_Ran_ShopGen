"""Stripe entitlements, webhook idempotency, and billing route guards."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from stripe import SignatureVerificationError

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import BillingSubscription, RegistrationKey, StripeWebhookEvent, User
from app.services.billing_rules import (
    can_add_player_to_campaign,
    get_gm_limits,
    requires_resubscribe_gate,
    resolve_phase_slug,
)
from app.services.entitlements import is_allowed_price, plan_slug_for_price, subscription_plans_for_display
from app.services.phase_config import PhaseEntitlements, resolve_phase_entitlements_path
from app.services.stripe_webhooks import process_stripe_event
from app.services.user_capabilities import ensure_gm_profile
from app.models import Campaign, Player


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
        pc = PhaseEntitlements(resolve_phase_entitlements_path())
        flask_app.extensions["phase_config"] = pc
        db.create_all()
        yield flask_app
        db.session.rollback()
        db.drop_all()


@pytest.fixture
def client(app_ctx):
    return app_ctx.test_client()


def test_subscribe_catalog_lists_three_tiers(app_ctx):
    plans = subscription_plans_for_display()
    slugs = {p["plan_slug"] for p in plans}
    assert slugs == {"tier1", "adventurer", "pro"}
    assert len(plans) == 6
    adv = next(p for p in plans if p["plan_slug"] == "adventurer" and p["interval_key"] == "monthly")
    assert adv["campaigns_label"] == "3 campaigns"
    assert "7 player seats" in adv["seats_label"]


def test_price_allowlist_rejects_unknown(app_ctx):
    assert is_allowed_price("price_tier1_m")
    assert plan_slug_for_price("price_pro_y") == "pro"
    assert plan_slug_for_price("price_adv_m") == "adventurer"
    assert not is_allowed_price("price_evil")
    assert plan_slug_for_price("price_evil") is None


def test_billing_rules_adventurer(app_ctx):
    user = User(username="adv", role="Both", email="adv@ex.com")
    user.set_password("Password1!")
    db.session.add(user)
    db.session.flush()
    db.session.add(
        BillingSubscription(
            user_id=user.id,
            stripe_subscription_id="sub_adv",
            stripe_customer_id="cus_adv",
            stripe_price_id="price_adv_m",
            plan_slug="adventurer",
            status="active",
        )
    )
    db.session.commit()
    cap, seats, label = get_gm_limits(user)
    assert cap == 3 and seats == 7 and "Adventurer" in label


def test_billing_rules_tier1_and_pro_unlimited(app_ctx):
    u1 = User(username="t1", role="Both", email="t1@ex.com")
    u1.set_password("Password1!")
    u2 = User(username="pro", role="Both", email="pro@ex.com")
    u2.set_password("Password1!")
    db.session.add_all([u1, u2])
    db.session.flush()
    db.session.add(
        BillingSubscription(
            user_id=u1.id,
            stripe_subscription_id="sub_t1",
            stripe_customer_id="cus_t1",
            stripe_price_id="price_tier1_m",
            plan_slug="tier1",
            status="active",
        )
    )
    db.session.add(
        BillingSubscription(
            user_id=u2.id,
            stripe_subscription_id="sub_pro",
            stripe_customer_id="cus_pro",
            stripe_price_id="price_pro_m",
            plan_slug="pro",
            status="active",
        )
    )
    db.session.commit()

    cap1, seats1, label1 = get_gm_limits(u1)
    assert cap1 == 1 and seats1 == 5 and "Casual" in label1
    cap2, seats2, label2 = get_gm_limits(u2)
    assert cap2 == 5 and seats2 is None and "Pro" in label2

    ensure_gm_profile(u2)
    db.session.commit()
    campaign = Campaign(
        name="C",
        gm_profile_id=u2.gm_profile.id,
        is_active=True,
    )
    db.session.add(campaign)
    db.session.commit()
    ok, _msg = can_add_player_to_campaign(campaign)
    assert ok is True


def test_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    with patch(
        "app.routes.billing_routes.construct_webhook_event",
        side_effect=SignatureVerificationError("bad", "sig"),
    ):
        resp = client.post(
            "/webhook/stripe",
            data=b"{}",
            headers={"Stripe-Signature": "t=1,v1=x"},
        )
    assert resp.status_code == 400


def test_webhook_idempotent_duplicate(app_ctx, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    event = {
        "id": "evt_dup_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_x",
                "customer": "cus_x",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_tier1_m"}}]},
            }
        },
    }
    assert process_stripe_event(event) is True
    assert StripeWebhookEvent.query.filter_by(id="evt_dup_1").first() is not None
    assert process_stripe_event(event) is False
    assert BillingSubscription.query.filter_by(stripe_subscription_id="sub_x").count() == 1


def test_create_checkout_rejects_unknown_price(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_PRICE_TIER1_MONTHLY", "price_tier1_m")
    resp = client.post(
        "/create-checkout-session",
        data={"price_id": "price_not_real", "email": "a@b.com"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/subscribe" in (resp.headers.get("Location") or "")


def test_access_request_redirects_to_subscribe(client):
    resp = client.get("/access-request", follow_redirects=False)
    assert resp.status_code == 302
    assert "/subscribe" in (resp.headers.get("Location") or "")


def test_requires_resubscribe_gate_canceled_only(app_ctx):
    free = User(username="free_u", role="Both", email="free@ex.com")
    free.set_password("Password1!")
    paid = User(username="paid_u", role="Both", email="paid@ex.com")
    paid.set_password("Password1!")
    paid.stripe_customer_id = "cus_paid"
    canceled = User(username="cancel_u", role="Both", email="cancel@ex.com")
    canceled.set_password("Password1!")
    canceled.stripe_customer_id = "cus_cancel"
    db.session.add_all([free, paid, canceled])
    db.session.flush()
    db.session.add(
        BillingSubscription(
            user_id=paid.id,
            stripe_subscription_id="sub_paid_active",
            stripe_customer_id="cus_paid",
            stripe_price_id="price_tier1_m",
            plan_slug="tier1",
            status="active",
        )
    )
    db.session.add(
        BillingSubscription(
            user_id=canceled.id,
            stripe_subscription_id="sub_canceled",
            stripe_customer_id="cus_cancel",
            stripe_price_id="price_tier1_m",
            plan_slug="tier1",
            status="canceled",
        )
    )
    db.session.commit()

    assert requires_resubscribe_gate(free) is False
    assert requires_resubscribe_gate(paid) is False
    assert requires_resubscribe_gate(canceled) is True
    assert resolve_phase_slug(canceled) == "default"


def test_lapsed_subscriber_sees_gate_modal(client, app_ctx):
    user = User(username="lapse_ui", role="Both", email="lapse_ui@ex.com")
    user.set_password("Password1!")
    user.stripe_customer_id = "cus_lapse_ui"
    db.session.add(user)
    db.session.flush()
    db.session.add(
        BillingSubscription(
            user_id=user.id,
            stripe_subscription_id="sub_lapse_ui",
            stripe_customer_id="cus_lapse_ui",
            stripe_price_id="price_tier1_m",
            plan_slug="tier1",
            status="canceled",
        )
    )
    db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True

    resp = client.get("/campaigns")
    assert resp.status_code == 200
    assert b"subscription-lapsed-modal" in resp.data
    assert b"You&#39;re no longer subscribed" in resp.data or b"You're no longer subscribed" in resp.data
    assert b"Subscribe again" in resp.data


def test_lapsed_subscriber_mutation_blocked(client, app_ctx):
    user = User(username="lapse_api", role="Both", email="lapse_api@ex.com")
    user.set_password("Password1!")
    user.stripe_customer_id = "cus_lapse_api"
    db.session.add(user)
    db.session.flush()
    db.session.add(
        BillingSubscription(
            user_id=user.id,
            stripe_subscription_id="sub_lapse_api",
            stripe_customer_id="cus_lapse_api",
            stripe_price_id="price_tier1_m",
            plan_slug="tier1",
            status="canceled",
        )
    )
    db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True

    resp = client.post(
        "/api/simulation/speed",
        json={"speed": "paused"},
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["code"] == "subscription_lapsed"
