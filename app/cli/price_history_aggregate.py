from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models.backend import PriceHistory
from app.models.price_history_aggregated import AggregatedPriceHistory
from app.config.price_history_config import default_price_history_retention


def aggregate_old_price_history() -> int:
    """
    Aggregate very old PriceHistory rows into coarse buckets so they can be deleted later.

    This is optional; for now it demonstrates a path to long-term trend preservation.
    Returns the number of aggregated groups created/updated in this run.
    """
    cfg = default_price_history_retention
    now = datetime.utcnow()
    cutoff = now - cfg.retention_timedelta

    # For simplicity, aggregate everything older than the cutoff into one-month buckets.
    # This is intentionally conservative and can be refined later.

    # NOTE: This implementation is intentionally simple and expected to run over
    # a limited amount of already-aged data in a maintenance window.
    session = db.session

    # Use raw SQL or ORM grouping; ORM shown here for clarity even if not the most efficient.
    # The expectation is that this job runs infrequently and over limited data.
    rows = (
        session.query(
            PriceHistory.gm_profile_id,
            PriceHistory.shop_id,
            PriceHistory.item_id,
            db.func.date_trunc("month", PriceHistory.recorded_at).label("period_start"),
            db.func.min(PriceHistory.price).label("low_price"),
            db.func.max(PriceHistory.price).label("high_price"),
            db.func.avg(PriceHistory.price).label("avg_price"),
            db.func.count(PriceHistory.id).label("sample_count"),
        )
        .filter(PriceHistory.recorded_at < cutoff)
        .group_by(
            PriceHistory.gm_profile_id,
            PriceHistory.shop_id,
            PriceHistory.item_id,
            db.func.date_trunc("month", PriceHistory.recorded_at),
        )
        .all()
    )

    aggregated_groups = 0

    for row in rows:
        # Compute the start and end of the month for this aggregation bucket.
        period_start = row.period_start
        year = period_start.year
        month = period_start.month
        if month == 12:
            period_end = datetime(year + 1, 1, 1, tzinfo=period_start.tzinfo)
        else:
            period_end = datetime(year, month + 1, 1, tzinfo=period_start.tzinfo)

        # For open/close prices, we want the first and last sample *within this month*,
        # not the absolute first/last sample across all months.
        first_sample = (
            session.query(PriceHistory)
            .filter(
                PriceHistory.gm_profile_id == row.gm_profile_id,
                PriceHistory.shop_id == row.shop_id,
                PriceHistory.item_id == row.item_id,
                PriceHistory.recorded_at >= period_start,
                PriceHistory.recorded_at < period_end,
                PriceHistory.recorded_at < cutoff,
            )
            .order_by(PriceHistory.recorded_at.asc())
            .first()
        )
        last_sample = (
            session.query(PriceHistory)
            .filter(
                PriceHistory.gm_profile_id == row.gm_profile_id,
                PriceHistory.shop_id == row.shop_id,
                PriceHistory.item_id == row.item_id,
                PriceHistory.recorded_at >= period_start,
                PriceHistory.recorded_at < period_end,
                PriceHistory.recorded_at < cutoff,
            )
            .order_by(PriceHistory.recorded_at.desc())
            .first()
        )

        if not first_sample or not last_sample:
            continue

        aggregated = AggregatedPriceHistory(
            gm_profile_id=row.gm_profile_id,
            shop_id=row.shop_id,
            item_id=row.item_id,
            period_start=period_start,
            period_type="month",
            open_price=first_sample.price,
            high_price=row.high_price,
            low_price=row.low_price,
            close_price=last_sample.price,
            avg_price=row.avg_price,
            sample_count=row.sample_count,
        )
        session.add(aggregated)
        aggregated_groups += 1

    session.commit()

    current_app.logger.info(
        "Aggregated old PriceHistory into monthly buckets",
        extra={"groups_created": aggregated_groups},
    )

    return aggregated_groups

