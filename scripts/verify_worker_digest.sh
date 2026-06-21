#!/usr/bin/env bash
# Verify Cloud Run web revision and GCE worker use the same image digest.
# Read-only: does not deploy or mutate systemd configuration.
# Usage:
#   export PROJECT_ID=econo-forge REGION=us-central1 SERVICE=trsg-web
#   export WORKER_DIGEST="$(grep TRSG_IMAGE /etc/systemd/system/trsg-worker.service.d/override.conf | cut -d= -f2- | tr -d ' \"')"
#   bash scripts/verify_worker_digest.sh "$WORKER_DIGEST"
set -euo pipefail

WORKER_DIGEST="${1:-}"
if [[ -z "${WORKER_DIGEST}" ]]; then
  echo "Usage: $0 <worker@sha256:digest>" >&2
  echo "Read TRSG_IMAGE from trsg-worker.service.d/override.conf on the worker VM." >&2
  exit 2
fi

PROJECT_ID="${PROJECT_ID:-econo-forge}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-trsg-web}"

WEB_DIGEST="$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(spec.template.spec.containers[0].image)')"

if [[ "${WEB_DIGEST}" == *"${WORKER_DIGEST}"* ]] || [[ "${WORKER_DIGEST}" == *"${WEB_DIGEST##*@}"* ]]; then
  echo "OK: digests align."
  echo "Web image:    ${WEB_DIGEST}"
  echo "Worker image: ${WORKER_DIGEST}"
  exit 0
fi

echo "[CRITICAL ERROR] Worker digest parity breach!" >&2
echo "Expected Pin Target:  ${WORKER_DIGEST}" >&2
echo "Live Cloud Run State: ${WEB_DIGEST}" >&2
echo "[DIAGNOSTICS] Verification control is driven by:" >&2
echo "- PROJECT_ID: ${PROJECT_ID:-Unset (gcloud default)}" >&2
echo "- REGION:     ${REGION:-Unset (gcloud default)}" >&2
echo "- SERVICE:    ${SERVICE:-Unset (gcloud default)}" >&2
exit 1
