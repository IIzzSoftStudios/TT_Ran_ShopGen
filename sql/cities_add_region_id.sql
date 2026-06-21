-- Add column expected by app.models.City (player/GM queries select region_id).
--
-- If `region` already exists, use the FK form instead of the plain INTEGER below:
--   ALTER TABLE cities ADD COLUMN IF NOT EXISTS region_id INTEGER
--       REFERENCES region (id) ON DELETE SET NULL;
--
-- Legacy DBs sometimes have `cities` but no `region` table yet: plain INTEGER + index
-- unblocks the app; add FK after `region` is created:
--   ALTER TABLE cities DROP CONSTRAINT IF EXISTS cities_region_id_fkey;
--   ALTER TABLE cities ADD CONSTRAINT cities_region_id_fkey
--       FOREIGN KEY (region_id) REFERENCES region (id) ON DELETE SET NULL;

ALTER TABLE cities
    ADD COLUMN IF NOT EXISTS region_id INTEGER;

CREATE INDEX IF NOT EXISTS ix_cities_region_id
    ON cities (region_id);
