"""Try Demo lead capture (name/email) + last-step funnel helpers."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from flask import session

from app.extensions import db
from app.models import DemoLead
from app.services.demo_analytics import GM_STEP_TRAIL, normalize_step_key

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: Any) -> Optional[str]:
    if value is None:
        return None
    email = str(value).strip().lower()
    if not email or len(email) > 255 or not _EMAIL_RE.match(email):
        return None
    return email


def normalize_contact_name(value: Any) -> Optional[str]:
    if value is None:
        return None
    name = " ".join(str(value).strip().split())
    if not name or len(name) > 120:
        return None
    return name


def get_lead_for_run(demo_run_id: str | None) -> Optional[DemoLead]:
    if not demo_run_id:
        return None
    return DemoLead.query.filter_by(demo_run_id=demo_run_id).first()


def session_has_demo_lead() -> bool:
    run_id = session.get("demo_run_id")
    return get_lead_for_run(run_id) is not None


def upsert_demo_lead(
    *,
    demo_run_id: str,
    demo_anon_id: str,
    contact_name: str,
    email: str,
) -> DemoLead:
    row = DemoLead.query.filter_by(demo_run_id=demo_run_id).first()
    if row is None:
        row = DemoLead(
            demo_run_id=demo_run_id,
            demo_anon_id=demo_anon_id,
            contact_name=contact_name,
            email=email,
        )
        db.session.add(row)
    else:
        row.demo_anon_id = demo_anon_id
        row.contact_name = contact_name
        row.email = email
        row.updated_at = datetime.utcnow()
    return row


def touch_last_step(*, demo_run_id: str | None, step_key: str | None) -> None:
    if not demo_run_id:
        return
    key = normalize_step_key(step_key)
    if not key:
        return
    row = DemoLead.query.filter_by(demo_run_id=demo_run_id).first()
    if row is None:
        return
    row.last_step_key = key
    row.last_step_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()


def leads_stopped_at(step_key: str | None) -> list[DemoLead]:
    key = normalize_step_key(step_key)
    if not key:
        return []
    return (
        DemoLead.query.filter_by(last_step_key=key)
        .order_by(DemoLead.last_step_at.desc(), DemoLead.id.desc())
        .all()
    )


def funnel_step_options() -> list[str]:
    return list(GM_STEP_TRAIL)
