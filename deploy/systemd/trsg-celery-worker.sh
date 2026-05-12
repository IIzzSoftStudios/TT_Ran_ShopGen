#!/bin/bash
# Celery worker launcher for systemd (GCE VM). Keeps trsg-worker.service short
# so editors/pagers do not truncate a single long docker line.
set -euo pipefail
: "${TRSG_IMAGE:?TRSG_IMAGE must be set (see trsg-worker.service.d/override.conf)}"

exec /usr/bin/docker run --rm --name trsg-worker \
  --network host \
  --env-file /etc/trsg/worker.env \
  --env TRSG_ROLE=worker \
  --env CELERY_WORKER_RUNNING=1 \
  --env CELERY_CONCURRENCY=1 \
  --env CELERY_WORKER_CONCURRENCY=1 \
  "${TRSG_IMAGE}" \
  celery -A celery_app.celery worker \
    --loglevel=info \
    --concurrency=1 \
    --max-tasks-per-child=50 \
    --time-limit=7200 \
    --soft-time-limit=6900
