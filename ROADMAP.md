# Econo-Forge Roadmap

This roadmap captures the next practical improvements for Econo-Forge based on the current app surface, tech-demo usage, simulation backend, tests, and deployment workflow. Phase 1 product polish is complete; the remaining work now shifts from activation clarity to branding consistency, simulation safety, reliability coverage, and deployment alignment.

## Guiding Priorities

- Make the first user journey coherent: landing page, access request, registration, login, campaign setup, and first simulation run should feel like one product.
- Raise activation from the current demo baseline: 29 registered users, 10 key activations, 7 campaigns created, and 3 users who ran simulations.
- Protect the simulation path: keep tick work fast, observable, and transactionally safe.
- Reduce production surprises: document runtime configuration, test Redis-dependent behavior, and verify web/worker deployment parity.
- Avoid expanding new features on top of unclear state authority, especially where row-based simulation state and `GMWorldState` can diverge.
- Deploy-branch Cloud Build already runs pytest in the promoted image; the remaining quality gaps are Redis `/ready`, lock semantics, PR/feature-branch feedback, and prodlike smoke coverage.

## Tech Demo Funnel Snapshot

Reported after about one month in tech demo:

- Total registered users: 29
- Used registration key: 10 of 29, about 34%
- GMs who created a campaign: 7 of 10 activated users, about 70%
- Users who ran simulations: 3 of 7 campaign creators, about 43%
- End-to-end activation to simulation: 3 of 29, about 10%

Product implication: the biggest leak was key activation, followed by the jump from campaign creation to first simulation. Phase 1 addressed the clearest funnel and first-run gaps; future roadmap work should measure whether activation improves before adding broad new feature surface.

## Phase 1: Product Polish And First-Run Experience

Status: completed.

Goal: make the app easier to understand and more credible for a new GM or player.

Completed work:

- [Done] Aligned public docs, access-request, login, and registration copy around the immediate auto-issued registration key flow.
- [Done] Restyled `app/templates/register.html`, `app/templates/login.html`, `app/templates/forgot_password.html`, and `app/templates/reset_password.html` through shared auth theme tokens and framing.
- [Done] Refined the GM first-run checklist in `app/templates/GM_Home.html` and `app/templates/partials/gm_onboarding_checklist.html` with world generation, player setup, join-code readiness, and first market day guidance.
- [Done] Added the "Run your first market day" prompt before advanced simulation controls for campaign creators who have not simulated.
- [Done] Tokenized player dashboard and join-code surfaces in `app/templates/Player_Home.html` and kept `app/templates/partials/player_join_code_reveal.html` readable against existing theme tokens.
- [Done] Added landing page viewport, canonical, Open Graph, Twitter, theme-color, hero poster, and video fallback metadata in `app/templates/landing.html`.
- [Done] Added a public roadmap docs section and pointed the landing footer Roadmap link to it.
- [Done] Added focused regression coverage for access-request auto-key behavior, docs roadmap routing, landing/link surfaces, and GM onboarding context.

Acceptance checks:

- A new user can follow landing page -> access request -> registration -> login without contradictory copy.
- Auth and player pages remain readable in light and dark themes.
- A GM with an empty campaign sees a clear next action instead of simulation controls only.
- Campaign creators who have not simulated see one obvious first-simulation action.

## Phase 2: Branding And Content Consistency

Status: completed.

Goal: remove visible drift between older TT Shop Gen surfaces and the current Econo-Forge product.

Completed work:

- [Done] Canonical changelog lives in `app/templates/docs.html#changelog`; `/changelog` redirects there. Standalone `changelog.html` was already absent.
- [Done] Retired legacy player list/market routes (`/player/shops`, `/player/cities`, `/player/market`) and removed their templates; kept active shop detail on `Player_view_city_shops.html` with dashboard-aligned navigation.
- [Done] Removed orphaned `/thank-you` from the access-request story (redirect only).
- [Done] Updated `404.html`, `base.html`, README, and dev log prefixes to Econo-Forge branding.
- [Done] Aligned public registration-key terminology and documented auto-access vs manual admin triage in docs and admin copy.

Acceptance checks:

- No primary player or GM route shows outdated "TT RPG Market" branding.
- Changelog entries have one source of truth.
- Access-request admin screens and public onboarding copy describe the same approval model.

## Phase 3: Simulation Performance And State Safety

Status: completed.

Goal: make the tick path more predictable before adding larger economy or state features.

Completed work:

