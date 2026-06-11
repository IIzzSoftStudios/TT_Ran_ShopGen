-- DDL for `map_point_of_interest` (matches app.models.MapPointOfInterest).
-- GM-authored labeled/note POIs on world map canvases.
-- Safe to re-run with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS map_point_of_interest (
    id SERIAL PRIMARY KEY,
    canvas_id INTEGER NOT NULL REFERENCES map_canvas (id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    label VARCHAR(120) NOT NULL,
    note TEXT NULL,
    x DOUBLE PRECISION NOT NULL,
    y DOUBLE PRECISION NOT NULL,
    visible_to_players BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT chk_map_poi_x_bounds CHECK (x >= 0.0 AND x <= 1.0),
    CONSTRAINT chk_map_poi_y_bounds CHECK (y >= 0.0 AND y <= 1.0)
);

CREATE INDEX IF NOT EXISTS ix_map_point_of_interest_canvas_id ON map_point_of_interest (canvas_id);
CREATE INDEX IF NOT EXISTS ix_map_point_of_interest_campaign_id ON map_point_of_interest (campaign_id);
