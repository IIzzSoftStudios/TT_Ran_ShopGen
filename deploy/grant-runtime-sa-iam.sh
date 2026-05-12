#!/usr/bin/env bash
# Grant the Cloud Run / Cloud Run Jobs *runtime* service account the IAM roles
# required by cloudbuild.yaml (--set-secrets, Cloud SQL socket).
#
# Default SA when --service-account is omitted:
#   PROJECT_NUMBER-compute@developer.gserviceaccount.com
#
# Usage (from repo root, with gcloud auth and project set):
#   export PROJECT_ID=econo-forge
#   export RUNTIME_SA=219200674100-compute@developer.gserviceaccount.com
#   bash deploy/grant-runtime-sa-iam.sh
#
# Or from TT_Ran_ShopGen:
#   bash deploy/grant-runtime-sa-iam.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
RUNTIME_SA="${RUNTIME_SA:-}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "Set PROJECT_ID (e.g. export PROJECT_ID=econo-forge)" >&2
  exit 1
fi
if [[ -z "$RUNTIME_SA" ]]; then
  echo "Set RUNTIME_SA to your default compute SA, e.g.:" >&2
  echo "  export RUNTIME_SA=\$(gcloud projects describe \"\$PROJECT_ID\" --format='value(projectNumber)')-compute@developer.gserviceaccount.com" >&2
  exit 1
fi

MEMBER="serviceAccount:${RUNTIME_SA}"

echo "Binding roles/secretmanager.secretAccessor for ${MEMBER} on project ${PROJECT_ID}..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="${MEMBER}" \
  --role="roles/secretmanager.secretAccessor"

echo "Binding roles/cloudsql.client for ${MEMBER} on project ${PROJECT_ID}..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="${MEMBER}" \
  --role="roles/cloudsql.client"

echo "Done. Re-run Cloud Build; migrate job should mount secrets and connect to Cloud SQL."
