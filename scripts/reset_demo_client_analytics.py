"""Reset demo + client analytics tables to zero (vault Demo / Client tabs).

Clears:
  - demo_analytics_event  (demo runs, funnel, client browser/OS/device on demos)
  - demo_lead             (Try Demo name/email leads)
  - user_submissions      (bug reports, feedback, suggestions + client context)

Does NOT touch users, campaigns, keys, or billing.

Usage:
    cd TT_Ran_ShopGen
    python scripts/reset_demo_client_analytics.py --confirm

Production / Cloud SQL:
    SQLALCHEMY_DATABASE_URI=postgresql://... python scripts/reset_demo_client_analytics.py --confirm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

TABLES = (
    "demo_analytics_event",
    "demo_lead",
    "user_submissions",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required: actually truncate analytics tables",
    )
    args = parser.parse_args()
    if not args.confirm:
        print("Refusing to run without --confirm", file=sys.stderr)
        return 1

    from dotenv import load_dotenv

    load_dotenv(_PROJECT_ROOT / "config.env")

    from sqlalchemy import text

    from app import app
    from app.extensions import db

    with app.app_context():
        uri = str(db.engine.url)
        if not uri.startswith("postgresql"):
            print(f"Expected PostgreSQL, got: {uri.split('://')[0]}", file=sys.stderr)
            return 1

        counts_before = {}
        for table in TABLES:
            try:
                counts_before[table] = db.session.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                ).scalar_one()
            except Exception as exc:
                print(f"Skip {table} (missing or inaccessible): {exc}", file=sys.stderr)
                counts_before[table] = None

        print("Before reset:")
        for table, n in counts_before.items():
            print(f"  {table}: {n if n is not None else 'n/a'}")

        for table in TABLES:
            if counts_before.get(table) is None:
                continue
            db.session.execute(
                text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
            )
        db.session.commit()

        print("After reset:")
        for table in TABLES:
            if counts_before.get(table) is None:
                continue
            n = db.session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            print(f"  {table}: {n}")

    print("Demo and client analytics reset complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
