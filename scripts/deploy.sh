#!/usr/bin/env bash
source "$(dirname "$0")/common.sh" "${1:-}"
cd "$REPO_ROOT"
command -v uv >/dev/null
command -v npm >/dev/null
if grep -Eq '^submissions_enabled[[:space:]]*=[[:space:]]*true' "$CONFIG"; then
 : "${PRIVACY_OPERATOR:?Set the confirmed legal controller}"
 : "${PRIVACY_CONTACT:?Set the privacy contact}"
 : "${APP_CHECK_SITE_KEY:?Configure production App Check before opening submissions}"
 [[ "${PRIVACY_READY:-false}" == true ]] || { echo 'Complete the privacy launch review and set PRIVACY_READY=true.' >&2; exit 2; }
fi
uv sync --frozen
uv run pytest
npm --prefix web ci
npm --prefix web run build
node scripts/frontend-notices.mjs
RELEASE=$(python3 scripts/release_id.py)
python3 -c 'import json,subprocess,pathlib;pathlib.Path(".bundle/source.json").write_text(json.dumps({"infra_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()}))'
REGISTRY="$REGION-docker.pkg.dev/$PROJECT_ID/builder"
gcloud builds submit . --project="$PROJECT_ID" --config=cloudbuild.yaml --substitutions="_REGISTRY=$REGISTRY,_RELEASE=$RELEASE" --service-account="projects/$PROJECT_ID/serviceAccounts/builder-build@$PROJECT_ID.iam.gserviceaccount.com" --gcs-source-staging-dir="gs://$PROJECT_ID-builds/source" --gcs-log-dir="gs://$PROJECT_ID-builds/logs"
WORKER_DIGEST=$(gcloud artifacts docker images describe "$REGISTRY/worker:$RELEASE" --project="$PROJECT_ID" --format='value(image_summary.digest)')
API_DIGEST=$(gcloud artifacts docker images describe "$REGISTRY/api:$RELEASE" --project="$PROJECT_ID" --format='value(image_summary.digest)')
tf_init
uv run --frozen python scripts/adopt_firebase.py "$PROJECT_ID" "$CONFIG"
python3 scripts/deployment_history.py load "$STATE_BUCKET" "$CONFIG"
source scripts/runtime-targets.sh
terraform -chdir=infrastructure apply "${RUNTIME_TARGETS[@]}" -var-file="$CONFIG" -var="image=$REGISTRY/worker@$WORKER_DIGEST" -var="api_image=$REGISTRY/api@$API_DIGEST" -var="release_id=$RELEASE"
python3 scripts/save_deployment.py "$CONFIG" "$REGISTRY/worker@$WORKER_DIGEST" "$REGISTRY/api@$API_DIGEST" "$RELEASE"
gcloud tasks queues resume builder --project="$PROJECT_ID" --location="$REGION"
gcloud tasks queues resume previews --project="$PROJECT_ID" --location="$REGION"
python3 scripts/deployment_history.py save "$STATE_BUCKET" "$CONFIG"
python3 scripts/hosting_config.py "$PROJECT_ID" "$REGION"
# REST upload uses gcloud's existing identity, avoiding a separate Firebase CLI login.
uv run --frozen python scripts/deploy_hosting.py "$PROJECT_ID"
gcloud scheduler jobs resume builder-maintenance --project="$PROJECT_ID" --location="$REGION"
curl --fail --silent --show-error "https://$PROJECT_ID.web.app/api/v1/health"
echo "Website: https://$PROJECT_ID.web.app"
