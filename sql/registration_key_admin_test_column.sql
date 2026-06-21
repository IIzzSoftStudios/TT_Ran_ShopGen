-- Required before using admin test keys: adds is_admin_test_key to registration_key.
-- Run once. If this column is missing while the model expects it, the vault page will error.

-- PostgreSQL:
ALTER TABLE registration_key ADD COLUMN IF NOT EXISTS is_admin_test_key BOOLEAN NOT NULL DEFAULT FALSE;

-- SQLite (run only if the column does not exist; omit IF NOT EXISTS on older SQLite):
-- ALTER TABLE registration_key ADD COLUMN is_admin_test_key BOOLEAN NOT NULL DEFAULT 0;
