"""Normalize account-menu submissions into UserSubmission rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from flask import request

from app.constants.submission_categories import (
    EXTRA_KEYS_BY_KIND,
    KINDS,
    VALID_CATEGORIES_BY_KIND,
    VALID_FREQUENCIES,
    VALID_SEVERITIES,
)
from app.models import User, UserSubmission


@dataclass
class SubmissionValidationError:
    message: str
    status_code: int = 400


def sanitize_page_url(raw_url: str | None) -> str:
    """Store path+query only; block javascript: and off-site absolute URLs."""
    raw = (raw_url or request.referrer or "/").strip()
    if raw.lower().startswith("javascript:"):
        return "/"
    try:
        parsed = urlparse(raw)
        if parsed.netloc:
            host = (request.host or "").split(":")[0]
            if parsed.netloc != host and parsed.netloc != request.host:
                path = parsed.path or "/"
            else:
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"
        else:
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
        return path[:500]
    except Exception:
        return "/"


def whitelist_extra(kind: str, extra: dict[str, Any]) -> dict[str, Any]:
    allowed = EXTRA_KEYS_BY_KIND.get(kind, frozenset())
    return {k: extra[k] for k in extra if k in allowed}


def normalize_session_mode(session: dict) -> str:
    mode = session.get("session_mode")
    if mode is None:
        return "hub"
    submitted = str(mode).lower()
    if submitted not in ("gm", "player", "hub"):
        return "hub"
    return submitted


def parse_campaign_id(session: dict) -> int | None:
    raw = session.get("campaign_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def build_submission(
    data: dict,
    user: User,
    session: dict,
) -> UserSubmission | SubmissionValidationError:
    if user.role == "vault_keeper":
        return SubmissionValidationError(
            "Vault keepers are barred from submitting triage items.", 403
        )

    kind = data.get("kind")
    if kind not in KINDS:
        return SubmissionValidationError("Invalid submission type classification.")

    category = data.get("category")
    if category not in VALID_CATEGORIES_BY_KIND[kind]:
        return SubmissionValidationError(f"Invalid category for classification: {kind}.")

    title = (data.get("title") or "").strip()[:120] or None
    extra_payload: dict[str, Any] = {}
    body_content = ""

    if kind == "bug_report":
        severity = data.get("severity")
        if severity not in VALID_SEVERITIES:
            return SubmissionValidationError("Invalid severity rating.")
        if not title:
            return SubmissionValidationError("Title is required.")
        body_content = (data.get("what_happened") or "")[:4000]
        extra_payload = whitelist_extra(
            kind,
            {
                "steps_to_reproduce": (data.get("steps_to_reproduce") or "")[:4000],
                "expected_behavior": (data.get("expected_behavior") or "")[:2000],
                "severity": severity,
            },
        )
    elif kind == "feedback":
        body_content = (data.get("trying_to_do") or "")[:2000]
        rating = data.get("rating")
        if rating not in (None, ""):
            try:
                rating_val = int(rating)
                if not (1 <= rating_val <= 5):
                    raise ValueError
                extra_payload["rating"] = rating_val
            except (ValueError, TypeError):
                return SubmissionValidationError(
                    "Rating must be an integer between 1 and 5."
                )
        extra_payload = whitelist_extra(
            kind,
            {
                **extra_payload,
                "worked_well": (data.get("worked_well") or "")[:2000],
                "frustrating": (data.get("frustrating") or "")[:2000],
            },
        )
    else:
        if not title:
            return SubmissionValidationError("Title is required.")
        frequency = data.get("frequency") or None
        if frequency and frequency not in VALID_FREQUENCIES:
            return SubmissionValidationError("Invalid frequency metric.")
        body_content = (data.get("description") or "")[:4000]
        extra_payload = whitelist_extra(
            kind,
            {
                "frequency": frequency,
                "beta_test": bool(data.get("beta_test")),
            },
        )

    if not body_content.strip():
        return SubmissionValidationError("Primary descriptive body content is required.")

    return UserSubmission(
        kind=kind,
        user_id=user.id,
        username_snapshot=user.username,
        submitted_session_mode=normalize_session_mode(session),
        account_role=user.role,
        category=category,
        title=title,
        body=body_content,
        extra=extra_payload,
        page_url=sanitize_page_url(data.get("page_url")),
        campaign_id=parse_campaign_id(session),
    )
