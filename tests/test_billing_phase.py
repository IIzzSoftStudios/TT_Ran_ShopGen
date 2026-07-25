from unittest.mock import MagicMock, patch

from app.services.billing_rules import get_gm_limits, can_add_player_profile


class _Key:
    def __init__(self, phase):
        self.key_phase = phase


class _User:
    def __init__(self, key=None):
        self.registration_key_used = key


def test_get_gm_limits_default_without_key(app_with_phases):
    with app_with_phases.app_context():
        c, s, lbl = get_gm_limits(_User(None))
        assert c == 1
        assert s == 2
        assert lbl == "Def"


def test_get_gm_limits_respects_key_phase(app_with_phases):
    with app_with_phases.app_context():
        c, s, lbl = get_gm_limits(_User(_Key("alpha")))
        assert c == 10
        assert s == 30
        assert lbl == "Alpha"


def test_get_gm_limits_tech_demo_allows_99_campaigns(app_with_phases):
    with app_with_phases.app_context():
        c, s, lbl = get_gm_limits(_User(_Key("tech_demo")))
        assert c == 99
        assert s == 50
        assert lbl == "Tech Demo"


def test_get_gm_limits_unknown_db_slug_falls_back(app_with_phases):
    with app_with_phases.app_context():
        c, s, lbl = get_gm_limits(_User(_Key("orphan_phase")))
        assert c == 1
        assert lbl == "Def"


def test_can_add_player_profile_non_player_always_ok(app_with_phases):
    with app_with_phases.app_context():
        ok, msg = can_add_player_profile(None)
        assert ok is True
        assert msg == ""
        ok, msg = can_add_player_profile(MagicMock(role="GM"))
        assert ok is True


def test_can_add_player_profile_respects_campaign_limit(app_with_phases):
    u = _User(_Key("default"))
    u.id = 5
    u.role = "Player"
    with app_with_phases.app_context():
        with patch("app.services.billing_rules.db.session.query") as qm:
            qm.return_value.filter.return_value.count.return_value = 1
            ok, msg = can_add_player_profile(u)
            assert ok is False
            assert "profile limit" in msg.lower() or "limit (1)" in msg or "player profile" in msg.lower()
