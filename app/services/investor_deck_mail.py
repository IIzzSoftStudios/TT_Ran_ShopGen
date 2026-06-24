"""Email-only investor deck request delivery — no database persistence."""

from __future__ import annotations

import logging
from typing import Any

from flask import current_app, url_for

logger = logging.getLogger(__name__)

INVESTOR_STATUS_LABELS = {
    "accredited": "Accredited Investor",
    "institutional": "Institutional Fund / Venture Capital Firm",
}

CHECK_SIZE_LABELS = {
    "10000_25000": "$10,000 – $25,000",
    "25000_50000": "$25,000 – $50,000",
    "50000_100000": "$50,000 – $100,000",
    "100000_plus": "$100,000+",
}


def _notify_recipient() -> str:
    return (
        current_app.config.get("INVESTOR_DECK_NOTIFY_EMAIL")
        or "iizzsoftstudios@gmail.com"
    )


def _sender() -> str:
    return current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@example.com")


def format_submission(payload: dict[str, Any]) -> str:
  """Plain-text summary for the internal review email."""
  lines = [
      "Econo-Forge investor deck request",
      "",
      f"Full name: {payload['full_name']}",
      f"Email: {payload['email']}",
      f"Company / fund / syndicate: {payload['company_fund_name']}",
      f"Fund website: {payload.get('fund_website') or '—'}",
      f"Investor status: {INVESTOR_STATUS_LABELS.get(payload['investor_status'], payload['investor_status'])}",
      f"Typical check size: {CHECK_SIZE_LABELS.get(payload['check_size'], payload.get('check_size') or '—')}",
      f"Prior SaaS / gaming / infrastructure investment: {payload['prior_saas_gaming_invest']}",
      "Confidentiality acknowledged: yes",
  ]
  lines.append("Review before sending a secure deck link. Do not auto-reply with the investor PDF.")
  return "\n".join(lines)


def send_investor_request_emails(payload: dict[str, Any]) -> None:
    """Notify the team and send the submitter auto-response. Raises on mail failure."""
    from flask_mailman import EmailMessage

    team_msg = EmailMessage(
        f"Investor deck request — {payload['full_name']}",
        format_submission(payload),
        _sender(),
        [_notify_recipient()],
        reply_to=[payload["email"]],
    )
    team_msg.send()

    auto_body = (
        "Thank you for your interest in Econo-Forge's pre-seed round. "
        "Our team is reviewing your request to ensure compliance with our regulatory "
        "data room frameworks. We will follow up shortly with access.\n\n"
        f"— Econo-Forge\n{url_for('main.index', _external=True)}"
    )
    auto_msg = EmailMessage(
        "Econo-Forge — investor deck request received",
        auto_body,
        _sender(),
        [payload["email"]],
    )
    auto_msg.send()
    logger.info("Investor deck request emails sent for %s", payload["email"])
