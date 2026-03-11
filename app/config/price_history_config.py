from dataclasses import dataclass
from datetime import timedelta


@dataclass
class PriceHistoryRetentionConfig:
    """
    Configuration for PriceHistory retention and cleanup behaviour.

    retention_years: number of years of fine-grained history to keep.
    delete_batch_size: max rows to delete per batch in a cleanup run.
    max_batches_per_run: safety cap on number of batches in a single run.
    """

    retention_years: int = 2
    delete_batch_size: int = 10_000
    max_batches_per_run: int = 50

    @property
    def retention_timedelta(self) -> timedelta:
        """Approximate retention window as a timedelta."""
        # Use 365 days/year for simplicity; precision is not critical here.
        return timedelta(days=365 * self.retention_years)


default_price_history_retention = PriceHistoryRetentionConfig()

