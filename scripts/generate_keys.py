#!/usr/bin/env python3
"""
Generate single-use registration keys (FORGE-XXXX-XXXX) and insert into the Vault.
Run from project root: python scripts/generate_keys.py 10
Uses shared app.services.key_generator (confusion-free alphabet).
"""
import argparse
import sys
import os

# Ensure project root is on path when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(
        description="Generate registration keys and insert into database."
    )
    parser.add_argument(
        "count",
        type=int,
        nargs="?",
        default=1,
        help="Number of keys to generate (default: 1)",
    )
    args = parser.parse_args()
    if args.count < 1 or args.count > 1000:
        print("Count must be between 1 and 1000.", file=sys.stderr)
        sys.exit(1)

    from app import create_app
    from app.extensions import db
    from app.services.key_generator import create_bulk_keys

    app = create_app()
    with app.app_context():
        keys_created = create_bulk_keys(args.count)
        db.session.commit()
        for k in keys_created:
            print(k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
