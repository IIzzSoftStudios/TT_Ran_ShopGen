CREATE TABLE IF NOT EXISTS expansion_interest (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    gm_profile_id INTEGER REFERENCES gm_profile(id) ON DELETE SET NULL,
    intent VARCHAR(64) NOT NULL DEFAULT 'campaign_limit_upgrade',
    source VARCHAR(80),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS idx_expansion_interest_user_created
    ON expansion_interest(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_expansion_interest_gm_created
    ON expansion_interest(gm_profile_id, created_at DESC);
