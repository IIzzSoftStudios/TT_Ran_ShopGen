-- DDL for `campaign_world_config` (matches app.models.CampaignWorldConfig).
-- Run when the table does not exist; safe to re-run with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS campaign_world_config (
    campaign_id INTEGER NOT NULL PRIMARY KEY REFERENCES campaign (id) ON DELETE CASCADE,
    settings_json JSONB NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    world_seed BIGINT NULL,
    generated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);
