#!/usr/bin/env python3
"""Sync landing-page TikTok videos from a TikTok collection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.tiktok_collection_sync import (  # noqa: E402
    DEFAULT_COLLECTION_URL,
    sync_landing_tiktok_collection,
)
from app.services.landing_tiktok import _DATA_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection-url",
        default=DEFAULT_COLLECTION_URL,
        help="Public TikTok collection URL to sync",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DATA_PATH,
        help="Output JSON path (default: app/data/landing_tiktok_videos.json)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser headed (debug only)",
    )
    args = parser.parse_args()

    payload = sync_landing_tiktok_collection(
        args.collection_url,
        output_path=args.output,
        headless=not args.headed,
    )
    print(
        f"Wrote {len(payload['videos'])} videos to {args.output} "
        f"from collection {payload.get('collection_id', '(unknown)')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
