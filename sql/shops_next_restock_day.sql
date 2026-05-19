-- Per-shop periodic restock schedule (game day index).
ALTER TABLE shops ADD COLUMN IF NOT EXISTS next_restock_day INTEGER;
