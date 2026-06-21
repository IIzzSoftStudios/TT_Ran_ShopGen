-- GM-only NPC roster: Player rows with no User, flagged is_npc.
-- Safe to run once on PostgreSQL.

ALTER TABLE player ADD COLUMN IF NOT EXISTS is_npc BOOLEAN NOT NULL DEFAULT false;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'player' AND column_name = 'user_id_player'
  ) THEN
    ALTER TABLE player ALTER COLUMN user_id_player DROP NOT NULL;
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'player' AND column_name = 'user_id_gm'
  ) THEN
    ALTER TABLE player ALTER COLUMN user_id_gm DROP NOT NULL;
  END IF;
END $$;
