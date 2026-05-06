# Docker Compose (local dev)

Stack: **PostgreSQL**, **Redis**, **Flask** (`web`), **Celery** (`worker`). Build context and compose file live in this directory (`TT_Ran_ShopGen/`).

## Prerequisites

- Docker Engine and Docker Compose v2.

## First-time database schema

On the **first** start with an **empty** `postgres_data` volume, PostgreSQL runs [`TTRSG_TableCreation.sql`](TTRSG_TableCreation.sql) from `docker-entrypoint-initdb.d`. That only happens when the data directory is empty.

If you change `TTRSG_TableCreation.sql` and need a clean DB:

```bash
docker compose down -v
docker compose up --build
```

The `-v` flag removes named volumes so init scripts run again on the next `up`.

**Alternative (ORM bootstrap):** You can instead bring up `db` and `redis`, then run `docker compose run --rm web python scripts/init_schema.py` before `web`/`worker`. Use one approach consistently for your environment.

## Run

From `TT_Ran_ShopGen/`:

```bash
docker compose up --build
```

- App: <http://127.0.0.1:5000>
- Health: <http://127.0.0.1:5000/healthz>
- Check **worker** logs for Celery ready / task consumption.

## Environment

Compose sets `REDIS_URL`, `SQLALCHEMY_DATABASE_URI`, `SECRET_KEY`, and Flask vars for `web` and `worker`. `config.env` is gitignored and not copied into the image (see [`.dockerignore`](.dockerignore)); local file-based config is for non-Docker runs.

`load_dotenv("config.env")` in the app is harmless when the file is missing; Compose-provided variables take precedence in the container.

## Readiness vs healthchecks

`pg_isready` and `redis-cli ping` only show that the daemons **accept connections**. They do **not** guarantee that `init.sql` has finished creating every table. For large init scripts, you may still see rare races on first boot. Mitigations:

- Retry DB connections in app startup or an entrypoint wrapper (e.g. loop on `SELECT 1` until success).
- Or accept the risk for small init scripts and restart `worker` once if it fails once.

The Flask app's `/healthz` endpoint is dependency-free (no DB or Redis call) so Cloud Run startup probes stay green even during a transient backend outage.

## Optional: live code reload (web)

`FLASK_DEBUG=1` reloads when files change **inside** the container. To edit code on the host without rebuilding, add a **local-only** `docker-compose.override.yml` (do not commit secrets; this repo lists it in `.dockerignore`):

```yaml
services:
  web:
    volumes:
      - .:/app
```

## Worker concurrency

The worker uses `--concurrency=1` to keep memory use low on Docker Desktop. For CPU-heavy workloads you can raise concurrency or use `-P solo` in `docker-compose.yml`. Production tuning may add `--max-tasks-per-child` to recycle workers (see deploy docs if present).

## Image notes

The Dockerfile uses **gunicorn** as default `CMD` for production-shaped images. The dev `docker-compose.yml` overrides `web`'s command to `flask run` so live reload works locally.

## Prodlike overlay

If [`docker-compose.prodlike.yml`](docker-compose.prodlike.yml) exists, it can run gunicorn and production-shaped env for local verification:

```bash
docker compose -f docker-compose.yml -f docker-compose.prodlike.yml up -d
```

## Refreshing `TTRSG_TableCreation.sql` (when models change)

Regenerate whenever ORM models change and you rely on the SQL snapshot for Cloud SQL or init:

```bash
docker compose down -v
docker compose up -d db redis
docker compose run --rm web python scripts/init_schema.py
docker compose exec db pg_dump --schema-only --no-owner --no-privileges -U trsg_user trsg_db > TTRSG_TableCreation.sql
```

Hand-review the diff before committing.
