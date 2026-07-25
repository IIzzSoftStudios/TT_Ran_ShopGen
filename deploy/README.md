# Deployment operations

GCP-readiness reference for the web tier (Cloud Run), the Celery worker
(GCE + systemd), and the shared Redis / Cloud SQL backplane. Pair this
with [`cloudbuild.yaml`](../cloudbuild.yaml) and the systemd units in
[`deploy/systemd/`](systemd/).

## Topology

```text
[Users] --HTTPS--> [Cloud Run web]
                       |
                       +---/cloudsql/---> [Cloud SQL Postgres]
                       |
                       +---VPC connector---> [Redis on GCE]
                                                ^
                                                |
                                           [GCE Celery worker]
                                                |
                                                +---/cloudsql/--> [Cloud SQL Postgres]
```

## VPC is mandatory (not optional)

For the documented topology — Redis hosted on a private GCE instance — Cloud
Run cannot reach Redis without one of:

1. **Serverless VPC Access connector** (recommended for Alpha simplicity).
2. **Direct VPC egress** (lower per-request overhead, fewer moving parts;
   evaluate after Alpha when traffic patterns are known).

Exposing Redis to the public internet is **not acceptable** in production
(rate limits, sessions, simulation locks, and the broker all live there);
running without VPC attachment will fail the `/ready` probe and break every
Redis-dependent code path.

`cloudbuild.yaml` warns at deploy time when `_VPC_CONNECTOR` is empty. Set
it via the build trigger UI or in `substitutions:` before merging to the
`deploy` branch.

## Continuous Integration Gates

All pull requests run pytest via GitHub Actions (`.github/workflows/pytest.yml`) using
in-memory SQLite (`SQLALCHEMY_DATABASE_URI=sqlite:///:memory:`), filesystem sessions
(`TRSG_TEST_FILESYSTEM_SESSION=1`), and Redis session fallback
(`SESSION_REDIS_FALLBACK=true`) so tests do not require live Redis or Cloud SQL.

Pushes to protected deploy branches (`main`, `master`, `deploy`, `GCP`) also trigger
Cloud Build, which runs `pytest -q` inside the built container image before that
image is promoted — validating the exact artifact about to be deployed.

## Cloud Run runtime service account (migrate job + web)

Cloud Build runs `gcloud run jobs create/update` and `gcloud run deploy` **without**
`--service-account`, so revisions use the **default Compute Engine service account**:

`PROJECT_NUMBER-compute@developer.gserviceaccount.com`

That identity must read any secret mounted with `--set-secrets` and open the
Cloud SQL Auth Proxy socket. If either is missing, you will see errors such as:

`Permission denied on secret ... for Revision service account ...-compute@developer.gserviceaccount.com`

### Fix (Alpha, project-wide)

From a workstation with Owner / Security Admin on the project:

```bash
export PROJECT_ID=econo-forge
export RUNTIME_SA="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
bash deploy/grant-runtime-sa-iam.sh
```

Or use the Console: **IAM & Admin → IAM → Grant access** → principal = that
service account → add **Secret Manager Secret Accessor** and **Cloud SQL Client**.

Secrets referenced today (grant accessor on each secret, or use project-level
binding above): `SECRET_KEY`, `SQLALCHEMY_DATABASE_URI`, `REDIS_URL`,
`MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`, `MAIL_SERVER`,
`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` (see
[`cloudbuild.yaml`](../cloudbuild.yaml) migrate and deploy steps).

Stripe price IDs (`STRIPE_PRICE_TIER1_MONTHLY`, `STRIPE_PRICE_TIER1_YEARLY`,
`STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_PRO_YEARLY`) are non-secret env vars
passed via Cloud Build substitutions `_STRIPE_PRICE_*` on deploy.

Before accepting live payments: enable **Managed Payments**, **Customer Portal**,
and **Smart Retries** (Billing → Revenue recovery) in the Stripe Dashboard.

### Per-secret alternative (tighter blast radius)

**Secret Manager →** each secret → **Permissions** → grant **Secret Manager Secret
Accessor** to `PROJECT_NUMBER-compute@developer.gserviceaccount.com`.

### Verification

After IAM propagates (~1 minute), re-run the Cloud Build trigger. The migrate
step should create or update `trsg-web-migrate` and the job execution should
proceed past secret mounting (next failures, if any, are app or DB URI issues).

### Optional hardening

