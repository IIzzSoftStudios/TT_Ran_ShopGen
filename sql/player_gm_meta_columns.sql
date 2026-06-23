-- GM-only NPC notes and player-visible NPC flag
ALTER TABLE player ADD COLUMN IF NOT EXISTS gm_notes TEXT;
ALTER TABLE player ADD COLUMN IF NOT EXISTS known_to_players BOOLEAN NOT NULL DEFAULT false;

-- City and shop owner NPC references
ALTER TABLE cities ADD COLUMN IF NOT EXISTS owner_player_id INTEGER;
ALTER TABLE shops ADD COLUMN IF NOT EXISTS owner_player_id INTEGER;
