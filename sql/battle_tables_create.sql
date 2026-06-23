-- DDL for D&D 5e tactical combat tables (matches app.models Battle* /
-- MonsterCompendiumEntry). Safe to re-run with IF NOT EXISTS. Must stay in
-- sync with ensure_battle_tables() in app/services/schema_compat.py.

CREATE TABLE IF NOT EXISTS battle_settings (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_battle_settings_campaign UNIQUE (campaign_id)
);

CREATE INDEX IF NOT EXISTS ix_battle_settings_campaign_id
    ON battle_settings (campaign_id);

CREATE TABLE IF NOT EXISTS monster_compendium_entry (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'custom',
    origin_srd_key VARCHAR(80) NULL,
    generation_seed VARCHAR(64) NULL,
    challenge_rating DOUBLE PRECISION NULL,
    stat_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_monster_compendium_entry_campaign_id
    ON monster_compendium_entry (campaign_id);

CREATE INDEX IF NOT EXISTS ix_monster_compendium_entry_origin_srd_key
    ON monster_compendium_entry (origin_srd_key);

CREATE TABLE IF NOT EXISTS battle_encounter (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    map_canvas_id INTEGER NULL REFERENCES map_canvas (id) ON DELETE SET NULL,
    map_x DOUBLE PRECISION NULL,
    map_y DOUBLE PRECISION NULL,
    name VARCHAR(120) NOT NULL DEFAULT 'Encounter',
    status VARCHAR(16) NOT NULL DEFAULT 'setup',
    visible_to_players BOOLEAN NOT NULL DEFAULT false,
    grid_width INTEGER NOT NULL DEFAULT 20,
    grid_height INTEGER NOT NULL DEFAULT 20,
    round_number INTEGER NOT NULL DEFAULT 0,
    turn_index INTEGER NOT NULL DEFAULT 0,
    turn_version INTEGER NOT NULL DEFAULT 0,
    settings_json JSONB NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_battle_encounter_campaign_id
    ON battle_encounter (campaign_id);

CREATE TABLE IF NOT EXISTS battle_combatant (
    id SERIAL PRIMARY KEY,
    encounter_id INTEGER NOT NULL REFERENCES battle_encounter (id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    player_id INTEGER NULL REFERENCES player (id) ON DELETE SET NULL,
    compendium_entry_id INTEGER NULL REFERENCES monster_compendium_entry (id) ON DELETE SET NULL,
    name VARCHAR(120) NOT NULL,
    side VARCHAR(10) NOT NULL DEFAULT 'foe',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    x INTEGER NOT NULL DEFAULT 0,
    y INTEGER NOT NULL DEFAULT 0,
    hp_max INTEGER NOT NULL DEFAULT 1,
    hp_current INTEGER NOT NULL DEFAULT 1,
    temp_hp INTEGER NOT NULL DEFAULT 0,
    ac INTEGER NOT NULL DEFAULT 10,
    speed_ft INTEGER NOT NULL DEFAULT 30,
    initiative INTEGER NULL,
    initiative_order INTEGER NULL,
    dex_mod INTEGER NOT NULL DEFAULT 0,
    movement_used_ft INTEGER NOT NULL DEFAULT 0,
    has_waited BOOLEAN NOT NULL DEFAULT FALSE,
    ability_json JSONB NULL,
    action_data_json JSONB NULL,
    resources_json JSONB NULL,
    spell_slots_json JSONB NULL,
    conditions_json JSONB NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_battle_combatant_encounter_id
    ON battle_combatant (encounter_id);
CREATE INDEX IF NOT EXISTS ix_battle_combatant_campaign_id
    ON battle_combatant (campaign_id);
CREATE INDEX IF NOT EXISTS ix_battle_combatant_player_id
    ON battle_combatant (player_id);

CREATE TABLE IF NOT EXISTS battle_action_log (
    id SERIAL PRIMARY KEY,
    encounter_id INTEGER NOT NULL REFERENCES battle_encounter (id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    combatant_id INTEGER NULL REFERENCES battle_combatant (id) ON DELETE SET NULL,
    round_number INTEGER NOT NULL DEFAULT 0,
    action_type VARCHAR(30) NOT NULL,
    payload_json JSONB NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_battle_action_log_encounter_id
    ON battle_action_log (encounter_id);
CREATE INDEX IF NOT EXISTS ix_battle_action_log_campaign_id
    ON battle_action_log (campaign_id);
