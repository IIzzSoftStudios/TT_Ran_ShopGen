-- DDL for `region` (matches app.models.Region).
-- Requires `campaign` and `gm_profile`. Safe to re-run with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS region (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    gm_profile_id INTEGER NOT NULL REFERENCES gm_profile (id),
    local_flavor JSONB NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_region_campaign_name UNIQUE (campaign_id, name)
);

CREATE INDEX IF NOT EXISTS ix_region_name ON region (name);
CREATE INDEX IF NOT EXISTS ix_region_campaign_id ON region (campaign_id);
CREATE INDEX IF NOT EXISTS ix_region_gm_profile_id ON region (gm_profile_id);
