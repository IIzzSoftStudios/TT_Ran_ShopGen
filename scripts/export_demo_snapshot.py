"""Export a campaign to the immutable Demo snapshot JSON.

Usage (from TT_Ran_ShopGen/):
  python scripts/export_demo_snapshot.py --campaign-id 121
  python scripts/export_demo_snapshot.py --campaign-id 121 --out app/data/demo_snapshots/demo_template_v1.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app as flask_app
from app.services.demo_snapshot import (
    default_snapshot_path,
    export_campaign_snapshot,
    write_snapshot_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Demo template snapshot")
    parser.add_argument("--campaign-id", type=int, required=True)
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output path (default: app/data/demo_snapshots/demo_template_v1.json)",
    )
    args = parser.parse_args()
    out = Path(args.out) if args.out else default_snapshot_path()
    if not out.is_absolute():
        out = ROOT / out

    with flask_app.app_context():
        snapshot = export_campaign_snapshot(args.campaign_id)
        write_snapshot_file(snapshot, out)
        print(
            f"Wrote snapshot schema={snapshot.get('schema_version')} "
            f"regions={len(snapshot.get('regions') or [])} "
            f"cities={len(snapshot.get('cities') or [])} "
            f"shops={len(snapshot.get('shops') or [])} "
            f"canvases={len(snapshot.get('map_canvases') or [])} "
            f"-> {out}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
