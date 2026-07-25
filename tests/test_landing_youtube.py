"""Landing page YouTube demo walkthrough rail."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.landing_youtube import (
    is_valid_youtube_playlist_id,
    is_valid_youtube_video_id,
    load_landing_youtube_feed,
)


def test_is_valid_youtube_video_id_accepts_standard_ids():
    assert is_valid_youtube_video_id("p8-E3vXNkL8") is True
    assert is_valid_youtube_video_id("_6GOEt3TjHI") is True


def test_is_valid_youtube_video_id_rejects_malformed():
    assert is_valid_youtube_video_id("") is False
    assert is_valid_youtube_video_id("short") is False
    assert is_valid_youtube_video_id("https://evil.example/") is False
    assert is_valid_youtube_video_id("abcdefghijkl") is False  # 12 chars


def test_is_valid_youtube_playlist_id_accepts_playlist_ids():
    assert is_valid_youtube_playlist_id("PLWlp4viQxbJM") is True


def test_load_landing_youtube_feed_filters_invalid_entries(tmp_path: Path):
    data_path = tmp_path / "landing_youtube_videos.json"
    data_path.write_text(
        json.dumps(
            {
                "title": "Econo-Forge Demo Walk Through",
                "playlist_url": "https://www.youtube.com/playlist?list=PLWlp4viQxbJM",
                "playlist_id": "PLWlp4viQxbJM",
                "videos": [
                    {"id": "p8-E3vXNkL8", "title": "Intro"},
                    {"id": "bad-id"},
                    {"id": "https://evil.example/video"},
                ],
            }
        ),
        encoding="utf-8",
    )

    feed = load_landing_youtube_feed(data_path)

    assert feed["playlist_url"] == "https://www.youtube.com/playlist?list=PLWlp4viQxbJM"
    assert feed["videos"] == [{"id": "p8-E3vXNkL8", "title": "Intro"}]


def test_landing_hides_youtube_rail_when_videos_empty(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.main_routes.load_landing_youtube_feed",
        lambda: {
            "title": "Econo-Forge Demo Walk Through",
            "playlist_url": "https://www.youtube.com/playlist?list=PLWlp4viQxbJM",
            "playlist_id": "PLWlp4viQxbJM",
            "videos": [],
        },
    )
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'class="youtube-rail-track"' not in html
    assert 'class="youtube-section"' not in html


def test_landing_shows_youtube_rail_when_videos_configured(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'class="youtube-rail-track"' in html
    assert "Econo-Forge Demo Walk Through" in html
    assert "p8-E3vXNkL8" in html
    assert 'data-src="https://www.youtube.com/embed/p8-E3vXNkL8' in html
    assert "View playlist on YouTube" in html
    assert "https://www.youtube.com/playlist?list=PLWlp4viQxbJM" in html
