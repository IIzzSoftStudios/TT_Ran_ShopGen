#!/usr/bin/env bash
# Local production-like smoke: gunicorn overlay + real Postgres/Redis via compose.
# Usage: bash scripts/prodlike_smoke.sh [--teardown]
set -euo pipefail

TEARDOWN=false
for arg in "$@"; do
  if [[ "$arg" == "--teardown" ]]; then
    TEARDOWN=true
  fi
done

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.prodlike.yml)

echo "[INFO] Assembling compound production-like local containers..."
docker compose "${COMPOSE_FILES[@]}" up -d --build

echo "[INFO] Polling application health endpoint (/healthz)..."
TIMEOUT=30
ELAPSED=0
until curl --output /dev/null --silent --head --fail http://127.0.0.1:5000/healthz; do
  if [[ "${ELAPSED}" -ge "${TIMEOUT}" ]]; then
    echo "[FAIL] Health timeout breached. Web proxy initialization failed."
    exit 1
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done

echo "[INFO] Auditing internal dependency readiness states (/ready)..."
STATUS_CODE="$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/ready)"

if [[ "${STATUS_CODE}" -eq 200 ]]; then
  echo "[SUCCESS] Smoke verification phase complete."
  if [[ "${TEARDOWN}" == true ]]; then
    echo "[INFO] Dropping transient containers and infrastructure..."
    docker compose "${COMPOSE_FILES[@]}" down
  fi
  exit 0
fi

echo "[FAIL] Ready endpoint returned terminal status code: ${STATUS_CODE}"
echo "[DIAGNOSTICS] Streaming recent output streams for triage diagnostics:"
docker compose "${COMPOSE_FILES[@]}" logs --tail=50
exit 1
