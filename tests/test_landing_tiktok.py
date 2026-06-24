"""Landing page TikTok community rail."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.landing_tiktok import (
    is_valid_tiktok_video_id,
    load_landing_tiktok_feed,
)


def test_is_valid_tiktok_video_id_accepts_numeric_ids():
    assert is_valid_tiktok_video_id("7123456789012345678") is True
    assert is_valid_tiktok_video_id("6718335390845095173") is True


def test_is_valid_tiktok_video_id_rejects_malformed():
    assert is_valid_tiktok_video_id("") is False
    assert is_valid_tiktok_video_id("not-a-number") is False
    assert is_valid_tiktok_video_id("https://evil.example/") is False
    assert is_valid_tiktok_video_id("123") is False


def test_load_landing_tiktok_feed_filters_invalid_entries(tmp_path: Path):
    data_path = tmp_path / "landing_tiktok_videos.json"
    data_path.write_text(
        json.dumps(
            {
                "hashtag_url": "https://www.tiktok.com/tag/econoforge",
                "videos": [
                    {"id": "7123456789012345678", "title": "Market day clip"},
                    {"id": "bad-id"},
                    {"id": "https://evil.example/video"},
                ],
            }
        ),
        encoding="utf-8",
    )

    feed = load_landing_tiktok_feed(data_path)

    assert feed["hashtag_url"] == "https://www.tiktok.com/tag/econoforge"
    assert feed["videos"] == [
        {"id": "7123456789012345678", "title": "Market day clip"},
    ]


def test_landing_hides_tiktok_rail_when_videos_empty(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.main_routes.load_landing_tiktok_feed",
        lambda: {
            "hashtag_url": "https://www.tiktok.com/tag/econoforge",
            "videos": [],
        },
    )
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'class="tiktok-rail-track"' not in html
    assert 'class="tiktok-section"' not in html
    assert "What you get" not in html
    assert "Built for long campaigns" not in html


def test_landing_shows_tiktok_rail_when_videos_configured(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'class="tiktok-rail-track"' in html
    assert "7645277507855453454" in html
    assert "player/v1/7645277507855453454" in html
    assert 'data-src="https://www.tiktok.com/player/v1/7645277507855453454' in html
    assert "autoplay=1" in html
    assert "muted=1" in html
    assert "Creator Approved" in html
    assert "TikToks updated every update." in html
    assert "View all on TikTok" in html
    assert "TikTok #Econoforge" in html
