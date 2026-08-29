-- Reset vault Demo analytics + Client analytics source tables.
-- Run only when you need a fresh telemetry start (e.g. after bad/missing UA data).
-- Does NOT delete users, campaigns, registration keys, or billing rows.

TRUNCATE TABLE demo_analytics_event RESTART IDENTITY CASCADE;
TRUNCATE TABLE demo_lead RESTART IDENTITY CASCADE;
TRUNCATE TABLE user_submissions RESTART IDENTITY CASCADE;
