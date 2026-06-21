"""SQLite schema compat for shops.next_restock_day."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.extensions import db
from app.services.schema_compat import (
    _sqlite_column_exists,
    ensure_shop_next_restock_day_column,
)


@pytest.fixture()
def sqlite_app():
    from flask import Flask

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.session.execute(
            text(
                "CREATE TABLE shops ("
                "shop_id INTEGER PRIMARY KEY, "
                "type VARCHAR(100), name VARCHAR(100), campaign_id INTEGER)"
            )
        )
        db.session.commit()
        yield app
        db.session.remove()


def test_ensure_next_restock_day_column_on_sqlite(sqlite_app):
    with sqlite_app.app_context():
        assert not _sqlite_column_exists("shops", "next_restock_day")
        assert ensure_shop_next_restock_day_column() is True
        assert _sqlite_column_exists("shops", "next_restock_day")
        assert ensure_shop_next_restock_day_column() is False