Create a dedicated service account (e.g. `trsg-cloud-run@PROJECT_ID.iam.gserviceaccount.com`),
grant it only **Secret Accessor** + **Cloud SQL Client**, then add
`--service-account=...` to the `gcloud run jobs` and `gcloud run deploy` commands
in `cloudbuild.yaml` (and document the substitution here).

### Connector throughput (and when to pivot to Memorystore)

Serverless VPC Access connectors have a fixed bandwidth ceiling per machine
type (default `e2-micro` ≈ 200 Mbps). Cold-start herds plus session reads,
limiter writes, and broker chatter compete for that pipe; saturation
manifests as elevated TTFB before any single component hits CPU.

Sizing checklist (revisit each Alpha milestone):

| Signal | Action |
|--------|--------|
| Connector p95 utilization > 70% during cold starts | Upsize machine type or move to Direct VPC. |
| Redis `instantaneous_ops_per_sec` correlates with web latency spikes | Split limiter / sessions onto a second Redis (see `LIMITER_STORAGE_URI`). |
| Operator time on Redis patching / backups exceeds the cost delta | Migrate to **Memorystore for Redis** (managed). |

**Memorystore trade-off (deferred — todo `vpc-throughput-memorystore`):**

| | GCE Redis (current) | Memorystore |
|--|--|--|
| Patching / backups | Manual | Managed |
| Networking | Already on the same private network | Native VPC peering |
| Cost (Alpha tier) | Lower | ~3-4x for equivalent RAM |
| HA | Manual replica | Standard tier ships with replica + failover |
| Right answer | Solo ops, low traffic | Once Alpha metrics show ops time or HA matters |

## Image digest pinning (orchestration lock)

The web tier and the Celery worker **must** run the same byte-for-byte
image. Tag drift (`:latest` on the web, an older `:latest` cached on the
worker VM) silently breaks task deserialization or schema assumptions.

Pipeline:

1. `cloudbuild.yaml` resolves the immutable digest after `docker push` and
   writes it to `/workspace/image_digest.txt` (also persisted to GCS as a
   build artifact under `gs://$PROJECT-cloudbuild-artifacts/<service>/<sha>/`).
2. The `deploy` step deploys the web tier **by digest**, not by tag.
3. The worker VM reads `TRSG_IMAGE` from
   `/etc/systemd/system/trsg-worker.service.d/override.conf`. The value
   **must** be a digest reference
   (`region-docker.pkg.dev/PROJECT/REPO/SERVICE@sha256:...`).

Operator runbook for a worker rollout:

```bash
# On the operator workstation, copy the digest from the latest build:
gsutil cat gs://$PROJECT-cloudbuild-artifacts/trsg-web/$SHORT_SHA/image_digest.txt

# On the worker VM:
sudo $EDITOR /etc/systemd/system/trsg-worker.service.d/override.conf
#   [Service]
#   Environment="TRSG_IMAGE=us-central1-docker.pkg.dev/.../trsg-web@sha256:..."
sudo systemctl daemon-reload
sudo systemctl restart trsg-worker
```

### Mandatory post-deployment release verification

After every Cloud Build deploy that promotes a new web revision:

1. Read the immutable digest from the build artifact (`image_digest.txt` in the
   Cloud Build workspace or `gs://$PROJECT-cloudbuild-artifacts/trsg-web/$SHORT_SHA/image_digest.txt`).
2. On the GCE worker VM, set `TRSG_IMAGE` in
   `/etc/systemd/system/trsg-worker.service.d/override.conf` to that **digest**
   reference (`region-docker.pkg.dev/PROJECT/REPO/SERVICE@sha256:...`).
3. Reload and restart the worker: `sudo systemctl daemon-reload &&
   sudo systemctl restart trsg-worker`.
4. From an authenticated workstation (repo root), verify parity:

```bash
export PROJECT_ID=econo-forge REGION=us-central1 SERVICE=trsg-web
export WORKER_DIGEST="$(grep TRSG_IMAGE /etc/systemd/system/trsg-worker.service.d/override.conf | cut -d= -f2- | tr -d ' \"')"
bash scripts/verify_worker_digest.sh "$WORKER_DIGEST"
```

The script is **read-only** — it compares the worker pin against the live Cloud
Run image and exits non-zero on mismatch. CI never updates the worker for you;
align worker rollouts with web deploys explicitly so a long-running Year batch
is never killed by an automatic image swap. Schema migrations run as part of the
Cloud Build pipeline (`migrate` step) before the new web revision serves traffic.

Optional one-liner (same as step 4, run on a machine that can SSH-read the worker override):

