"""SQLite schema compat for simulation_state.last_market_run."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.extensions import db
from app.services.schema_compat import (
    _sqlite_column_exists,
    ensure_global_market_baseline_stock_column,
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
                "CREATE TABLE simulation_state ("
                "state_id INTEGER PRIMARY KEY, "
                "current_tick INTEGER NOT NULL, "
                "speed VARCHAR(10) NOT NULL, "
                "last_tick_time DATETIME NOT NULL, "
                "campaign_id INTEGER NOT NULL UNIQUE)"
            )
        )
        db.session.commit()
        yield app
        db.session.remove()


def test_ensure_last_market_run_column_on_sqlite(sqlite_app):
    with sqlite_app.app_context():
        assert not _sqlite_column_exists("simulation_state", "last_market_run")
        assert ensure_global_market_baseline_stock_column() is True
        assert _sqlite_column_exists("simulation_state", "last_market_run")
        assert ensure_global_market_baseline_stock_column() is False
