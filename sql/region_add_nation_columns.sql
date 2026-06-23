-- Nation (region) display colors and ruler NPC link.
ALTER TABLE region ADD COLUMN IF NOT EXISTS main_color VARCHAR(7);
ALTER TABLE region ADD COLUMN IF NOT EXISTS secondary_color VARCHAR(7);
ALTER TABLE region ADD COLUMN IF NOT EXISTS ruler_player_id INTEGER REFERENCES player(id) ON DELETE SET NULL;
