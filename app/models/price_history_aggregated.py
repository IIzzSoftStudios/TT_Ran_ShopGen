from datetime import datetime

from app.extensions import db


class AggregatedPriceHistory(db.Model):
    """
    Optional aggregated view of long-term price history.

    Stores summary statistics for a (gm_profile_id, shop_id, item_id, period_start, period_type)
    bucket so that very old fine-grained PriceHistory rows can be safely deleted.
    """

    __tablename__ = "price_history_aggregated"

    id = db.Column(db.Integer, primary_key=True)
    gm_profile_id = db.Column(db.Integer, nullable=False, index=True)
    shop_id = db.Column(db.Integer, nullable=False, index=True)
    item_id = db.Column(db.Integer, nullable=False, index=True)

    # Start of the aggregation window (e.g. first day of the month)
    period_start = db.Column(db.DateTime, nullable=False, index=True)

    # e.g. "month" or "week" – kept flexible for future needs
    period_type = db.Column(db.String(16), nullable=False, default="month")

    open_price = db.Column(db.Float, nullable=False)
    high_price = db.Column(db.Float, nullable=False)
    low_price = db.Column(db.Float, nullable=False)
    close_price = db.Column(db.Float, nullable=False)
    avg_price = db.Column(db.Float, nullable=False)

    sample_count = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

