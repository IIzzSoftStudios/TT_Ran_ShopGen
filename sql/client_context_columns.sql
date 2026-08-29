-- Browser / OS / device columns for demo analytics and account-menu submissions.
-- Safe to re-run (IF NOT EXISTS).

ALTER TABLE demo_analytics_event
    ADD COLUMN IF NOT EXISTS client_browser VARCHAR(40),
    ADD COLUMN IF NOT EXISTS client_os VARCHAR(40),
    ADD COLUMN IF NOT EXISTS client_device_type VARCHAR(20);

ALTER TABLE user_submissions
    ADD COLUMN IF NOT EXISTS client_browser VARCHAR(40),
    ADD COLUMN IF NOT EXISTS client_os VARCHAR(40),
    ADD COLUMN IF NOT EXISTS client_device_type VARCHAR(20);
