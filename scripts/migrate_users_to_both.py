"""Migrate legacy GM/Player accounts to unified role Both + GMProfile backfill."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models import User
from app.services.user_capabilities import ensure_gm_profile


def run_migration() -> int:
    app = create_app()
    with app.app_context():
        print("Starting user migration to unified account model...")
        target_users = User.query.filter(User.role.in_(["GM", "Player"])).all()
        total = 0
        for user in target_users:
            try:
                print(f"  User {user.id} ({user.username}): {user.role} -> Both")
                user.role = "Both"
                ensure_gm_profile(user)
                total += 1
            except Exception as exc:
                print(f"CRITICAL: failed user {user.id}: {exc}")
                db.session.rollback()
                raise
        db.session.commit()
        print(f"Migration complete. Updated {total} user(s).")
        return total


if __name__ == "__main__":
    run_migration()
