from datetime import datetime
from time import perf_counter

from flask import current_app

from app.extensions import db
from app.models.backend import PriceHistory
from app.config.price_history_config import default_price_history_retention


def cleanup_price_history() -> int:
    """
    Delete old PriceHistory rows in small batches based on the configured retention window.

    Returns the total number of rows deleted in this run.
    """
    cfg = default_price_history_retention
    now = datetime.utcnow()
    cutoff = now - cfg.retention_timedelta

    total_deleted = 0
    started_at = perf_counter()

    # Perform batched deletes to avoid long-running transactions and big locks.
    # The surrounding Flask CLI command is already decorated with @with_appcontext,
    # so we reuse that single application context and database session here.
    for _ in range(cfg.max_batches_per_run):
        deleted = (
            db.session.query(PriceHistory)
            .filter(PriceHistory.recorded_at < cutoff)
            .order_by(PriceHistory.recorded_at)
            .limit(cfg.delete_batch_size)
            .delete(synchronize_session=False)
        )

        if not deleted:
            db.session.rollback()
            break

        total_deleted += deleted
        db.session.commit()

    duration = perf_counter() - started_at
    current_app.logger.info(
        "PriceHistory cleanup run completed",
        extra={
            "deleted_rows": total_deleted,
            "cutoff": cutoff.isoformat(),
            "duration_seconds": round(duration, 3),
        },
    )

    return total_deleted

