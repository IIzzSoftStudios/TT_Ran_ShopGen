-- Campaign scope migration for generated world/economy tables.
-- Safe rollout plan:
--   1) Add nullable campaign_id columns + indexes + FKs.
--   2) Backfill deterministic rows from existing relationships.
--   3) Remove ambiguous legacy rows that cannot be reliably mapped.
--   4) (Optional hardening) alter campaign_id columns to NOT NULL after app rollout.

BEGIN;

ALTER TABLE cities ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE shops ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE items ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE shop_inventory ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE regional_markets ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE global_markets ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE price_history ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE demand_modifiers ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE modifier_targets ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE resource_transforms ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE market_events ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE simulation_logs ADD COLUMN IF NOT EXISTS campaign_id INTEGER;
ALTER TABLE sim_rules ADD COLUMN IF NOT EXISTS campaign_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_cities_campaign'
    ) THEN
        ALTER TABLE cities
            ADD CONSTRAINT fk_cities_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_shops_campaign'
    ) THEN
        ALTER TABLE shops
            ADD CONSTRAINT fk_shops_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_items_campaign'
    ) THEN
        ALTER TABLE items
            ADD CONSTRAINT fk_items_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_shop_inventory_campaign'
    ) THEN
        ALTER TABLE shop_inventory
            ADD CONSTRAINT fk_shop_inventory_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_regional_markets_campaign'
    ) THEN
        ALTER TABLE regional_markets
            ADD CONSTRAINT fk_regional_markets_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_global_markets_campaign'
    ) THEN
        ALTER TABLE global_markets
            ADD CONSTRAINT fk_global_markets_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_price_history_campaign'
    ) THEN
        ALTER TABLE price_history
            ADD CONSTRAINT fk_price_history_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_demand_modifiers_campaign'
    ) THEN
        ALTER TABLE demand_modifiers
            ADD CONSTRAINT fk_demand_modifiers_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_modifier_targets_campaign'
    ) THEN
        ALTER TABLE modifier_targets
            ADD CONSTRAINT fk_modifier_targets_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_resource_transforms_campaign'
    ) THEN
        ALTER TABLE resource_transforms
            ADD CONSTRAINT fk_resource_transforms_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_market_events_campaign'
    ) THEN
        ALTER TABLE market_events
            ADD CONSTRAINT fk_market_events_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_simulation_logs_campaign'
    ) THEN
        ALTER TABLE simulation_logs
            ADD CONSTRAINT fk_simulation_logs_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_sim_rules_campaign'
    ) THEN
        ALTER TABLE sim_rules
            ADD CONSTRAINT fk_sim_rules_campaign
            FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_cities_campaign_id ON cities(campaign_id);
CREATE INDEX IF NOT EXISTS ix_shops_campaign_id ON shops(campaign_id);
CREATE INDEX IF NOT EXISTS ix_items_campaign_id ON items(campaign_id);
CREATE INDEX IF NOT EXISTS ix_shop_inventory_campaign_id ON shop_inventory(campaign_id);
CREATE INDEX IF NOT EXISTS ix_regional_markets_campaign_id ON regional_markets(campaign_id);
CREATE INDEX IF NOT EXISTS ix_global_markets_campaign_id ON global_markets(campaign_id);
CREATE INDEX IF NOT EXISTS ix_price_history_campaign_id ON price_history(campaign_id);
CREATE INDEX IF NOT EXISTS ix_demand_modifiers_campaign_id ON demand_modifiers(campaign_id);
CREATE INDEX IF NOT EXISTS ix_modifier_targets_campaign_id ON modifier_targets(campaign_id);
CREATE INDEX IF NOT EXISTS ix_resource_transforms_campaign_id ON resource_transforms(campaign_id);
CREATE INDEX IF NOT EXISTS ix_market_events_campaign_id ON market_events(campaign_id);
CREATE INDEX IF NOT EXISTS ix_simulation_logs_campaign_id ON simulation_logs(campaign_id);
CREATE INDEX IF NOT EXISTS ix_sim_rules_campaign_id ON sim_rules(campaign_id);

-- Deterministic backfill: if GM has exactly one campaign, map all null rows to it.
WITH single_campaign AS (
    SELECT gm_profile_id, MIN(id) AS campaign_id
    FROM campaign
    GROUP BY gm_profile_id
    HAVING COUNT(*) = 1
)
UPDATE cities c
SET campaign_id = sc.campaign_id
FROM single_campaign sc
WHERE c.campaign_id IS NULL
  AND c.gm_profile_id = sc.gm_profile_id;

WITH single_campaign AS (
    SELECT gm_profile_id, MIN(id) AS campaign_id
    FROM campaign
    GROUP BY gm_profile_id
    HAVING COUNT(*) = 1
)
UPDATE shops s
SET campaign_id = sc.campaign_id
FROM single_campaign sc
WHERE s.campaign_id IS NULL
  AND s.gm_profile_id = sc.gm_profile_id;

WITH single_campaign AS (
    SELECT gm_profile_id, MIN(id) AS campaign_id
    FROM campaign
    GROUP BY gm_profile_id
    HAVING COUNT(*) = 1
)
UPDATE items i
SET campaign_id = sc.campaign_id
FROM single_campaign sc
WHERE i.campaign_id IS NULL
  AND i.gm_profile_id = sc.gm_profile_id;

-- Fill dependent tables from parent records.
UPDATE shop_inventory si
SET campaign_id = s.campaign_id
FROM shops s
WHERE si.campaign_id IS NULL
  AND si.shop_id = s.shop_id;

UPDATE regional_markets rm
SET campaign_id = c.campaign_id
FROM cities c
WHERE rm.campaign_id IS NULL
  AND rm.city_id = c.city_id;

UPDATE global_markets gm
SET campaign_id = i.campaign_id
FROM items i
WHERE gm.campaign_id IS NULL
  AND gm.item_id = i.item_id;

UPDATE price_history ph
SET campaign_id = s.campaign_id
FROM shops s
WHERE ph.campaign_id IS NULL
  AND ph.shop_id = s.shop_id;

-- Ambiguous leftovers (multi-campaign GMs with legacy shared world rows):
-- remove from campaign-owned tables to avoid bleed into new campaigns.
DELETE FROM shop_inventory WHERE campaign_id IS NULL;
DELETE FROM regional_markets WHERE campaign_id IS NULL;
DELETE FROM global_markets WHERE campaign_id IS NULL;
DELETE FROM price_history WHERE campaign_id IS NULL;
DELETE FROM cities WHERE campaign_id IS NULL;
DELETE FROM shops WHERE campaign_id IS NULL;
DELETE FROM items WHERE campaign_id IS NULL;

COMMIT;
