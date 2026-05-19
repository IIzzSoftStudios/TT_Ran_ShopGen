"""Vault keys dashboard: GM simulation usage tab is vault_keeper-only."""

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
            _load_submissions_by_kind=MagicMock(return_value=[]),
        ):
            admin_handler.RegistrationKey.query.filter_by.return_value = reg_chain
            admin_handler.AccessRequest.query.filter.return_value.all.return_value = []
            admin_handler.handle_admin_keys()
            admin_handler._gm_simulation_usage_serialized_rows.assert_not_called()
            kw = admin_handler.render_template.call_args[1]
            assert kw["gm_simulation_rows"] == []
            assert kw["show_gm_usage_tab"] is False


def test_handle_admin_keys_loads_gm_simulation_for_vault_keeper():
    with app.app_context():
        app.extensions["phase_config"] = _mock_phase_config()
        reg_chain = MagicMock()
        reg_chain.order_by.return_value.all.return_value = []
        fake_rows = [{"username": "gm_test_user", "email": "gm@example.com"}]
        with patch.multiple(
            admin_handler,
            RegistrationKey=MagicMock(),
            AccessRequest=MagicMock(),
            current_user=MagicMock(id=1, role="vault_keeper"),
            render_template=MagicMock(return_value="ok"),
            _gm_simulation_usage_serialized_rows=MagicMock(return_value=fake_rows),
            _load_submissions_by_kind=MagicMock(return_value=[]),
        ):
            admin_handler.RegistrationKey.query.filter_by.return_value = reg_chain
            admin_handler.AccessRequest.query.filter.return_value.all.return_value = []
            admin_handler.handle_admin_keys()
            admin_handler._gm_simulation_usage_serialized_rows.assert_called_once()
            kw = admin_handler.render_template.call_args[1]
            assert kw["gm_simulation_rows"] == fake_rows
            assert kw["show_gm_usage_tab"] is True


def test_keys_template_includes_gm_heading_only_when_flag_true():
    from flask import render_template_string

    tpl = """
    {% set show_gm_usage_tab = show_gm_usage_tab | default(false) %}
    {% if show_gm_usage_tab %}
    <span id="gm-simulation-usage-heading">GM simulation usage</span>
    {% endif %}
    """
    with app.app_context():
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
