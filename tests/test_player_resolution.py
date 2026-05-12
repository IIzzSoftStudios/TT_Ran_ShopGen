"""Regression tests for ``get_active_player`` honoring ``session['player_id'].``

Covers the multi-character-per-campaign case introduced when ``Player`` was
re-keyed onto ``Campaign``. The key invariant: when a user has two non-NPC
``Player`` rows in the same campaign, ``get_active_player`` MUST NOT pick one
arbitrarily. It returns the pinned character when ``session['player_id']`` is
set and validated, otherwise None (forcing the chooser flow).
"""

from __future__ import annotations

import pytest
from flask import Flask

from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, GMProfile, Player, User
from app.services.player_resolution import get_active_player


@pytest.fixture()
def player_app():
    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SECRET_KEY"] = "test"
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


def _make_user(username: str, role: str = "Player") -> User:
    u = User(username=username, password="x", role=role)
    db.session.add(u)
    db.session.commit()
    return u


def _make_campaign(name: str = "Camp") -> Campaign:
    gm_user = _make_user(f"gm-{name}", role="GM")
    gm = GMProfile(user_id=gm_user.id)
    db.session.add(gm)
    db.session.flush()
    c = Campaign(
        gm_profile_id=gm.id,
        name=name,
        system_type="generic",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(c)
    db.session.commit()
    return c


def _make_character(user: User, campaign: Campaign) -> Player:
    p = Player(user_id=user.id, campaign_id=campaign.id, currency=0, is_npc=False)
    db.session.add(p)
    db.session.commit()
    return p


def test_single_character_in_campaign_resolves_without_pin(player_app):
    with player_app.test_request_context():
        from flask import session

        user = _make_user("solo-player")
        camp = _make_campaign("Single")
        ch = _make_character(user, camp)
        session["campaign_id"] = camp.id

        active = get_active_player(user)
        assert active is not None
        assert active.id == ch.id


def test_two_characters_no_pin_returns_none(player_app):
    """The bug: previously this returned an arbitrary character."""
    with player_app.test_request_context():
        from flask import session

        user = _make_user("multi-player")
        camp = _make_campaign("Twin")
        _make_character(user, camp)
        _make_character(user, camp)
        session["campaign_id"] = camp.id

        active = get_active_player(user)
        assert active is None


def test_two_characters_with_pin_returns_pinned(player_app):
    with player_app.test_request_context():
        from flask import session

        user = _make_user("multi-player-2")
        camp = _make_campaign("Twin2")
        a = _make_character(user, camp)
        b = _make_character(user, camp)
        session["campaign_id"] = camp.id
        session["player_id"] = b.id

        active = get_active_player(user)
        assert active is not None
        assert active.id == b.id

        session["player_id"] = a.id
        active = get_active_player(user)
        assert active is not None
        assert active.id == a.id


def test_pinned_player_belonging_to_other_user_is_rejected(player_app):
    """IDOR guard: another user's player_id in session must be ignored."""
    with player_app.test_request_context():
        from flask import session

        legit = _make_user("legit")
        attacker = _make_user("attacker")
        camp = _make_campaign("IDOR")
        legit_char = _make_character(legit, camp)
        attacker_char = _make_character(attacker, camp)

        session["campaign_id"] = camp.id
        session["player_id"] = legit_char.id  # attacker tries to pin legit's char

        active = get_active_player(attacker)
        # Must NOT return the legit user's character. With a single own char in
        # the campaign and the pin rejected, fallback returns the attacker's
        # own character.
        assert active is not None
        assert active.id == attacker_char.id
        assert "player_id" not in session


def test_pin_in_different_campaign_is_rejected(player_app):
    """A pin from a different campaign must not leak across campaigns."""
    with player_app.test_request_context():
        from flask import session

        user = _make_user("cross-camp")
        camp_a = _make_campaign("A")
        camp_b = _make_campaign("B")
        _make_character(user, camp_a)
        char_b = _make_character(user, camp_b)

        session["campaign_id"] = camp_a.id
        session["player_id"] = char_b.id  # belongs to camp_b, not camp_a

        active = get_active_player(user)
        # Pin rejected; len(rows in camp_a) == 1 → returns the camp_a char.
        assert active is not None
        assert active.campaign_id == camp_a.id
        assert "player_id" not in session


def test_stale_pin_is_cleared(player_app):
    """A pin pointing at a deleted character must clear itself."""
    with player_app.test_request_context():
        from flask import session

        user = _make_user("stale")
        camp = _make_campaign("Stale")
        char = _make_character(user, camp)
        session["campaign_id"] = camp.id
        session["player_id"] = char.id

        db.session.delete(char)
        db.session.commit()

        active = get_active_player(user)
        assert active is None
        assert "player_id" not in session
