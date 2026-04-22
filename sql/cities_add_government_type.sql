-- Add column expected by app.models.City (world generator + GM dashboard).
-- Safe to run on existing DBs: IF NOT EXISTS.

ALTER TABLE cities
    ADD COLUMN IF NOT EXISTS government_type VARCHAR(50);

CREATE INDEX IF NOT EXISTS ix_cities_government_type
    ON cities (government_type);
