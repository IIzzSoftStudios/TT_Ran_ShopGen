"""Curated TikTok videos for the public landing page."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_DEFAULT_HASHTAG_URL = "https://www.tiktok.com/tag/econoforge"
_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "landing_tiktok_videos.json"
_TIKTOK_VIDEO_ID_RE = re.compile(r"^\d{10,25}$")


def is_valid_tiktok_video_id(value: str) -> bool:
    """Return True when value is a numeric TikTok video ID safe for iframe src."""
    return bool(_TIKTOK_VIDEO_ID_RE.match(str(value).strip()))


def _normalize_video(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    raw_id = entry.get("id")
    if raw_id is None:
        return None
    video_id = str(raw_id).strip()
    if not is_valid_tiktok_video_id(video_id):
        return None
    title = str(entry.get("title") or "").strip()
    return {"id": video_id, "title": title}


def load_landing_tiktok_feed(path: Path | None = None) -> dict[str, Any]:
    """Load curated landing-page TikTok feed from JSON."""
    data_path = path or _DATA_PATH
    try:
        payload = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"hashtag_url": _DEFAULT_HASHTAG_URL, "videos": []}

    if not isinstance(payload, dict):
        return {"hashtag_url": _DEFAULT_HASHTAG_URL, "videos": []}

    hashtag_url = str(payload.get("hashtag_url") or _DEFAULT_HASHTAG_URL).strip()
    if not hashtag_url.startswith("https://www.tiktok.com/"):
        hashtag_url = _DEFAULT_HASHTAG_URL

    raw_videos = payload.get("videos")
    videos: list[dict[str, str]] = []
    if isinstance(raw_videos, list):
        for entry in raw_videos:
            normalized = _normalize_video(entry)
            if normalized:
                videos.append(normalized)

    return {"hashtag_url": hashtag_url, "videos": videos}
