-- Password reuse policy (forgot/reset and future change-password flows).
-- Idempotent: safe to re-run. Prefer running via scripts/apply_sql_migrations.py in prod.

CREATE TABLE IF NOT EXISTS user_password_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    password_hash VARCHAR(128) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_uph_user_id ON user_password_history (user_id);
CREATE INDEX IF NOT EXISTS ix_uph_user_created ON user_password_history (user_id, created_at);
