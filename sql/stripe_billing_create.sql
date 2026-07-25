-- Stripe Managed Payments billing + demo lead funnel tables/columns.
-- Safe to re-run (IF NOT EXISTS / WHERE NOT EXISTS patterns).

ALTER TABLE "user" ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);
CREATE UNIQUE INDEX IF NOT EXISTS ix_user_stripe_customer_id
  ON "user"(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

ALTER TABLE registration_key ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);
ALTER TABLE registration_key ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255);
ALTER TABLE registration_key ADD COLUMN IF NOT EXISTS stripe_price_id VARCHAR(255);
ALTER TABLE registration_key ADD COLUMN IF NOT EXISTS stripe_checkout_session_id VARCHAR(255);
CREATE UNIQUE INDEX IF NOT EXISTS ix_registration_key_stripe_checkout_session_id
  ON registration_key(stripe_checkout_session_id)
  WHERE stripe_checkout_session_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS billing_subscription (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES "user"(id) ON DELETE SET NULL,
    stripe_subscription_id VARCHAR(255) NOT NULL UNIQUE,
    stripe_customer_id VARCHAR(255) NOT NULL,
    stripe_price_id VARCHAR(255) NOT NULL,
    plan_slug VARCHAR(40) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'incomplete',
    current_period_end TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS ix_billing_subscription_user_id ON billing_subscription(user_id);
CREATE INDEX IF NOT EXISTS ix_billing_subscription_customer ON billing_subscription(stripe_customer_id);
CREATE INDEX IF NOT EXISTS ix_billing_subscription_plan_status ON billing_subscription(plan_slug, status);

CREATE TABLE IF NOT EXISTS stripe_webhook_event (
    id VARCHAR(255) PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);

CREATE TABLE IF NOT EXISTS demo_lead (
    id SERIAL PRIMARY KEY,
    demo_run_id VARCHAR(36) NOT NULL UNIQUE,
    demo_anon_id VARCHAR(64) NOT NULL,
    contact_name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL,
    last_step_key VARCHAR(64),
    last_step_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS ix_demo_lead_email ON demo_lead(email);
CREATE INDEX IF NOT EXISTS ix_demo_lead_last_step ON demo_lead(last_step_key);
CREATE INDEX IF NOT EXISTS ix_demo_lead_anon ON demo_lead(demo_anon_id);
