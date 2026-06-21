-- Columns for app.models.Item (world generator + stat blocks).
-- Safe to re-run: uses IF NOT EXISTS per column where supported.

ALTER TABLE items ADD COLUMN IF NOT EXISTS stats JSONB NULL;
ALTER TABLE items ADD COLUMN IF NOT EXISTS axis_position INTEGER NULL;

CREATE INDEX IF NOT EXISTS ix_items_axis_position ON items (axis_position);
CREATE INDEX IF NOT EXISTS ix_item_gm_axis ON items (gm_profile_id, axis_position);
