#!/usr/bin/env bash
source "$(dirname "$0")/common.sh" "${1:-}"
: "${BILLING_ACCOUNT:?Set BILLING_ACCOUNT to the billing account ID}"
if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
 gcloud projects create "$PROJECT_ID" --name="Open Siddur Builder $ENVIRONMENT"
fi
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"
gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com iam.googleapis.com storage.googleapis.com --project="$PROJECT_ID"
if ! gcloud storage buckets describe "gs://$STATE_BUCKET" >/dev/null 2>&1; then
 gcloud storage buckets create "gs://$STATE_BUCKET" --project="$PROJECT_ID" --location="$REGION" --uniform-bucket-level-access
 gcloud storage buckets update "gs://$STATE_BUCKET" --versioning --public-access-prevention
fi
if [[ ! -f "$CONFIG" ]]; then cp "$REPO_ROOT/infrastructure/$ENVIRONMENT.tfvars.example" "$CONFIG"; fi
tf_init
cd "$REPO_ROOT"
uv run --frozen python scripts/adopt_firebase.py "$PROJECT_ID" "$CONFIG"
terraform -chdir="$REPO_ROOT/infrastructure" apply -var-file="$CONFIG"
echo "Foundation ready. State bucket: $STATE_BUCKET"
