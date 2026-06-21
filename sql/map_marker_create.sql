-- DDL for `map_marker` (matches app.models.MapMarker).
-- Normalized (0.0..1.0) marker positions for cities (world canvas)
-- and shops (city canvas). Safe to re-run with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS map_marker (
    id SERIAL PRIMARY KEY,
    canvas_id INTEGER NOT NULL REFERENCES map_canvas (id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    entity_type VARCHAR(10) NOT NULL,
    city_id INTEGER NULL REFERENCES cities (city_id) ON DELETE CASCADE,
    shop_id INTEGER NULL REFERENCES shops (shop_id) ON DELETE CASCADE,
    x DOUBLE PRECISION NOT NULL,
    y DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_map_marker_canvas_city UNIQUE (canvas_id, city_id),
    CONSTRAINT uq_map_marker_canvas_shop UNIQUE (canvas_id, shop_id),
    CONSTRAINT chk_map_marker_x_bounds CHECK (x >= 0.0 AND x <= 1.0),
    CONSTRAINT chk_map_marker_y_bounds CHECK (y >= 0.0 AND y <= 1.0)
);

CREATE INDEX IF NOT EXISTS ix_map_marker_canvas_id ON map_marker (canvas_id);
CREATE INDEX IF NOT EXISTS ix_map_marker_campaign_id ON map_marker (campaign_id);
CREATE INDEX IF NOT EXISTS ix_map_marker_city_id ON map_marker (city_id);
CREATE INDEX IF NOT EXISTS ix_map_marker_shop_id ON map_marker (shop_id);
