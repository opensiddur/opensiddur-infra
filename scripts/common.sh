#!/usr/bin/env bash
set -euo pipefail
umask 077
REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ENVIRONMENT=${1:?Usage: script dev|prod}
case "$ENVIRONMENT" in dev|prod) ;; *) echo 'Choose dev or prod' >&2; exit 2;; esac
PROJECT_ID=${PROJECT_ID:-opensiddur-builder-$ENVIRONMENT}
REGION=${REGION:-us-central1}
STATE_BUCKET=${STATE_BUCKET:-$PROJECT_ID-tfstate}
CONFIG="$REPO_ROOT/.runtime/$ENVIRONMENT.auto.tfvars"
mkdir -p "$REPO_ROOT/.runtime"
chmod 700 "$REPO_ROOT/.runtime"
export TF_DATA_DIR="$REPO_ROOT/.runtime/terraform-$ENVIRONMENT"
export TF_VAR_project_id="$PROJECT_ID" TF_VAR_environment="$ENVIRONMENT" TF_VAR_region="$REGION"
tf_init() {
 export GOOGLE_OAUTH_ACCESS_TOKEN="${GOOGLE_OAUTH_ACCESS_TOKEN:-$(gcloud auth print-access-token)}"
 terraform -chdir="$REPO_ROOT/infrastructure" init -reconfigure -backend-config="bucket=$STATE_BUCKET" -backend-config="prefix=builder/$ENVIRONMENT"
}