```bash
bash scripts/verify_worker_digest.sh "$(grep TRSG_IMAGE /etc/systemd/system/trsg-worker.service.d/override.conf | cut -d= -f2- | tr -d ' \"')"
```

## Redis hot-path topology

A single Redis instance currently backs sessions, Flask-Limiter, the Celery
broker, the Celery result backend, distributed locks, and `sim_job:*`
progress writes. Redis is single-threaded; under load these workloads
contend for the same event loop.

Profile during Alpha (todo `redis-hot-path-split`):

- `INFO commandstats` and `latency latest` while a Year batch runs.
- `CLIENT LIST` to identify chatty workers.
- Web session p95 vs. simulation progress write rate.

Levers, in increasing operational cost:

1. **Reduce write frequency.** `run_period_task` HSETs `sim_job:*` after
   every tick. Larger intervals (every N ticks) trade UI smoothness for
   Redis headroom.
2. **Use pipelining** for the burst of writes at job start/end.
3. **Split the URL.** Set `LIMITER_STORAGE_URI` and/or
   `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` to a second Redis (or a
   separate logical DB on the same instance, e.g. `/1`, `/2`) so session
   reads do not queue behind broker traffic.
4. **Move sessions to Memorystore**, leave the broker on GCE Redis (or vice
   versa) to isolate failure modes.

## Cloud SQL connection budget

Each web instance and each Celery worker hold up to
`DB_POOL_SIZE + DB_MAX_OVERFLOW` connections per process; long-running
Year batches keep them checked out for minutes. Web instances are
short-lived per request; workers are long-lived and dominate steady state.

Effective ceiling:

```text
total_active <= web_max_instances * gunicorn_workers * (DB_POOL_SIZE_web + DB_MAX_OVERFLOW_web)
              + worker_vms * CELERY_CONCURRENCY     * (DB_POOL_SIZE_wkr + DB_MAX_OVERFLOW_wkr)
```

Defaults (override per role with `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`):

| Role | `DB_POOL_SIZE` | `DB_MAX_OVERFLOW` | Trigger |
|------|----------------|-------------------|---------|
| Web (Cloud Run, default) | 5 | 5 | Stateless requests, burst tolerant |
| Worker (`TRSG_ROLE=worker`) | 2 | 2 | One Year batch per concurrency slot |

Alpha sizing example, Cloud SQL `db-custom-2-7680` (~100 connections):

```text
web   (max 3 inst x 2 gunicorn x 10) = 60
wkr   (1 vm   x 4 concurrency x  4) = 16
                                     ----
                                     76 < 100  OK
```

When CELERY_CONCURRENCY climbs toward 10 on a single VM, raise the Cloud
SQL tier first (or front the workers with PgBouncer in transaction-pool
mode); do not let `total_active` exceed ~80% of `max_connections`.

## Deferred: auto-refusal thresholds (Hard No)

Todo `alpha-year-hard-no` (deliberately not implemented yet). Once
`alpha-metrics-queue` produces real durations and Cloud SQL / Redis SLOs
are agreed, add a guard at the start of `run_period_stream` that returns
HTTP 503 with a "service overloaded" message when any of:

| Signal (proposed) | Source |
|-------------------|--------|
| `running >= max_concurrent_runs` | `metrics:sim:running` |
| `queue_depth >= max_queue_depth` | Celery broker `LLEN celery` |
| Cloud SQL `connections / max_connections > 0.8` | Cloud SQL Insights |
| Redis `latency_ms_p95 > N` | `INFO commandstats` / `latency latest` |

Until those numbers exist, prefer the ACID rollback story (a failed batch
does no harm) plus operator-side feature flags over a brittle synthetic
threshold. Revisit when `/admin/vault/metrics/simulation` shows stable
distributions across at least one Year run.

## Local prodlike smoke (optional pre-push)

Before pushing to a deploy branch, you can run a production-shaped stack locally
(gunicorn overlay + real Postgres and Redis) to catch bootstrap and `/ready`
wiring issues that SQLite-only pytest misses:

```bash
cd TT_Ran_ShopGen
bash scripts/prodlike_smoke.sh
```

Pass `--teardown` to stop containers after a successful run. Requires Docker,
`curl`, and Bash. This does **not** simulate Cloud SQL Unix sockets or VPC
connectors — see [`DOCKER.md`](../DOCKER.md) for compose details.

**Deferred:** Running this script inside Cloud Build (Docker-in-Docker).

