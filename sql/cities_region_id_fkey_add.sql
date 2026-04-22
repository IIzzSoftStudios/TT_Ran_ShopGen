-- FK from cities.region_id -> region(id). Run after `region` exists and
-- `cities.region_id` column exists (see cities_add_region_id.sql).

ALTER TABLE cities DROP CONSTRAINT IF EXISTS cities_region_id_fkey;

ALTER TABLE cities
    ADD CONSTRAINT cities_region_id_fkey
    FOREIGN KEY (region_id) REFERENCES region (id) ON DELETE SET NULL;
