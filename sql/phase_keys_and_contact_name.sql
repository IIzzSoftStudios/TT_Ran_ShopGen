-- Phase-based registration keys + access request display name.
-- Run once against PostgreSQL (adjust for SQLite if needed).
-- If a column already exists, skip that statement or use a migration tool.

-- --- registration_key.key_phase ---
ALTER TABLE registration_key ADD COLUMN key_phase VARCHAR(40);

UPDATE registration_key SET key_phase = 'test' WHERE is_admin_test_key IS TRUE;

-- Treat NULL is_admin_test_key as non-admin (legacy rows); plain `= false` misses those.
UPDATE registration_key SET key_phase = 'forge_master'
WHERE COALESCE(is_admin_test_key, false) = false;

-- Any row still NULL (unexpected states) must be cleared before NOT NULL.
UPDATE registration_key SET key_phase = 'default' WHERE key_phase IS NULL;

ALTER TABLE registration_key ALTER COLUMN key_phase SET NOT NULL;
ALTER TABLE registration_key ALTER COLUMN key_phase SET DEFAULT 'default';

-- --- access_requests.contact_name ---
ALTER TABLE access_requests ADD COLUMN contact_name VARCHAR(120);

UPDATE access_requests SET contact_name = 'Unknown' WHERE contact_name IS NULL OR trim(contact_name) = '';

ALTER TABLE access_requests ALTER COLUMN contact_name SET NOT NULL;
ALTER TABLE access_requests ALTER COLUMN contact_name SET DEFAULT '';