- [Done] Keep the current tick instrumentation visible: `app/services/simulation.py` exposes `tick_duration` and phase timings such as load and compute duration.
- [Done] Preload active demand modifiers once per tick via `DemandContext` in `app/services/economy/demand.py`; indexed buckets replace per-item/per-city modifier queries on the canonical tick path.
- [Done] Pass precomputed demand context into `app/services/simulation.py` while preserving the existing single-commit and rollback behavior.
- [Done] Add focused tests for one modifier load per tick, no inner DB loads during pricing, phase timing coherence, and generous bounded-fixture ceilings (33ms remains a P99 measurement target, not a brittle CI gate).
- [Done] Document state authority in `app/services/world_state_reads.py`: row tables remain read-authoritative while `READ_PRICES_FROM_WORLD_STATE` is false; `GMWorldState` is a dual-write snapshot when `WORLD_STATE_ENABLED` is true.
- [Done] Add reconciliation and fallback tests around `app/services/world_state_reads.py` and post-tick row/blob alignment; `READ_PRICES_FROM_WORLD_STATE` remains disabled by default.

Acceptance checks:

- Tick behavior remains atomic: no extra commits inside pricing loops and rollback still protects failed ticks.
- Demand modifier loading does not create per-item/per-city query churn.
- State authority is documented before new read paths are enabled.

## Phase 4: Reliability, Tests, And CI

Status: completed.

Goal: catch production-critical regressions before deployment.

Completed work:

- [Done] Keep the existing deploy-branch Cloud Build pytest step that runs tests inside the built image before promotion.
- [Done] Preserve the access-request auto-key regression coverage in `tests/test_access_request_auto_key.py`.
- [Done] Extend `/ready` tests in `tests/test_ready.py` for dual Redis/DB failure, falsy ping, and `/healthz` liveness isolation.
- [Done] Extend ownership, refresh, and release tests in `tests/test_distributed_lock.py`.
- [Done] Add simulation lock-failure coverage in `tests/test_simulation_lock_failures.py` (busy lock, Redis acquire error, lock stolen mid-batch).
- [Done] Extend smoke coverage in `tests/test_smoke.py` for landing, docs, access-request, and register redirect.
- [Done] PR-time pytest gate via `.github/workflows/pytest.yml` on all pull requests; deploy README documents the GHA + Cloud Build split.
- [Deferred] Coverage and lint gates — revisit after Redis/readiness and lock regression coverage have been exercised in production CI.

Acceptance checks:

- Redis-dependent readiness and lock behavior are covered by tests.
- Feature branches get test feedback before deployment.
- Simulation metrics and lock failures cannot silently regress without test coverage.

## Phase 5: Deployment And Runtime Configuration

Status: completed.

Goal: keep local examples, Cloud Run, workers, and deploy docs aligned.

Completed work:

- [Done] Runtime env matrix in `config.example.env` with Dev/Web/Mig/Wrk role tags for `REQUIRE_REGISTRATION_KEY`, `WORLD_STATE_ENABLED`, `READ_PRICES_FROM_WORLD_STATE`, `METRICS_DURATIONS_CAP`, `METRICS_TERMINAL_TTL_SECONDS`, `SIM_TICK_DEBUG_ASSERTS`, `TRSG_CLOUD_RUN_MIGRATE`, and testing fallbacks.
- [Done] Mandatory post-deployment digest verification checklist in `deploy/README.md` and hardened `scripts/verify_worker_digest.sh` (read-only parity check).
- [Done] `scripts/prodlike_smoke.sh` for local gunicorn overlay smoke (`/healthz`, `/ready`); documented in `DOCKER.md` and `deploy/README.md`.
- [Done] Per-tick `tick_duration` telemetry via `record_tick_duration` in `app/services/sim_metrics.py` (Redis key `metrics:sim:tick_durations`); wired from `run_period_task`; exposed in admin metrics via `snapshot()` `tick_durations_seconds`.
- [Done] Focused tests in `tests/test_phase5_deployment_metrics.py`.

Deferred:

- Automatic GCE worker image rollout from Cloud Build (operator pins `TRSG_IMAGE` manually).
- Cloud Build-hosted prodlike smoke (Docker-in-Docker).
- Separate `METRICS_TICK_DURATIONS_CAP` unless later justified.

Acceptance checks:

- Every runtime env var used by app/deploy code is documented with its expected environment.
- Web and worker images can be verified against the same digest after deployment.
- Prodlike smoke catches bootstrap or readiness issues that SQLite-only tests miss.

## Suggested Implementation Order

1. Add Redis `/ready` and `distributed_lock` tests.
2. ~~Document runtime env vars in `config.example.env`.~~ (Phase 5 complete)
3. Preload demand modifiers and add bounded tick performance tests.
4. Decide and test state authority before enabling `GMWorldState` reads.
5. Phase 4 (extended `/ready`, lock safety, task lock-failure tests, and core route smoke validation) is complete; coverage caps and lint gates are deferred to a later post-Redis/readiness stage.
6. Revisit tech-demo funnel metrics after Phase 1 has had usage time, then decide whether activation needs more product work or deeper reliability investment.

## Deferred Ideas

- Paid-tier billing integration beyond YAML phase entitlements.
- Full model/module splitting for `models.py` and large route modules.
- Admin metrics dashboards for simulation jobs and tick timing.
- Larger world-state migration after state authority is decided.