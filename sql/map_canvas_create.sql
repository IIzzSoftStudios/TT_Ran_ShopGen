-- DDL for `map_canvas` (matches app.models.MapCanvas).
-- Campaign-scoped GM map backgrounds (world map or one city map).
-- Safe to re-run with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS map_canvas (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    city_id INTEGER NULL REFERENCES cities (city_id) ON DELETE CASCADE,
    scope VARCHAR(10) NOT NULL DEFAULT 'world',
    source_type VARCHAR(20) NOT NULL DEFAULT 'generated',
    image_path VARCHAR(255) NULL,
    underlay_path VARCHAR(255) NULL,
    generation_json JSONB NULL,
    width INTEGER NOT NULL DEFAULT 1024,
    height INTEGER NOT NULL DEFAULT 1024,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_map_canvas_city UNIQUE (campaign_id, city_id)
);

CREATE INDEX IF NOT EXISTS ix_map_canvas_campaign_id ON map_canvas (campaign_id);
CREATE INDEX IF NOT EXISTS ix_map_canvas_city_id ON map_canvas (city_id);

-- One world canvas per campaign (partial index over world-scope rows only;
-- city canvases all share scope='city' so a plain (campaign_id, scope)
-- unique constraint would be wrong).
CREATE UNIQUE INDEX IF NOT EXISTS uq_map_canvas_world
    ON map_canvas (campaign_id)
    WHERE scope = 'world';
