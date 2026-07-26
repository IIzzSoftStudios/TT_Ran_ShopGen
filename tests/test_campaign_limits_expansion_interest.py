from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import app as flask_app
from app.extensions import db
from app.models import Campaign, ExpansionInterest, GMProfile, Player, User
from app.services.billing_rules import can_create_campaign
from app.services.join_codes import SeatCapError, redeem_campaign_code
from app.services.user_capabilities import ensure_gm_profile
from tests.session_helpers import seed_client_session


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _make_user(username: str, role: str = "Both") -> User:
    user = User(username=username, password="x", role=role)
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    return user


def _make_gm(username: str = "gm") -> User:
    user = _make_user(username, role="Both")
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    return user


def _make_campaign(gm_profile: GMProfile, name: str, *, is_active: bool = True) -> Campaign:
    campaign = Campaign(
        gm_profile_id=gm_profile.id,
        name=name,
        system_type="generic",
        is_active=is_active,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def test_can_create_campaign_counts_only_active_campaigns():
    gm_user = _make_gm("inactive-ok")
    _make_campaign(gm_user.gm_profile, "Archived", is_active=False)

    ok, msg = can_create_campaign(gm_user.gm_profile)

    assert ok is True
    assert msg == ""


def test_skip_generation_blocks_direct_post_when_active_campaign_cap_reached(client):
    gm_user = _make_gm("capped-post")
    _make_campaign(gm_user.gm_profile, "Live", is_active=True)
    seed_client_session(client, gm_user)

    resp = client.post(
        "/gm/generate_world/skip",
        data={"campaign_name": "Second", "system_type": "generic"},
    )

    assert resp.status_code == 402
    assert Campaign.query.filter_by(gm_profile_id=gm_user.gm_profile.id).count() == 1
    assert b"Ready to expand your realm" in resp.data


def test_campaign_selection_renders_expansion_modal_trigger_when_capped(client):
    gm_user = _make_gm("capped-ui")
    _make_campaign(gm_user.gm_profile, "Live", is_active=True)
    seed_client_session(client, gm_user)

    resp = client.get("/campaigns")

    assert resp.status_code == 200
    assert b"data-expansion-interest-trigger" in resp.data
    assert b"Go to Billing" in resp.data
    assert b"No, stay on current tier" in resp.data


def test_gm_campaign_list_renders_expansion_modal_trigger_when_capped(client):
    gm_user = _make_gm("capped-gm-list")
    _make_campaign(gm_user.gm_profile, "Live", is_active=True)
    seed_client_session(client, gm_user)

    resp = client.get("/gm/campaigns/", follow_redirects=True)

    assert resp.status_code == 200
    assert b"data-expansion-interest-source=\"campaign_selection_create\"" in resp.data


def test_expansion_interest_endpoint_persists_server_identity(client):
    gm_user = _make_gm("interest")
    seed_client_session(client, gm_user)

    resp = client.post(
        "/gm/expansion-interest",
        json={
            "intent": "pro_interest",
            "source": "pytest",
            "user_id": 999999,
        },
    )

    assert resp.status_code == 201
    assert resp.get_json()["message"] == (
        "Thanks for your interest! We've added you to our priority waitlist."
    )
    row = ExpansionInterest.query.one()
    assert row.user_id == gm_user.id
    assert row.gm_profile_id == gm_user.gm_profile.id
    assert row.intent == "pro_interest"
    assert row.source == "pytest"
    assert row.created_at is not None


def test_expansion_interest_endpoint_updates_existing_selection_without_duplicates(client):
    gm_user = _make_gm("interest-update")
    seed_client_session(client, gm_user)

    first = client.post(
        "/gm/expansion-interest",
        json={"intent": "campaign_limit_upgrade", "source": "first"},
    )
    duplicate = client.post(
        "/gm/expansion-interest",
        json={"intent": "campaign_limit_upgrade", "source": "second"},
    )
    changed = client.post(
        "/gm/expansion-interest",
        json={"intent": "not_interested", "source": "declined"},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.get_json()["already_selected"] is True
    assert duplicate.get_json()["selection"] == "yes"
    assert changed.status_code == 200
    assert changed.get_json()["selection"] == "no"
    assert ExpansionInterest.query.count() == 1
    row = ExpansionInterest.query.one()
    assert row.user_id == gm_user.id
    assert row.intent == "not_interested"
    assert row.source == "declined"


def test_expansion_interest_schema_compat_requires_gm_profile_table(monkeypatch):
    from app.services import schema_compat

    class _NoDdlSession:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("DDL should not run when gm_profile is missing")

        def commit(self):
            raise AssertionError("commit should not run when gm_profile is missing")

    fake_db = SimpleNamespace(
        engine=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        session=_NoDdlSession(),
    )

    monkeypatch.setattr(schema_compat, "db", fake_db)
    monkeypatch.setattr(
        schema_compat,
        "_regclass_exists",
        lambda table_name: table_name == "user",
    )

    assert schema_compat.ensure_expansion_interest_table() is False


def test_campaign_join_rejects_when_player_seat_cap_reached():
    gm_user = _make_gm("seat-cap")
    campaign = _make_campaign(gm_user.gm_profile, "Full", is_active=True)
    db.session.add_all(
        [
            Player(user_id=_make_user("p1", role="Player").id, campaign_id=campaign.id, is_npc=False),
            Player(user_id=_make_user("p2", role="Player").id, campaign_id=campaign.id, is_npc=False),
            Player(user_id=_make_user("p3", role="Player").id, campaign_id=campaign.id, is_npc=False),
        ]
    )
    joining_user = _make_user("joiner", role="Player")
    db.session.add(Player(user_id=joining_user.id, campaign_id=None, is_npc=False))
    db.session.commit()

    with pytest.raises(SeatCapError):
        redeem_campaign_code(joining_user, campaign.join_code, _commit=True)
