"""Parse browser / OS / device type from User-Agent (no external deps)."""

from __future__ import annotations

from typing import Any


def parse_user_agent(user_agent: str | None) -> dict[str, str | None]:
    raw = (user_agent or "").strip()[:512]
    lower = raw.lower()

    if not raw:
        return {
            "client_browser": None,
            "client_os": None,
            "client_device_type": None,
        }

    if "ipad" in lower or ("tablet" in lower and "mobile" not in lower):
        device = "tablet"
    elif any(token in lower for token in ("mobile", "iphone", "ipod", "android")):
        device = "mobile"
    else:
        device = "desktop"

    browser = "Unknown"
    if "edg/" in lower or "edge/" in lower:
        browser = "Edge"
    elif "firefox/" in lower or "fxios/" in lower:
        browser = "Firefox"
    elif "opr/" in lower or "opera" in lower:
        browser = "Opera"
    elif "brave/" in lower:
        browser = "Brave"
    elif "chrome/" in lower or "crios/" in lower:
        browser = "Chrome"
    elif "safari/" in lower:
        browser = "Safari"

    os_name = "Unknown"
    if "iphone" in lower or "ipad" in lower or "ipod" in lower:
        os_name = "iOS"
    elif "windows" in lower:
        os_name = "Windows"
    elif "mac os x" in lower or "macintosh" in lower:
        os_name = "macOS"
    elif "android" in lower:
        os_name = "Android"
    elif "linux" in lower:
        os_name = "Linux"

    return {
        "client_browser": browser[:40],
        "client_os": os_name[:40],
        "client_device_type": device[:20],
    }


def client_context_from_request() -> dict[str, str | None]:
    try:
        from flask import has_request_context, request

        if not has_request_context():
            return parse_user_agent(None)
        return parse_user_agent(request.headers.get("User-Agent"))
    except Exception:
        return parse_user_agent(None)


def apply_client_context(target: Any, fields: dict[str, str | None] | None = None) -> None:
    ctx = fields if fields is not None else client_context_from_request()
    for key in ("client_browser", "client_os", "client_device_type"):
        if hasattr(target, key):
            setattr(target, key, ctx.get(key))
