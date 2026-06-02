# Econo-Forge Roadmap

This roadmap captures the next practical improvements for Econo-Forge based on the current app surface, simulation backend, tests, and deployment workflow. It is ordered to improve the demo and onboarding experience first, then harden production-critical systems.

## Guiding Priorities

- Make the first user journey coherent: landing page, access request, registration, login, campaign setup, and first simulation run should feel like one product.
- Protect the simulation path: keep tick work fast, observable, and transactionally safe.
- Reduce production surprises: document runtime configuration, test Redis-dependent behavior, and verify web/worker deployment parity.
- Avoid expanding new features on top of unclear state authority, especially where row-based simulation state and `GMWorldState` can diverge.

## Phase 1: Product Polish And First-Run Experience

Goal: make the app easier to understand and more credible for a new GM or player.

Recommended work:

- Align onboarding copy in `app/templates/docs.html` with the live access flow in `app/routes/main_routes.py`, where access requests are auto-approved and redirect to registration.
- Restyle `app/templates/register.html`, `app/templates/login.html`, and `app/templates/forgot_password.html` with the same theme tokens used by the landing and access-request pages.
- Add a GM first-run checklist to `app/templates/GM_Home.html` for empty campaigns, with links to world generation, player setup, join codes, and the first simulation run.
- Update `app/templates/Player_Home.html` and `app/templates/partials/player_join_code_reveal.html` to remove hardcoded light-mode colors.
- Add basic SEO and social sharing metadata to `app/templates/landing.html`, plus a video poster fallback for the hero media.

Acceptance checks:

- A new user can follow landing page -> access request -> registration -> login without contradictory copy.
- Auth and player pages remain readable in light and dark themes.
- A GM with an empty campaign sees a clear next action instead of simulation controls only.

## Phase 2: Branding And Content Consistency

Goal: remove visible drift between older TT Shop Gen surfaces and the current Econo-Forge product.

Recommended work:

- Decide whether `app/templates/docs.html` is the canonical changelog source, then retire or redirect duplicate content in `app/templates/changelog.html`.
- Restyle or remove legacy player templates that still inherit old branding from `app/templates/base.html`.
- Rework the unused `thank_you.html` path or remove it from the access-request story. If kept, use it for Discord/ruleset onboarding before registration.
- Update root documentation references that still use the old project name where user-facing branding should say Econo-Forge.

Acceptance checks:

- No primary player or GM route shows outdated "TT RPG Market" branding.
- Changelog entries have one source of truth.
- Access-request admin screens and public onboarding copy describe the same approval model.

## Phase 3: Simulation Performance And State Safety

Goal: make the tick path more predictable before adding larger economy or state features.

Recommended work:

- Preload active demand modifiers once per tick in `app/services/economy/demand.py` instead of querying inside every inventory/city pricing calculation.
- Pass precomputed demand context into `app/services/simulation.py` while preserving the existing single-commit and rollback behavior.
- Add focused tests that make `tick_duration` visible against the documented 33ms budget.
- Decide whether row-based state or `GMWorldState.state_json` is the player-facing price authority before enabling `READ_PRICES_FROM_WORLD_STATE`.
- Add reconciliation tests around `app/services/world_state_reads.py` before any state-read flag is enabled in production.

Acceptance checks:

- Tick behavior remains atomic: no extra commits inside pricing loops and rollback still protects failed ticks.
- Demand modifier loading does not create per-item/per-city query churn.
- State authority is documented before new read paths are enabled.

## Phase 4: Reliability, Tests, And CI

Goal: catch production-critical regressions before deployment.

Recommended work:

- Add `/ready` tests for `app/routes/main_routes.py`, including Redis and database failure cases.
- Add ownership, refresh, and release tests for `app/services/distributed_lock.py`.
- Extend smoke coverage in `tests/test_smoke.py` beyond `/healthz`.
- Add a PR-time test gate through GitHub Actions or a Cloud Build trigger so pytest runs before deploy-branch promotion.
- Consider coverage and lint gates after Redis/readiness coverage is in place.

Acceptance checks:

- Redis-dependent readiness and lock behavior are covered by tests.
- Feature branches get test feedback before deployment.
- Simulation metrics and lock failures cannot silently regress without test coverage.

## Phase 5: Deployment And Runtime Configuration

Goal: keep local examples, Cloud Run, workers, and deploy docs aligned.

Recommended work:

- Document runtime knobs in `config.example.env`, including `REQUIRE_REGISTRATION_KEY`, `WORLD_STATE_ENABLED`, `READ_PRICES_FROM_WORLD_STATE`, `METRICS_DURATIONS_CAP`, `METRICS_TERMINAL_TTL_SECONDS`, `SIM_TICK_DEBUG_ASSERTS`, and `TRSG_CLOUD_RUN_MIGRATE`.
- Add a worker image digest parity check or explicit runbook step tied to `cloudbuild.yaml` and `deploy/README.md`.
- Wire `docker-compose.prodlike.yml` into a release smoke path when practical.
- Export or surface simulation timing metrics beyond Redis-only keys, especially for `tick_duration`.

Acceptance checks:

- Every runtime env var used by app/deploy code is documented with its expected environment.
- Web and worker images can be verified against the same digest after deployment.
- Prodlike smoke catches bootstrap or readiness issues that SQLite-only tests miss.

## Suggested Implementation Order

1. Onboarding copy and auth-page theming.
2. GM first-run checklist.
3. Player dark-mode and legacy branding cleanup.
4. Redis readiness and lock tests.
5. Config documentation and deploy parity checks.
6. Demand modifier preloading and tick performance tests.
7. State-authority decision for `GMWorldState` reads.
8. PR-time CI, coverage, and lint gates.

## Deferred Ideas

- Paid-tier billing integration beyond YAML phase entitlements.
- Full model/module splitting for `models.py` and large route modules.
- Admin metrics dashboards for simulation jobs and tick timing.
- Larger world-state migration after state authority is decided.
