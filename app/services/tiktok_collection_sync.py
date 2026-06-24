"""Sync landing-page TikTok videos from a public TikTok collection."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.services.landing_tiktok import _DATA_PATH, is_valid_tiktok_video_id

DEFAULT_COLLECTION_URL = (
    "https://www.tiktok.com/@iizzsoftstudios/collection/Econo-Forge-7607510052252994318"
)
_COLLECTION_ID_RE = re.compile(r"/collection/[^/?#]*-(\d{10,25})(?:[/?#]|$)")
_VIDEO_HREF_RE = re.compile(r"/video/(\d{10,25})")


def parse_collection_id(collection_url: str) -> str | None:
    """Extract numeric collection ID from a TikTok collection URL."""
    match = _COLLECTION_ID_RE.search(str(collection_url or "").strip())
    if not match:
        return None
    collection_id = match.group(1)
    return collection_id if is_valid_tiktok_video_id(collection_id) else None


def extract_video_ids_from_hrefs(hrefs: list[str]) -> list[str]:
    """Return unique TikTok video IDs in first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for href in hrefs:
        for video_id in _VIDEO_HREF_RE.findall(str(href)):
            if video_id in seen:
                continue
            if not is_valid_tiktok_video_id(video_id):
                continue
            seen.add(video_id)
            ordered.append(video_id)
    return ordered


def fetch_collection_video_hrefs(collection_url: str, *, headless: bool = True) -> list[str]:
    """Load a public TikTok collection page and return video post hrefs."""
    from playwright.sync_api import sync_playwright

    hrefs: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.goto(collection_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(4000)

        for label in ("Accept all", "Decline optional cookies", "Reject all"):
            try:
                page.get_by_role("button", name=label).click(timeout=2000)
                break
            except Exception:
                pass

        for _ in range(8):
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(1200)

        hrefs = page.eval_on_selector_all(
            "a[href*='/video/']",
            "els => els.map(e => e.href)",
        )
        browser.close()
    return [str(href) for href in hrefs]


def build_feed_payload(
    *,
    collection_url: str,
    video_ids: list[str],
    hashtag: str = "econoforge",
) -> dict[str, Any]:
    """Build landing feed JSON payload from scraped video IDs."""
    collection_id = parse_collection_id(collection_url)
    videos = [{"id": video_id, "title": ""} for video_id in video_ids]
    payload: dict[str, Any] = {
        "hashtag": hashtag,
        "hashtag_url": collection_url,
        "collection_url": collection_url,
        "videos": videos,
    }
    if collection_id:
        payload["collection_id"] = collection_id
    return payload


def write_landing_tiktok_feed(payload: dict[str, Any], path: Path | None = None) -> Path:
    """Write landing TikTok feed JSON to disk."""
    out_path = path or _DATA_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out_path


def sync_landing_tiktok_collection(
    collection_url: str = DEFAULT_COLLECTION_URL,
    *,
    output_path: Path | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """Fetch collection videos and write landing feed JSON."""
    hrefs = fetch_collection_video_hrefs(collection_url, headless=headless)
    video_ids = extract_video_ids_from_hrefs(hrefs)
    if not video_ids:
        raise RuntimeError(
            "No TikTok video IDs found in collection page. "
            "Confirm the collection URL is public and contains video posts."
        )
    payload = build_feed_payload(collection_url=collection_url, video_ids=video_ids)
    write_landing_tiktok_feed(payload, output_path)
    return payload
