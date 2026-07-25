"""Curated YouTube playlist videos for the public landing page."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_DEFAULT_PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLWlp4viQxbJM"
_DEFAULT_TITLE = "Econo-Forge Demo Walk Through"
_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "landing_youtube_videos.json"
_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,64}$")


def is_valid_youtube_video_id(value: str) -> bool:
    """Return True when value is a YouTube video ID safe for iframe src."""
    return bool(_YOUTUBE_VIDEO_ID_RE.match(str(value).strip()))


def is_valid_youtube_playlist_id(value: str) -> bool:
    """Return True when value looks like a YouTube playlist ID."""
    return bool(_YOUTUBE_PLAYLIST_ID_RE.match(str(value).strip()))


def _normalize_video(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    raw_id = entry.get("id")
    if raw_id is None:
        return None
    video_id = str(raw_id).strip()
    if not is_valid_youtube_video_id(video_id):
        return None
    title = str(entry.get("title") or "").strip()
    return {"id": video_id, "title": title}


def load_landing_youtube_feed(path: Path | None = None) -> dict[str, Any]:
    """Load curated landing-page YouTube playlist feed from JSON."""
    data_path = path or _DATA_PATH
    try:
        payload = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "title": _DEFAULT_TITLE,
            "playlist_url": _DEFAULT_PLAYLIST_URL,
            "playlist_id": "PLWlp4viQxbJM",
            "videos": [],
        }

    if not isinstance(payload, dict):
        return {
            "title": _DEFAULT_TITLE,
            "playlist_url": _DEFAULT_PLAYLIST_URL,
            "playlist_id": "PLWlp4viQxbJM",
            "videos": [],
        }

    title = str(payload.get("title") or _DEFAULT_TITLE).strip() or _DEFAULT_TITLE
    playlist_url = str(payload.get("playlist_url") or _DEFAULT_PLAYLIST_URL).strip()
    if not playlist_url.startswith("https://www.youtube.com/"):
        playlist_url = _DEFAULT_PLAYLIST_URL

    playlist_id = str(payload.get("playlist_id") or "PLWlp4viQxbJM").strip()
    if not is_valid_youtube_playlist_id(playlist_id):
        playlist_id = "PLWlp4viQxbJM"

    raw_videos = payload.get("videos")
    videos: list[dict[str, str]] = []
    if isinstance(raw_videos, list):
        for entry in raw_videos:
            normalized = _normalize_video(entry)
            if normalized:
                videos.append(normalized)

    return {
        "title": title,
        "playlist_url": playlist_url,
        "playlist_id": playlist_id,
        "videos": videos,
    }
