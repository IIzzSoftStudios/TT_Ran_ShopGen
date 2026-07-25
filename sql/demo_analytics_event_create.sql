CREATE TABLE IF NOT EXISTS demo_analytics_event (
    id SERIAL PRIMARY KEY,
    demo_run_id VARCHAR(36) NOT NULL,
    demo_anon_id VARCHAR(64) NOT NULL,
    user_id INTEGER REFERENCES "user"(id) ON DELETE SET NULL,
    event_type VARCHAR(32) NOT NULL,
    step_key VARCHAR(64),
    surface VARCHAR(40) NOT NULL DEFAULT 'gm_tutorial',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE INDEX IF NOT EXISTS ix_demo_analytics_event_demo_run_id
    ON demo_analytics_event(demo_run_id);

CREATE INDEX IF NOT EXISTS ix_demo_analytics_event_demo_anon_id
    ON demo_analytics_event(demo_anon_id);

CREATE INDEX IF NOT EXISTS ix_demo_analytics_event_user_id
    ON demo_analytics_event(user_id);

CREATE INDEX IF NOT EXISTS ix_demo_analytics_event_created_at
    ON demo_analytics_event(created_at);

CREATE INDEX IF NOT EXISTS ix_demo_analytics_event_type_created
    ON demo_analytics_event(event_type, created_at);

CREATE INDEX IF NOT EXISTS ix_demo_analytics_run_type
    ON demo_analytics_event(demo_run_id, event_type);

CREATE INDEX IF NOT EXISTS ix_demo_analytics_step_type
    ON demo_analytics_event(step_key, event_type);
