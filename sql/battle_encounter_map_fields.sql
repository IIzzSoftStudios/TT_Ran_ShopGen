-- Per-encounter tactical battle map metadata (upload + procedural generation).
-- Safe to run multiple times on PostgreSQL.

ALTER TABLE battle_encounter ADD COLUMN IF NOT EXISTS map_source_type VARCHAR(16) NOT NULL DEFAULT 'none';
ALTER TABLE battle_encounter ADD COLUMN IF NOT EXISTS map_asset_key VARCHAR(255) NULL;
ALTER TABLE battle_encounter ADD COLUMN IF NOT EXISTS terrain_preset VARCHAR(32) NULL;
ALTER TABLE battle_encounter ADD COLUMN IF NOT EXISTS terrain_seed INTEGER NULL;
ALTER TABLE battle_encounter ADD COLUMN IF NOT EXISTS terrain_metadata JSONB NULL;
ALTER TABLE battle_encounter ADD COLUMN IF NOT EXISTS map_version INTEGER NOT NULL DEFAULT 0;
