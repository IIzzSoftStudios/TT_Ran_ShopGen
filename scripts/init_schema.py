"""One-shot ORM-driven schema bootstrap.

Imports the configured Flask app from `app/__init__.py` (which registers all
ORM models and the `db` extension), then calls `db.create_all()` against the
configured database.

Idempotent: `create_all()` no-ops on already-existing tables, so re-running
is safe. This is the bridge until an Alembic baseline lands (deferred to
"before alpha" per the GCP deployment plan).

Usage (local compose):
    docker compose run --rm web python scripts/init_schema.py

Usage (Cloud SQL via Auth Proxy or direct connection):
    SQLALCHEMY_DATABASE_URI=postgresql+psycopg2://USER:PWD@HOST:5432/DB \
        python scripts/init_schema.py

The app factory in `app/__init__.py` requires SECRET_KEY in production. Set
FLASK_ENV=development (or supply SECRET_KEY) when running this script.

Cloud Build migrate job sets ``TRSG_CLOUD_RUN_MIGRATE=true`` so production
startup skips Redis (filesystem sessions) and does not require ``REDIS_URL``.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Allow running as `python scripts/init_schema.py` from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger("init_schema")

    if not os.getenv("SQLALCHEMY_DATABASE_URI"):
        sys.stderr.write("SQLALCHEMY_DATABASE_URI is required\n")
        return 1

    # Importing `app` runs the factory; compatibility bootstraps tolerate partial schema.
    from app import app as flask_app
    from app.extensions import db
    from sqlalchemy import inspect

    with flask_app.app_context():
        engine = db.engine
        expected = sorted(t.name for t in db.metadata.sorted_tables)
        logger.info(
            "creating %d ORM tables against %s",
            len(expected),
            engine.url.render_as_string(hide_password=True),
        )
        db.create_all()

        actual = sorted(inspect(engine).get_table_names())
        logger.info("schema bootstrap complete; %d tables present in DB", len(actual))
        missing = sorted(set(expected) - set(actual))
        if missing:
            logger.error("expected tables missing after create_all: %s", missing)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
