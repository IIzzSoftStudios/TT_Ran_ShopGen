"""First-party Demo walkthrough analytics (Vault Demo tab)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from flask import session
from sqlalchemy import func

from app.extensions import db
from app.models import DemoAnalyticsEvent
from app.services.client_context import client_context_from_request

EVENT_DEMO_START = "demo_start"
EVENT_STEP_VIEW = "step_view"
EVENT_REGISTER_CLICK = "register_click"
ALLOWED_EVENT_TYPES = frozenset(
    {EVENT_DEMO_START, EVENT_STEP_VIEW, EVENT_REGISTER_CLICK}
)
SURFACE_GM_TUTORIAL = "gm_tutorial"

# Ordered GM coach phases for vault funnel display (matches demo_tutorial.js).
GM_STEP_TRAIL: tuple[str, ...] = (
    "welcome",
    "point_nations",
    "draw_on_map",
    "draw_borders",
    "open_nations_ruler",
    "add_ruler",
    "wizard_identity",
    "wizard_species",
    "wizard_class",
    "wizard_background",
    "wizard_abilities",
    "wizard_review",
    "point_cities",
    "place_cities",
    "owners_info",
    "select_city",
    "city_popout",
    "open_city",
    "point_shops",
    "place_shops",
    "shop_owners_info",
    "select_shop",
    "shop_popout",
    "open_shop",
    "point_items",
    "items_briefing",
    "catalog_explain",
    "catalog_select_item",
    "catalog_stock",
    "catalog_assign_shop",
    "catalog_confirm_stock",
    "back_to_city",
    "select_shop_goods",
    "return_world_map",
    "select_city_goods",
    "point_market",
    "market_explain",
    "point_calendar",
    "calendar_explain",
    "sim_week",
    "sim_result",
    "point_species",
    "species_explain",
    "point_traits",
    "traits_explain",
    "point_classes",
    "classes_explain",
    "point_spells",
    "spells_explain",
    "point_monsters",
    "monsters_explain",
    "invite_open",
    "invite_reveal",
    "invite_copy",
    "point_profile",
    "switch_campaigns",
    "drawing",
    "close_ready",
    "register",
)

ALLOWED_STEP_KEYS = frozenset(GM_STEP_TRAIL)
_STEP_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def mint_demo_run_id() -> str:
    """Create a new demo run UUID and store it on the Flask session."""
    run_id = str(uuid.uuid4())
    session["demo_run_id"] = run_id
    session.modified = True
    return run_id


def current_demo_run_id() -> str | None:
    raw = session.get("demo_run_id")
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    return raw if len(raw) == 36 else None


def normalize_step_key(value: Any) -> str | None:
    if value is None:
        return None
    key = str(value).strip().lower()
    if not key or not _STEP_KEY_RE.match(key):
        return None
    if key not in ALLOWED_STEP_KEYS:
        return None
    return key


def record_demo_event(
    *,
    event_type: str,
    demo_run_id: str,
    demo_anon_id: str,
    user_id: int | None = None,
    step_key: str | None = None,
    surface: str = SURFACE_GM_TUTORIAL,
    commit: bool = True,
) -> DemoAnalyticsEvent | None:
    """Insert an allowlisted demo analytics event. Returns None if rejected."""
    et = str(event_type or "").strip().lower()
    if et not in ALLOWED_EVENT_TYPES:
        return None
    run_id = str(demo_run_id or "").strip()
    if len(run_id) != 36:
        return None
    anon = str(demo_anon_id or "").strip()
    if len(anon) < 8 or len(anon) > 64:
        return None

    normalized_step: str | None = None
    if et in (EVENT_STEP_VIEW, EVENT_REGISTER_CLICK):
        normalized_step = normalize_step_key(step_key)
        if not normalized_step:
            return None
    elif step_key:
        # demo_start should not carry a step key
        normalized_step = None

    if et == EVENT_STEP_VIEW:
        # Dedupe consecutive identical step_view for the same run.
        last = (
            DemoAnalyticsEvent.query.filter_by(
                demo_run_id=run_id,
                event_type=EVENT_STEP_VIEW,
            )
            .order_by(DemoAnalyticsEvent.id.desc())
            .first()
        )
        if last is not None and last.step_key == normalized_step:
            return last

    row = DemoAnalyticsEvent(
        demo_run_id=run_id,
        demo_anon_id=anon,
        user_id=user_id,
        event_type=et,
        step_key=normalized_step,
        surface=str(surface or SURFACE_GM_TUTORIAL)[:40] or SURFACE_GM_TUTORIAL,
    )
    ctx = client_context_from_request()
    row.client_browser = ctx.get("client_browser")
    row.client_os = ctx.get("client_os")
    row.client_device_type = ctx.get("client_device_type")
    db.session.add(row)
    if et != EVENT_DEMO_START:
        _sync_demo_start_client_context(run_id, ctx)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return row


def _sync_demo_start_client_context(
    run_id: str, ctx: dict[str, str | None] | None = None
) -> None:
    """Backfill demo_start row when step/register events carry the first UA snapshot."""
    if not run_id or not ctx:
        return
    if not any(ctx.get(k) for k in ("client_browser", "client_os", "client_device_type")):
        return
    start_row = (
        DemoAnalyticsEvent.query.filter_by(
            demo_run_id=run_id,
            event_type=EVENT_DEMO_START,
        )
        .order_by(DemoAnalyticsEvent.id.asc())
        .first()
    )
    if start_row is None:
        return
    changed = False
    for key in ("client_browser", "client_os", "client_device_type"):
        if getattr(start_row, key, None) in (None, "") and ctx.get(key):
            setattr(start_row, key, ctx.get(key))
            changed = True
    if changed:
        db.session.flush()


def aggregate_demo_analytics(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """Build vault tab summary + per-step funnel rows."""
    q = DemoAnalyticsEvent.query
    if since is not None:
        q = q.filter(DemoAnalyticsEvent.created_at >= since)
    if until is not None:
        q = q.filter(DemoAnalyticsEvent.created_at < until)

    total_runs = (
        q.filter(DemoAnalyticsEvent.event_type == EVENT_DEMO_START)
        .with_entities(func.count(func.distinct(DemoAnalyticsEvent.demo_run_id)))
        .scalar()
        or 0
    )
    total_runs = int(total_runs)

    runs_with_register = (
        q.filter(DemoAnalyticsEvent.event_type == EVENT_REGISTER_CLICK)
        .with_entities(func.count(func.distinct(DemoAnalyticsEvent.demo_run_id)))
        .scalar()
        or 0
    )
    runs_with_register = int(runs_with_register)
    register_conversion_pct = (
        round((runs_with_register / total_runs) * 100.0, 1) if total_runs else 0.0
    )

    step_reach_rows = (
        q.filter(DemoAnalyticsEvent.event_type == EVENT_STEP_VIEW)
        .with_entities(
            DemoAnalyticsEvent.step_key,
            func.count(func.distinct(DemoAnalyticsEvent.demo_run_id)),
        )
        .group_by(DemoAnalyticsEvent.step_key)
        .all()
    )
    reach_by_step = {str(k): int(c) for k, c in step_reach_rows if k}

    register_by_step_rows = (
        q.filter(DemoAnalyticsEvent.event_type == EVENT_REGISTER_CLICK)
        .with_entities(
            DemoAnalyticsEvent.step_key,
            func.count(DemoAnalyticsEvent.id),
        )
        .group_by(DemoAnalyticsEvent.step_key)
        .all()
    )
    register_clicks_by_step = {
        str(k): int(c) for k, c in register_by_step_rows if k
    }

    steps: list[dict[str, Any]] = []
    for key in GM_STEP_TRAIL:
        reached = int(reach_by_step.get(key, 0))
        pct = round((reached / total_runs) * 100.0, 1) if total_runs else 0.0
        steps.append(
            {
                "step_key": key,
                "runs_reached": reached,
                "reach_pct": pct,
                "register_clicks": int(register_clicks_by_step.get(key, 0)),
            }
        )

    return {
        "total_runs": total_runs,
        "runs_with_register_click": runs_with_register,
        "register_conversion_pct": register_conversion_pct,
        "steps": steps,
        "client_breakdown": _client_breakdown_for_query(q),
    }


def _breakdown_rows(
    query,
    *,
    group_col,
    distinct_col=None,
) -> list[dict[str, Any]]:
    distinct = distinct_col or DemoAnalyticsEvent.demo_run_id
    rows = (
        query.with_entities(
            group_col,
            func.count(func.distinct(distinct)),
        )
        .group_by(group_col)
        .order_by(func.count(func.distinct(distinct)).desc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for label, count in rows:
        key = str(label or "Unknown")
        out.append({"label": key, "count": int(count or 0)})
    return out


def _client_breakdown_for_query(query) -> dict[str, list[dict[str, Any]]]:
    """Per demo run: best client context from any event (not only demo_start)."""
    start_run_ids = (
        query.filter(DemoAnalyticsEvent.event_type == EVENT_DEMO_START)
        .with_entities(DemoAnalyticsEvent.demo_run_id)
        .distinct()
        .subquery()
    )
    per_run = (
        query.filter(DemoAnalyticsEvent.demo_run_id.in_(start_run_ids))
        .with_entities(
            DemoAnalyticsEvent.demo_run_id,
            func.max(DemoAnalyticsEvent.client_browser).label("client_browser"),
            func.max(DemoAnalyticsEvent.client_os).label("client_os"),
            func.max(DemoAnalyticsEvent.client_device_type).label("client_device_type"),
        )
        .group_by(DemoAnalyticsEvent.demo_run_id)
        .all()
    )
    browser_counts: dict[str, int] = {}
    os_counts: dict[str, int] = {}
    device_counts: dict[str, int] = {}
    for _run_id, browser, os_name, device in per_run:
        b_key = str(browser or "Unknown")
        o_key = str(os_name or "Unknown")
        d_key = str(device or "Unknown")
        browser_counts[b_key] = browser_counts.get(b_key, 0) + 1
        os_counts[o_key] = os_counts.get(o_key, 0) + 1
        device_counts[d_key] = device_counts.get(d_key, 0) + 1

    def _sorted_rows(counts: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {"label": label, "count": counts[label]}
            for label in sorted(counts.keys(), key=lambda k: (-counts[k], k.lower()))
        ]

    return {
        "browsers": _sorted_rows(browser_counts),
        "operating_systems": _sorted_rows(os_counts),
        "devices": _sorted_rows(device_counts),
    }


def aggregate_client_analytics(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """Browser/device breakdown for demo runs and account-menu submissions."""
    from app.models import UserSubmission

    demo_q = DemoAnalyticsEvent.query
    if since is not None:
        demo_q = demo_q.filter(DemoAnalyticsEvent.created_at >= since)
    if until is not None:
        demo_q = demo_q.filter(DemoAnalyticsEvent.created_at < until)

    sub_q = UserSubmission.query
    if since is not None:
        sub_q = sub_q.filter(UserSubmission.created_at >= since)
    if until is not None:
        sub_q = sub_q.filter(UserSubmission.created_at < until)

    demo_starts = (
        demo_q.filter(DemoAnalyticsEvent.event_type == EVENT_DEMO_START)
        .with_entities(func.count(func.distinct(DemoAnalyticsEvent.demo_run_id)))
        .scalar()
        or 0
    )

    return {
        "demo_runs": int(demo_starts),
        "submission_count": int(sub_q.count()),
        "demo": _client_breakdown_for_query(demo_q),
        "submissions": {
            "browsers": _breakdown_rows(
                sub_q,
                group_col=UserSubmission.client_browser,
                distinct_col=UserSubmission.id,
            ),
            "operating_systems": _breakdown_rows(
                sub_q,
                group_col=UserSubmission.client_os,
                distinct_col=UserSubmission.id,
            ),
            "devices": _breakdown_rows(
                sub_q,
                group_col=UserSubmission.client_device_type,
                distinct_col=UserSubmission.id,
            ),
        },
    }
