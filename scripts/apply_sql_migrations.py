"""Apply Postgres DDL in sql/migrations in sorted filename order.

Usage (Compose Postgres after base schema exists):
    SQLALCHEMY_DATABASE_URI=postgresql://trsg_user:trsg_pass@localhost:5432/trsg_db \\
        python scripts/apply_sql_migrations.py

Staging / Cloud SQL: same command with the instance connection string.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> int:
    uri = os.getenv("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("postgresql"):
        sys.stderr.write("SQLALCHEMY_DATABASE_URI must be a postgresql URL\n")
        return 1

    mig_dir = _PROJECT_ROOT / "sql" / "migrations"
    files = sorted(mig_dir.glob("*.sql"))
    if not files:
        sys.stderr.write(f"No .sql files in {mig_dir}\n")
        return 1

    from sqlalchemy import create_engine, text

    engine = create_engine(uri)
    with engine.connect() as conn:
        for path in files:
            stmt = path.read_text(encoding="utf-8")
            conn.execute(text(stmt))
            conn.commit()
            print("applied", path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
