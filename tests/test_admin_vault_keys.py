"""Vault keys dashboard: GM simulation usage tab is vault_keeper-only."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import app
from app.routes.handlers import admin_handler


def _mock_phase_config():
    pc = MagicMock()
    pc.list_phases.side_effect = lambda include_internal=False: (
        ["forge_master", "alpha", "default"]
        if include_internal
        else ["forge_master", "alpha"]
    )
    return pc


def test_handle_admin_keys_skips_gm_simulation_query_for_gm_role():
    with app.app_context():
        app.extensions["phase_config"] = _mock_phase_config()
        reg_chain = MagicMock()
        reg_chain.order_by.return_value.all.return_value = []
        with patch.multiple(
            admin_handler,
            RegistrationKey=MagicMock(),
            AccessRequest=MagicMock(),
            current_user=MagicMock(id=2, role="GM"),
            render_template=MagicMock(return_value="ok"),
            _gm_simulation_usage_serialized_rows=MagicMock(),
            _campaign_code_redemption_rows=MagicMock(return_value=[]),
            _campaign_character_rows=MagicMock(return_value=[]),
            _prompted_feedback_answer_rows=MagicMock(return_value=[]),
            _load_submissions_by_kind=MagicMock(return_value=[]),
        ):
            admin_handler.RegistrationKey.query.filter_by.return_value = reg_chain
            admin_handler.AccessRequest.query.all.return_value = []
            admin_handler.handle_admin_keys()
            admin_handler._gm_simulation_usage_serialized_rows.assert_not_called()
            kw = admin_handler.render_template.call_args[1]
            assert kw["gm_simulation_rows"] == []
            assert kw["show_gm_usage_tab"] is False
            assert kw["campaign_character_rows"] == []
            assert kw["prompted_feedback_rows"] == []
            assert kw["prompted_feedback_questions"][0]["key"] == "campaign_limit"


def test_handle_admin_keys_loads_gm_simulation_for_vault_keeper():
    with app.app_context():
        app.extensions["phase_config"] = _mock_phase_config()
        reg_chain = MagicMock()
        reg_chain.order_by.return_value.all.return_value = []
        fake_rows = [{"username": "gm_test_user", "email": "gm@example.com"}]
        fake_demo = {"total_runs": 0, "runs_with_register_click": 0, "steps": []}
        with app.test_request_context("/admin/keys"):
            with patch.multiple(
                admin_handler,
                RegistrationKey=MagicMock(),
                AccessRequest=MagicMock(),
                current_user=MagicMock(id=1, role="vault_keeper"),
                render_template=MagicMock(return_value="ok"),
                _gm_simulation_usage_serialized_rows=MagicMock(return_value=fake_rows),
                _campaign_code_redemption_rows=MagicMock(return_value=[]),
                _campaign_character_rows=MagicMock(return_value=[]),
                _prompted_feedback_answer_rows=MagicMock(return_value=[]),
                _load_submissions_by_kind=MagicMock(return_value=[]),
            ), patch(
                "app.services.demo_analytics.aggregate_demo_analytics",
                return_value=fake_demo,
            ), patch(
                "app.services.demo_analytics.aggregate_client_analytics",
                return_value={"demo_runs": 0, "submission_count": 0, "demo": {}, "submissions": {}},
            ):
                admin_handler.RegistrationKey.query.filter_by.return_value = reg_chain
                admin_handler.AccessRequest.query.all.return_value = []
                admin_handler.handle_admin_keys()
                admin_handler._gm_simulation_usage_serialized_rows.assert_called_once()
                kw = admin_handler.render_template.call_args[1]
                assert kw["gm_simulation_rows"] == fake_rows
                assert kw["show_gm_usage_tab"] is True
                assert kw["demo_analytics"] == fake_demo
                assert kw["client_analytics"]["demo_runs"] == 0
                assert kw["access_request_rows"] == []
                assert kw["campaign_character_flat_rows"] == []
                assert kw["demo_lead_step"] is None
                assert kw["demo_leads_at_step"] == []
                assert kw["campaign_character_rows"] == []
                assert kw["prompted_feedback_rows"] == []


def test_keys_template_includes_gm_heading_only_when_flag_true():
    from flask import render_template_string

    tpl = """
    {% set show_gm_usage_tab = show_gm_usage_tab | default(false) %}
    {% if show_gm_usage_tab %}
    <span id="gm-simulation-usage-heading">GM simulation usage</span>
    {% endif %}
    """
    with app.app_context():
        with app.test_request_context("/"):
            html_off = render_template_string(tpl, show_gm_usage_tab=False)
            assert "gm-simulation-usage-heading" not in html_off
            html_on = render_template_string(tpl, show_gm_usage_tab=True)
            assert "GM simulation usage" in html_on


def _sample_gm_row():
    return {
        "username": "other_gm",
        "email": "other_gm_leak_test@example.com",
        "key_phase": "alpha",
        "sim_clicks_day": 2,
        "sim_clicks_week": 0,
        "sim_clicks_month": 1,
        "sim_clicks_year": 0,
        "sim_clicks_pause": 3,
        "campaigns_count": 0,
    }


def test_admin_keys_full_template_hides_gm_tab_from_non_vault_render():
    from flask import render_template

    ctx_kwargs = dict(
        keys=[],
        admin_keys=[],
        stats={"total": 0, "used": 0, "available": 0},
        admin_stats={"total": 0, "used": 0, "available": 0},
        access_requests=[],
        prompted_feedback_keys=[],
        prompted_feedback_questions=[],
        vault_phase_slugs=["forge_master"],
        all_phase_slugs=["forge_master"],
        gm_simulation_rows=[_sample_gm_row()],
    )
    with app.test_request_context("/"):
        html = render_template(
            "admin/keys.html",
            show_gm_usage_tab=False,
            **ctx_kwargs,
        )
    assert "gm-simulation-tab" not in html
    assert "other_gm_leak_test@example.com" not in html


def test_admin_keys_full_template_shows_gm_tab_for_vault_keeper_render():
    from flask import render_template

    ctx_kwargs = dict(
        keys=[],
        admin_keys=[],
        stats={"total": 0, "used": 0, "available": 0},
        admin_stats={"total": 0, "used": 0, "available": 0},
        access_requests=[],
        prompted_feedback_keys=[],
        prompted_feedback_questions=[],
        vault_phase_slugs=["forge_master"],
        all_phase_slugs=["forge_master"],
        gm_simulation_rows=[_sample_gm_row()],
    )
    with app.test_request_context("/"):
        html = render_template(
            "admin/keys.html",
            show_gm_usage_tab=True,
            **ctx_kwargs,
        )
    assert 'id="gm-simulation-tab"' in html
    assert "other_gm_leak_test@example.com" in html


def test_campaign_code_redemption_rows_serializes_vault_payload():
    from datetime import datetime

    from app.extensions import db
    from app.models import (
        Campaign,
        CampaignCodeRedemption,
        GMProfile,
        Player,
        User,
    )

    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
        gm_user = User(username="gm_owner", password="x", role="GM")
        player_user = User(username="new_player", password="x", role="Player")
        db.session.add_all([gm_user, player_user])
        db.session.flush()
        gm_profile = GMProfile(user_id=gm_user.id)
        db.session.add(gm_profile)
        db.session.flush()
        campaign = Campaign(
            gm_profile_id=gm_profile.id,
            name="Vault Camp",
            join_code="CAMP-ABCD-EFGH-IJKL",
        )
        db.session.add(campaign)
        db.session.flush()
        player = Player(user_id=player_user.id, campaign_id=campaign.id, is_npc=False)
        db.session.add(player)
        db.session.flush()
        redeemed_at = datetime(2026, 6, 3, 1, 0)
        db.session.add(
            CampaignCodeRedemption(
                campaign_id=campaign.id,
                user_id=player_user.id,
                player_id=player.id,
                source="registration",
                redeemed_at=redeemed_at,
            )
        )
        db.session.commit()

        rows = admin_handler._campaign_code_redemption_rows()

    assert rows == [
        {
            "code_masked": "CAMP-A****-****",
            "campaign_name": "Vault Camp",
            "gm_username": "gm_owner",
            "player_username": "new_player",
            "source": "registration",
            "source_label": "Player registration",
            "redeemed_at": redeemed_at,
        }
    ]


def test_keys_template_renders_campaign_code_redemptions_as_key_rows():
    from datetime import datetime
    from flask import render_template

    redemption = {
        "code_masked": "CAMP-T****-****",
        "campaign_name": "Alpha World",
        "gm_username": "gm_alpha",
        "player_username": "T12",
        "source": "registration",
        "source_label": "Player registration",
        "redeemed_at": datetime(2026, 6, 3, 0, 59),
    }
    ctx_kwargs = dict(
        keys=[],
        admin_keys=[],
        stats={"total": 0, "used": 0, "available": 0},
        admin_stats={"total": 0, "used": 0, "available": 0},
        access_requests=[],
        prompted_feedback_keys=[],
        prompted_feedback_questions=[],
        vault_phase_slugs=["default"],
        all_phase_slugs=["default"],
        gm_simulation_rows=[],
        campaign_code_redemptions=[redemption],
    )
    with app.test_request_context("/"):
        html = render_template(
            "admin/keys.html",
            show_gm_usage_tab=False,
            **ctx_kwargs,
        )

    assert "Campaign codes" not in html
    assert "No campaign code redemptions yet." not in html
    assert "CAMP-T****-****" in html
    assert "<td><span class=\"small\">Player</span></td>" in html
    assert "Used by T12" in html


def test_campaign_character_rows_group_user_campaign_players():
    from datetime import datetime

    from app.extensions import db
    from app.models import Campaign, GMProfile, Player, PlayerCharacterSheet, User

    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
        gm_user = User(username="roster_gm", password="x", role="GM")
        player_user = User(
            username="roster_player",
            password="x",
            role="Player",
            email="roster@example.com",
        )
        db.session.add_all([gm_user, player_user])
        db.session.flush()
        gm_profile = GMProfile(user_id=gm_user.id)
        db.session.add(gm_profile)
        db.session.flush()
        campaign = Campaign(
            gm_profile_id=gm_profile.id,
            name="Roster Campaign",
            system_type="dnd5e",
        )
        db.session.add(campaign)
        db.session.flush()
        player = Player(user_id=player_user.id, campaign_id=campaign.id, is_npc=False)
        npc = Player(user_id=None, campaign_id=campaign.id, is_npc=True)
        solo = Player(user_id=player_user.id, campaign_id=None, is_npc=False)
        db.session.add_all([player, npc, solo])
        db.session.flush()
        updated = datetime(2026, 6, 3, 2, 15)
        db.session.add(
            PlayerCharacterSheet(
                player_id=player.id,
                campaign_id=campaign.id,
                sheet_json={"name": "Keira"},
                updated_at=updated,
            )
        )
        db.session.commit()
        gm_user_id = gm_user.id
        campaign_id = campaign.id
        player_id = player.id

        rows = admin_handler._campaign_character_rows()

    assert rows == [
        {
            "user_id": gm_user_id,
            "username": "roster_gm",
            "email": "—",
            "campaign_count": 1,
            "player_count": 1,
            "campaigns": [
                {
                    "campaign_id": campaign_id,
                    "campaign_name": "Roster Campaign",
                    "system_type": "dnd5e",
                    "is_active": True,
                    "player_count": 1,
                    "players": [
                        {
                            "player_id": player_id,
                            "username": "roster_player",
                            "email": "roster@example.com",
                            "character_name": "Keira",
                            "sheet_updated_at": updated,
                        }
                    ],
                }
            ],
        }
    ]


def test_keys_template_renders_character_tab_with_campaign_rosters():
    from datetime import datetime
    from flask import render_template

    ctx_kwargs = dict(
        keys=[],
        admin_keys=[],
        stats={"total": 0, "used": 0, "available": 0},
        admin_stats={"total": 0, "used": 0, "available": 0},
        access_requests=[],
        prompted_feedback_keys=[],
        prompted_feedback_questions=[],
        vault_phase_slugs=["default"],
        all_phase_slugs=["default"],
        gm_simulation_rows=[],
        campaign_character_rows=[
            {
                "user_id": 3,
                "username": "gm_alpha",
                "email": "gm-alpha@example.com",
                "campaign_count": 1,
                "player_count": 1,
                "campaigns": [
                    {
                        "campaign_id": 7,
                        "campaign_name": "Alpha World",
                        "system_type": "dnd5e",
                        "is_active": True,
                        "player_count": 1,
                        "players": [
                            {
                                "player_id": 12,
                                "username": "T12",
                                "email": "t12@example.com",
                                "character_name": "Mira",
                                "sheet_updated_at": datetime(2026, 6, 3, 0, 59),
                            }
                        ],
                    }
                ],
            }
        ],
        campaign_character_flat_rows=[
            {
                "user_id": 3,
                "gm_username": "gm_alpha",
                "gm_email": "gm-alpha@example.com",
                "campaign_id": 7,
                "campaign_name": "Alpha World",
                "system_type": "dnd5e",
                "is_active": True,
                "character_name": "Mira",
                "player_username": "T12",
                "player_email": "t12@example.com",
                "sheet_updated_at": "2026-06-03T00:59:00Z",
            }
        ],
    )
    with app.test_request_context("/"):
        html = render_template(
            "admin/keys.html",
            show_gm_usage_tab=False,
            **ctx_kwargs,
        )

    assert 'id="characters-tab"' in html
    assert 'id="characters-table"' in html
    assert 'id="characters-search"' in html
    assert "Alpha World" in html
    assert "gm_alpha" in html
    assert "gm-alpha@example.com" in html
    assert "Mira" in html
    assert "T12" in html


def test_keys_template_shows_compact_expansion_interest_badges_for_used_keys():
    from flask import render_template

    yes_latest = SimpleNamespace(
        created_at=datetime(2026, 6, 2, 19, 30),
        source="gm_campaigns_add",
        intent="campaign_limit_upgrade",
    )
    no_latest = SimpleNamespace(
        created_at=datetime(2026, 6, 2, 19, 31),
        source="campaign_selection_create",
        intent="not_interested",
    )
    ctx_kwargs = dict(
        keys=[],
        admin_keys=[],
        stats={"total": 2, "used": 2, "available": 0},
        admin_stats={"total": 0, "used": 0, "available": 0},
        access_requests=[],
        prompted_feedback_rows=[
            {
                "username": "capped_gm",
                "key_phase": "default",
                "answers": {
                    "campaign_limit": {
                        "value": "Yes, express interest",
                        "badge": "success",
                        "created_at": yes_latest.created_at,
                        "source": yes_latest.source,
                    },
                    "monster_import": {
                        "value": "CSV",
                        "badge": "secondary",
                        "created_at": datetime(2026, 6, 2, 19, 40),
                        "source": "Monster import request",
                    },
                    "setup_tutorial": {
                        "value": "A setup tutorial would be useful.",
                        "badge": "secondary",
                        "created_at": datetime(2026, 6, 2, 19, 41),
                        "source": "Setup tutorial interest",
                    },
                },
            },
            {
                "username": "base_gm",
                "key_phase": "default",
                "answers": {
                    "campaign_limit": {
                        "value": "No, stay base tier",
                        "badge": "danger",
                        "created_at": no_latest.created_at,
                        "source": no_latest.source,
                    },
                    "market_import": {
                        "value": "JSON",
                        "badge": "secondary",
                        "created_at": datetime(2026, 6, 2, 19, 42),
                        "source": "Market data import request",
                    },
                },
            },
        ],
        prompted_feedback_questions=[
            {
                "key": "campaign_limit",
                "label": "Ready to expand your realm?",
                "prompt": "You've hit the base limit for active campaigns.",
            },
            {
                "key": "monster_import",
                "label": "Import monsters",
                "prompt": "Which monster file type should import support prepare for?",
            },
            {
                "key": "srd_monsters",
                "label": "SRD monsters",
                "prompt": "Should SRD 5.1 monsters be added to the battle compendium?",
            },
            {
                "key": "market_import",
                "label": "Import market data",
                "prompt": "Which market file type should import support prepare for?",
            },
            {
                "key": "setup_tutorial",
                "label": "Setup tutorial",
                "prompt": "Would a setup tutorial be useful?",
            },
        ],
        vault_phase_slugs=["default"],
        all_phase_slugs=["default"],
        gm_simulation_rows=[],
    )
    with app.test_request_context("/"):
        html = render_template(
            "admin/keys.html",
            show_gm_usage_tab=False,
            **ctx_kwargs,
        )

    assert '<th style="width: 7rem;">Pro?</th>' not in html
    assert 'id="access-requests-tab"' in html
    assert "Permanent record of public" in html
    assert 'id="prompted-feedback-tab"' in html
    assert "Prompted Feedback" in html
    assert "prompted-feedback-scroll" in html
    assert "Ready to expand your realm?" in html
    assert "Yes, express interest" in html
    assert "No, stay base tier" in html
    assert "Import monsters" in html
    assert "SRD monsters" in html
    assert "Import market data" in html
    assert "Setup tutorial" in html
    assert "Which monster file type should import support prepare for?" not in html
    assert "Should SRD 5.1 monsters be added to the battle compendium?" not in html
    assert "Which market file type should import support prepare for?" not in html
    assert "CSV" in html
    assert "JSON" in html
    assert "A setup tutorial would be useful." in html
    assert "gm_campaigns_add" in html
    assert "capped_gm" in html
    assert "base_gm" in html


def test_gm_simulation_usage_api_vault_keeper():
    row = _sample_gm_row()
    with app.app_context():
        with patch.object(
            admin_handler,
            "current_user",
            MagicMock(id=99, role="vault_keeper", is_authenticated=True),
        ):
            with patch.object(
                admin_handler,
                "_gm_simulation_usage_serialized_rows",
                return_value=[row],
            ):
                resp = admin_handler.handle_gm_simulation_usage_api()
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["rows"][0]["username"] == "other_gm"
    assert data["rows"][0]["sim_clicks_day"] == 2
    assert data["rows"][0]["sim_clicks_pause"] == 3


def test_gm_simulation_usage_api_forbidden_for_gm():
    with app.app_context():
        with patch.object(
            admin_handler,
            "current_user",
            MagicMock(id=2, role="GM", is_authenticated=True),
        ):
            resp = admin_handler.handle_gm_simulation_usage_api()
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "vault_keeper_required"


def test_gm_simulation_usage_export_vault_keeper():
    row = _sample_gm_row()
    with app.app_context():
        with app.test_request_context("/"):
            with patch.object(
                admin_handler,
                "current_user",
                MagicMock(id=99, role="vault_keeper", is_authenticated=True),
            ):
                with patch.object(
                    admin_handler,
                    "_gm_simulation_usage_serialized_rows",
                    return_value=[row],
                ):
                    resp = admin_handler.handle_gm_simulation_usage_export()
    assert resp.status_code == 200
    assert "spreadsheetml" in (resp.mimetype or "")
    assert resp.headers.get("Content-Disposition", "").find("attachment") >= 0


def test_gm_simulation_usage_export_forbidden_for_gm():
    with app.app_context():
        with patch.object(
            admin_handler,
            "current_user",
            MagicMock(id=2, role="GM", is_authenticated=True),
        ):
            resp = admin_handler.handle_gm_simulation_usage_export()
    assert resp.status_code == 403


def _mock_sim_state(*, day=0, week=0, month=0, year=0, pause=0, last_tick=None):
    sim = MagicMock()
    sim.sim_clicks_day = day
    sim.sim_clicks_week = week
    sim.sim_clicks_month = month
    sim.sim_clicks_year = year
    sim.sim_clicks_pause = pause
    sim.last_tick_time = last_tick
    return sim


def _mock_campaign(
    *,
    cid,
    name,
    system="dnd5e",
    is_active=True,
    current_game_day=1,
    sim=None,
):
    c = MagicMock()
    c.id = cid
    c.name = name
    c.system_type = system
    c.is_active = is_active
    c.current_game_day = current_game_day
    c.simulation_state = sim
    return c


def _patched_query_chain(users):
    """Return a MagicMock that matches ``User.query.filter(...).options(...).order_by(...).all()``."""

    chain = MagicMock()
    chain.options.return_value.order_by.return_value.all.return_value = list(users)
    return chain


def _passthrough_joinedload():
    """Return a MagicMock standing in for ``joinedload`` whose ``.joinedload`` chains to itself.

    The handler does ``joinedload(User.gm_profile).joinedload(GMProfile.campaigns)``.
    Mocking ``User`` strips the real SQLA attributes, so the easiest patch is to
    no-op ``joinedload`` itself and let chained calls return the same mock.
    """

    fake_jl = MagicMock()
    fake_jl.joinedload.return_value = fake_jl
    return MagicMock(return_value=fake_jl)


def _empty_snapshot_index():
    """Stub for the snapshot-loader: no tombstones."""

    return MagicMock(return_value={})


def _mock_snapshot(
    *,
    campaign_id,
    name,
    system="dnd5e",
    days_simulated=0,
    day=0,
    week=0,
    month=0,
    year=0,
    pause=0,
    last_tick=None,
    deleted_at=None,
):
    snap = MagicMock()
    snap.campaign_id = campaign_id
    snap.campaign_name = name
    snap.system_type = system
    snap.current_game_day = days_simulated + 1
    snap.days_simulated = days_simulated
    snap.sim_clicks_day = day
    snap.sim_clicks_week = week
    snap.sim_clicks_month = month
    snap.sim_clicks_year = year
    snap.sim_clicks_pause = pause
    snap.last_tick_time = last_tick
    snap.deleted_at = deleted_at
    return snap


def test_gm_simulation_usage_payload_includes_per_campaign_rows():
    """Each GM row must carry a ``campaigns`` array so the UI can drill down.

    Aggregates at the GM level must equal the sum of per-campaign metrics, and
    ``last_tick_time`` at the GM level must equal the max across campaigns.
    """
    from datetime import datetime

    earlier = datetime(2026, 1, 5, 12, 0, 0)
    later = datetime(2026, 5, 7, 9, 30, 0)
    camp_a = _mock_campaign(
        cid=10,
        name="Beta",
        current_game_day=5,
        sim=_mock_sim_state(day=3, week=1, pause=2, last_tick=earlier),
    )
    camp_b = _mock_campaign(
        cid=11,
        name="alpha",
        current_game_day=8,
        sim=_mock_sim_state(day=4, month=2, last_tick=later),
        is_active=False,
    )

    gm_profile = MagicMock()
    gm_profile.campaigns = [camp_a, camp_b]

    user = MagicMock()
    user.username = "tgm_two_camps"
    user.email = "tgm@example.com"
    user.gm_profile = gm_profile
    user.registration_key_used = MagicMock(key_phase="alpha")

    with app.app_context():
        with patch.object(admin_handler, "joinedload", _passthrough_joinedload()):
            with patch.object(
                admin_handler, "_load_snapshot_index_by_gm", _empty_snapshot_index()
            ):
                with patch.object(admin_handler, "User") as user_mock:
                    user_mock.query.filter.return_value = _patched_query_chain([user])
                    rows = admin_handler._gm_simulation_usage_serialized_rows()

    assert len(rows) == 1
    r = rows[0]
    assert r["username"] == "tgm_two_camps"
    assert r["campaigns_count"] == 2
    assert r["sim_clicks_day"] == 7
    assert r["sim_clicks_week"] == 1
    assert r["sim_clicks_month"] == 2
    assert r["sim_clicks_pause"] == 2
    assert r["days_simulated"] == (5 - 1) + (8 - 1)
    assert r["last_tick_time"] == later.isoformat()

    camps = r["campaigns"]
    assert isinstance(camps, list) and len(camps) == 2
    by_name = {c["name"]: c for c in camps}
    assert set(by_name.keys()) == {"Beta", "alpha"}
    assert by_name["alpha"]["is_active"] is False
    assert by_name["alpha"]["sim_clicks_day"] == 4
    assert by_name["alpha"]["last_tick_time"] == later.isoformat()
    assert by_name["alpha"]["days_simulated"] == 7
    assert by_name["Beta"]["is_active"] is True
    assert by_name["Beta"]["sim_clicks_pause"] == 2
    assert by_name["Beta"]["last_tick_time"] == earlier.isoformat()
    assert by_name["Beta"]["days_simulated"] == 4
    assert all("system_type" in c for c in camps)
    assert all("current_game_day" in c for c in camps)


def test_gm_simulation_usage_payload_handles_gm_without_campaigns():
    user = MagicMock()
    user.username = "fresh_gm"
    user.email = "fresh@example.com"
    user.gm_profile = None
    user.registration_key_used = MagicMock(key_phase="alpha")

    with app.app_context():
        with patch.object(admin_handler, "joinedload", _passthrough_joinedload()):
            with patch.object(
                admin_handler, "_load_snapshot_index_by_gm", _empty_snapshot_index()
            ):
                with patch.object(admin_handler, "User") as user_mock:
                    user_mock.query.filter.return_value = _patched_query_chain([user])
                    rows = admin_handler._gm_simulation_usage_serialized_rows()

    assert rows == [
        {
            "username": "fresh_gm",
            "email": "fresh@example.com",
            "key_phase": "alpha",
            "sim_clicks_day": 0,
            "sim_clicks_week": 0,
            "sim_clicks_month": 0,
            "sim_clicks_year": 0,
            "sim_clicks_pause": 0,
            "last_tick_time": None,
            "days_simulated": 0,
            "campaigns_count": 0,
            "campaigns": [],
        }
    ]


def test_gm_simulation_usage_payload_folds_in_deleted_campaign_snapshots():
    """Tombstones contribute to per-GM aggregates and appear in the drill-down.

    When a Campaign is deleted, the live aggregate would otherwise drop to
    zero. The vault-keeper analytics view must treat tombstone rows as
    first-class citizens in both totals and the per-campaign expansion,
    flagged ``is_deleted: True``.
    """
    from datetime import datetime

    later = datetime(2026, 5, 7, 9, 30, 0)
    earlier = datetime(2026, 1, 5, 12, 0, 0)
    deleted_at = datetime(2026, 5, 7, 14, 0, 0)

    live = _mock_campaign(
        cid=10,
        name="LiveCamp",
        current_game_day=4,
        sim=_mock_sim_state(day=2, pause=1, last_tick=earlier),
    )
    gm_profile = MagicMock()
    gm_profile.id = 77
    gm_profile.campaigns = [live]

    user = MagicMock()
    user.username = "mixed_gm"
    user.email = "mixed@example.com"
    user.gm_profile = gm_profile
    user.registration_key_used = MagicMock(key_phase="alpha")

    snap = _mock_snapshot(
        campaign_id=999,
        name="DeadCamp",
        days_simulated=10,
        day=5,
        week=1,
        pause=2,
        last_tick=later,
        deleted_at=deleted_at,
    )

    with app.app_context():
        with patch.object(admin_handler, "joinedload", _passthrough_joinedload()):
            with patch.object(
                admin_handler,
                "_load_snapshot_index_by_gm",
                MagicMock(return_value={77: [snap]}),
            ):
                with patch.object(admin_handler, "User") as user_mock:
                    user_mock.query.filter.return_value = _patched_query_chain([user])
                    rows = admin_handler._gm_simulation_usage_serialized_rows()

    r = rows[0]
    assert r["campaigns_count"] == 2
    assert r["sim_clicks_day"] == 7
    assert r["sim_clicks_week"] == 1
    assert r["sim_clicks_pause"] == 3
    assert r["days_simulated"] == 3 + 10
    assert r["last_tick_time"] == later.isoformat()

    by_name = {c["name"]: c for c in r["campaigns"]}
    assert by_name["LiveCamp"]["is_deleted"] is False
    assert by_name["LiveCamp"]["deleted_at"] is None
    assert by_name["DeadCamp"]["is_deleted"] is True
    assert by_name["DeadCamp"]["deleted_at"] == deleted_at.isoformat()
    assert by_name["DeadCamp"]["days_simulated"] == 10
    assert by_name["DeadCamp"]["sim_clicks_day"] == 5

    deleted_idx = next(i for i, c in enumerate(r["campaigns"]) if c["is_deleted"])
    live_idx = next(i for i, c in enumerate(r["campaigns"]) if not c["is_deleted"])
    assert live_idx < deleted_idx, "live campaigns should be listed before deleted ones"


def test_gm_simulation_usage_payload_supports_only_deleted_campaigns():
    """A GM whose campaigns are all deleted still has an analytics row.

    Aggregate totals come entirely from snapshots; the GM-level row must
    still appear in the dashboard table with positive values.
    """
    from datetime import datetime

    last = datetime(2026, 5, 7, 9, 30, 0)
    deleted_at = datetime(2026, 5, 7, 14, 0, 0)

    gm_profile = MagicMock()
    gm_profile.id = 88
    gm_profile.campaigns = []

    user = MagicMock()
    user.username = "all_deleted_gm"
    user.email = "ad@example.com"
    user.gm_profile = gm_profile
    user.registration_key_used = MagicMock(key_phase="alpha")

    snaps = [
        _mock_snapshot(
            campaign_id=1,
            name="A",
            days_simulated=3,
            day=2,
            last_tick=last,
            deleted_at=deleted_at,
        ),
        _mock_snapshot(
            campaign_id=2,
            name="B",
            days_simulated=7,
            day=4,
            pause=1,
            last_tick=last,
            deleted_at=deleted_at,
        ),
    ]

    with app.app_context():
        with patch.object(admin_handler, "joinedload", _passthrough_joinedload()):
            with patch.object(
                admin_handler,
                "_load_snapshot_index_by_gm",
                MagicMock(return_value={88: snaps}),
            ):
                with patch.object(admin_handler, "User") as user_mock:
                    user_mock.query.filter.return_value = _patched_query_chain([user])
                    rows = admin_handler._gm_simulation_usage_serialized_rows()

    r = rows[0]
    assert r["campaigns_count"] == 2
    assert r["sim_clicks_day"] == 6
    assert r["sim_clicks_pause"] == 1
    assert r["days_simulated"] == 10
    assert r["last_tick_time"] == last.isoformat()
    assert all(c["is_deleted"] for c in r["campaigns"])


def test_keys_template_renders_logout_button_in_gm_simulation_tab():
    """Logout link must live INSIDE the GM simulation pane, not just the page.

    The Vault & Keys pane already has its own logout link, so a naive
    ``"/auth/logout" in html`` would pass even with no GM-pane logout. We
    slice the GM-pane fragment first and assert against that fragment so
    the test fails if the link is moved out of the pane.
    """
    from flask import render_template

    ctx_kwargs = dict(
        keys=[],
        admin_keys=[],
        stats={"total": 0, "used": 0, "available": 0},
        admin_stats={"total": 0, "used": 0, "available": 0},
        access_requests=[],
        vault_phase_slugs=["forge_master"],
        all_phase_slugs=["forge_master"],
        gm_simulation_rows=[_sample_gm_row()],
    )
    with app.test_request_context("/"):
        html = render_template(
            "admin/keys.html",
            show_gm_usage_tab=True,
            **ctx_kwargs,
        )
    pane_marker = 'id="gm-simulation-pane"'
    assert pane_marker in html
    pane_start = html.index(pane_marker)
    pane_fragment = html[pane_start:]
    assert ">Log out<" in pane_fragment
    assert "/auth/logout" in pane_fragment
    # Same styling as the Vault & Keys logout (outline-secondary btn-sm
    # inside <p class="mt-3">) — this is the layout the user requested.
    assert "btn btn-outline-secondary btn-sm" in pane_fragment
    assert 'class="mt-3"' in pane_fragment


def test_keys_template_renders_expander_column_when_gm_tab_visible():
    from flask import render_template

    ctx_kwargs = dict(
        keys=[],
        admin_keys=[],
        stats={"total": 0, "used": 0, "available": 0},
        admin_stats={"total": 0, "used": 0, "available": 0},
        access_requests=[],
        vault_phase_slugs=["forge_master"],
        all_phase_slugs=["forge_master"],
        gm_simulation_rows=[_sample_gm_row()],
    )
    with app.test_request_context("/"):
        html = render_template(
            "admin/keys.html",
            show_gm_usage_tab=True,
            **ctx_kwargs,
        )
    assert "gm-sim-expander-cell" in html
    assert "gm-sim-expand-btn" in html
    assert "buildCampaignsTable" in html
