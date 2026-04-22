-- DDL for `resource_nodes` (matches app.models.ResourceNode).
-- Requires `cities`, `player`, and `gm_profile`. Safe to re-run with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS resource_nodes (
    node_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    production_rate DOUBLE PRECISION NOT NULL,
    quality DOUBLE PRECISION NOT NULL,
    city_id INTEGER NOT NULL REFERENCES cities (city_id),
    owner_id INTEGER NULL REFERENCES player (id),
    gm_profile_id INTEGER NOT NULL REFERENCES gm_profile (id)
);
