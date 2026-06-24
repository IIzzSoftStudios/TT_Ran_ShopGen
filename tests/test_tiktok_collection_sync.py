"""Tests for TikTok collection sync helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.tiktok_collection_sync import (
    DEFAULT_COLLECTION_URL,
    build_feed_payload,
    extract_video_ids_from_hrefs,
    parse_collection_id,
    write_landing_tiktok_feed,
)


def test_parse_collection_id_from_url():
    collection_id = parse_collection_id(DEFAULT_COLLECTION_URL)
    assert collection_id == "7607510052252994318"


def test_parse_collection_id_rejects_invalid_url():
    assert parse_collection_id("https://www.tiktok.com/@user") is None


def test_extract_video_ids_from_hrefs_dedupes_and_preserves_order():
    hrefs = [
        "https://www.tiktok.com/@user/video/7645277507855453454",
        "https://www.tiktok.com/@user/video/7645277507855453454",
        "https://www.tiktok.com/@user/video/7646056265881373966",
        "https://evil.example/not-a-video",
    ]
    assert extract_video_ids_from_hrefs(hrefs) == [
        "7645277507855453454",
        "7646056265881373966",
    ]


def test_build_feed_payload_sets_collection_fields():
    payload = build_feed_payload(
        collection_url=DEFAULT_COLLECTION_URL,
        video_ids=["7645277507855453454"],
    )
    assert payload["collection_id"] == "7607510052252994318"
    assert payload["hashtag_url"] == DEFAULT_COLLECTION_URL
    assert payload["videos"] == [{"id": "7645277507855453454", "title": ""}]


def test_write_landing_tiktok_feed_round_trip(tmp_path: Path):
    out = tmp_path / "landing_tiktok_videos.json"
    payload = build_feed_payload(
        collection_url=DEFAULT_COLLECTION_URL,
        video_ids=["7645277507855453454"],
    )
    write_landing_tiktok_feed(payload, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["videos"][0]["id"] == "7645277507855453454"
