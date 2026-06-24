"""Email-only creator / sponsor partnership intake — no database persistence."""

from __future__ import annotations

import logging
from typing import Any

from flask import current_app, url_for

logger = logging.getLogger(__name__)

PLATFORM_LABELS = {
    "youtube_shorts": "YouTube / Shorts",
    "tiktok": "TikTok",
    "twitch": "Twitch",
    "instagram_reels": "Instagram Reels",
    "podcast_other": "Podcast / Other",
}

AUDIENCE_LABELS = {
    "under_10k": "Under 10k subscribers/followers",
    "10k_50k": "10k – 50k subscribers/followers",
    "50k_250k": "50k – 250k subscribers/followers",
    "250k_plus": "250k+ subscribers/followers",
}

CONTENT_FOCUS_LABELS = {
    "ttrpg": "Tabletop RPGs (D&D 5E, Pathfinder, OGL, etc.)",
    "gm_advice": "GM Advice / World-Building Tutorials",
    "grand_strategy": "Grand Strategy / Simulation / Management Games",
    "military_sim": "Military Simulation / Tactical Gaming",
}

PARTNERSHIP_LABELS = {
    "affiliate": "Affiliate / Revenue Share",
    "paid_sponsorship": "Paid Sponsorship / Integration",
    "product_exchange": "Product Exchange (Pro / Forge Master access)",
}

TRIAGE_BUCKETS = {
    "under_10k": "Nano-Creator (<10k)",
    "10k_50k": "Mid-Tier (10k–50k)",
    "50k_250k": "Premium Partner (50k–250k)",
    "250k_plus": "Premium Partner (250k+)",
}


def _notify_recipient() -> str:
    return (
        current_app.config.get("CREATOR_PARTNERSHIP_NOTIFY_EMAIL")
        or current_app.config.get("INVESTOR_DECK_NOTIFY_EMAIL")
        or "iizzsoftstudios@gmail.com"
    )


def _sender() -> str:
    return current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@example.com")


def triage_bucket(audience_size: str) -> str:
    return TRIAGE_BUCKETS.get(audience_size, "Unclassified")


def format_submission(payload: dict[str, Any]) -> str:
    focuses = payload.get("content_focus") or []
    focus_text = ", ".join(
        CONTENT_FOCUS_LABELS.get(key, key) for key in focuses
    ) or "—"
    lines = [
        "Econo-Forge creator / sponsor partnership request",
        f"Triage bucket: {triage_bucket(payload['audience_size'])}",
        "",
        f"Full name: {payload['full_name']}",
        f"Email: {payload['email']}",
        f"Primary platform: {PLATFORM_LABELS.get(payload['primary_platform'], payload['primary_platform'])}",
        f"Channel URL / handle: {payload['channel_url']}",
        f"Audience size: {AUDIENCE_LABELS.get(payload['audience_size'], payload['audience_size'])}",
        f"Content focus: {focus_text}",
        f"Avg views / concurrent viewers: {payload['avg_views_note']}",
        f"Partnership type: {PARTNERSHIP_LABELS.get(payload['partnership_type'], payload['partnership_type'])}",
        f"Rate / base CPM: {payload.get('rate_or_cpm') or '—'}",
        "",
        "Campaign pitch:",
        payload["campaign_pitch"],
        "",
        "Review channel fit before replying. No automated Pro tier or affiliate codes are issued from this form.",
    ]
    return "\n".join(lines)


def _auto_response_body(payload: dict[str, Any]) -> str:
    bucket = payload["audience_size"]
    if bucket == "under_10k":
        body = (
            "Thanks for reaching out about partnering with Econo-Forge. "
            "Based on your channel size, we're routing you to our affiliate and product-access track. "
            "Our team will review your submission and follow up with affiliate details and a temporary "
            "Pro tier pass if your content aligns with systems-heavy TTRPG GMs.\n\n"
            "Drive qualified GM signups or hit our engagement targets and we can extend access from there."
        )
    elif bucket == "10k_50k":
        body = (
            "Thanks for your creator partnership request. Our team is hand-reviewing your channel "
            "for alignment with Econo-Forge's core audience—GMs who care about economy, world-building, "
            "and believable campaign systems.\n\n"
            "If your content is a fit, we'll follow up about Forge Master access or a dedicated review series."
        )
    else:
        body = (
            "Thanks for your interest in a premium partnership with Econo-Forge. "
            "Your channel size flags this for direct review by our team. "
            "We'll follow up shortly to discuss paid integrations or sponsorship once we've vetted audience fit."
        )
    return f"{body}\n\n— Econo-Forge\n{url_for('main.index', _external=True)}"


def send_creator_partnership_emails(payload: dict[str, Any]) -> None:
    """Notify the team and send bucket-aware auto-response. Raises on mail failure."""
    from flask_mailman import EmailMessage

    team_msg = EmailMessage(
        f"Creator partnership — {payload['full_name']} ({triage_bucket(payload['audience_size'])})",
        format_submission(payload),
        _sender(),
        [_notify_recipient()],
        reply_to=[payload["email"]],
    )
    team_msg.send()

    auto_msg = EmailMessage(
        "Econo-Forge — creator partnership request received",
        _auto_response_body(payload),
        _sender(),
        [payload["email"]],
    )
    auto_msg.send()
    logger.info("Creator partnership emails sent for %s", payload["email"])
