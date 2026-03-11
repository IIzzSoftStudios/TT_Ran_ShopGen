from datetime import datetime

from app.extensions import db
from app.models.backend import PriceHistory


def count_price_history_older_than(cutoff: datetime) -> int:
    """Return how many PriceHistory rows are older than the given cutoff."""
    return db.session.query(PriceHistory).filter(PriceHistory.recorded_at < cutoff).count()


def count_price_history_total() -> int:
    """Return total number of PriceHistory rows."""
    return db.session.query(PriceHistory).count()

