-- Reference DDL for `price_history` when bootstrapping a database that already has
-- `shops`, `items`, and `gm_profile`. PK column is `id` (matches app.models.PriceHistory).
--
-- Run manually only when the table does not exist; adjust names if your schema differs.

CREATE TABLE IF NOT EXISTS price_history (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops (shop_id),
    item_id INTEGER NOT NULL REFERENCES items (item_id),
    price DOUBLE PRECISION NOT NULL,
    recorded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    gm_profile_id INTEGER NOT NULL REFERENCES gm_profile (id)
);

CREATE INDEX IF NOT EXISTS ix_price_history_gm_profile
    ON price_history (gm_profile_id);
