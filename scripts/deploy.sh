#!/usr/bin/env bash
source "$(dirname "$0")/common.sh" "${1:-}"
cd "$REPO_ROOT"
command -v uv >/dev/null
command -v npm >/dev/null

VERSION=${BUILDER_VERSION:-}
PHASE=${DEPLOY_PHASE:-development}
COMMIT=$(git rev-parse HEAD)
admission_args=(-var=submissions_enabled=false)
if [[ "$ENVIRONMENT" == prod ]]; then
  [[ "$PROJECT_ID" == opensiddur-builder-prod ]]
  [[ "$PHASE" == pilot || "$PHASE" == public ]]
  python3 scripts/release_notes.py "$VERSION" >/dev/null
  [[ $(git cat-file -t "refs/tags/$VERSION") == tag ]]
  [[ $(git rev-parse "refs/tags/$VERSION^{commit}") == "$COMMIT" ]]
  : "${PRIVACY_OPERATOR:?Set the confirmed legal controller}"
  : "${PRIVACY_CONTACT:?Set the privacy contact}"
  : "${APPROVED_PRIVACY_NOTICE:?Supply the approved production privacy notice}"
  : "${APP_CHECK_SITE_KEY:?Configure production App Check}"
  [[ "${PRIVACY_READY:-false}" == true ]] || { echo 'Complete the privacy launch review and set PRIVACY_READY=true.' >&2; exit 2; }
  admission_args+=(-var=require_app_check=true)
  if [[ "$PHASE" == pilot || "$VERSION" == v0.1.0 || "${FIRST_PUBLIC_LAUNCH:-false}" == true ]]; then
    operators=$(jq -ce 'select(type == "array" and length > 0 and all(.[]; type == "string" and test("^[^@[:space:]]+@[^@[:space:]]+$")))' <<< "${PILOT_OPERATORS:-[]}")
    admission_args+=("-var=admin_emails=$operators")
  fi
elif grep -Eq '^submissions_enabled[[:space:]]*=[[:space:]]*true' "$CONFIG"; then
  echo 'Development must keep public submissions disabled.' >&2
  exit 2
fi

uv sync --frozen
uv run --frozen pytest
npm --prefix web ci
npm --prefix web test
npm --prefix web run build
node scripts/frontend-notices.mjs
mkdir -p .bundle
jq -nc --arg commit "$COMMIT" --arg version "$VERSION" \
  '{infra_commit: $commit} + (if $version == "" then {} else {version: $version} end)' > .bundle/source.json
RELEASE=$(python3 scripts/release_id.py)
REGISTRY="$REGION-docker.pkg.dev/$PROJECT_ID/builder"
record_root="gs://$STATE_BUCKET/deployments/versions/$VERSION"
prepared=.runtime/prepared-release.json
pilot_hosting_version=
if [[ "$ENVIRONMENT" == prod && "$PHASE" == public ]]; then
  if [[ "$VERSION" != v0.1.0 ]]; then
    gcloud storage cat "gs://$STATE_BUCKET/deployments/versions/v0.1.0/public.json" |
      jq -e '.version == "v0.1.0" and .submissions_enabled == true' >/dev/null
  fi
  if [[ "$VERSION" == v0.1.0 || "${FIRST_PUBLIC_LAUNCH:-false}" == true ]]; then
    pilot_hosting_version=$(gcloud storage cat "$record_root/pilot.json" |
      jq -er --arg commit "$COMMIT" --arg release "$RELEASE" \
        'select(.infra_commit == $commit and .release == $release and .submissions_enabled == false) | .hosting_version')
  fi
fi

# Once a version has passed the smoke build, reuse its immutable images
# on retries and when opening the pilot to the public.
prepared_exists=false
if [[ -n "$VERSION" ]]; then
  if gcloud storage cat "$record_root/images.json" > "$prepared" 2> .runtime/release-read-error; then
    prepared_exists=true
  elif ! rg -qi 'not found|notfound|matched no objects|404' .runtime/release-read-error; then
    cat .runtime/release-read-error >&2
    exit 1
  fi
fi
if [[ "$prepared_exists" == true ]]; then
  jq -e --arg commit "$COMMIT" --arg release "$RELEASE" --arg version "$VERSION" \
    '.infra_commit == $commit and .release == $release and .version == $version' "$prepared" >/dev/null
  WORKER_IMAGE=$(jq -er '.worker_image' "$prepared")
  API_IMAGE=$(jq -er '.api_image' "$prepared")
else
  gcloud builds submit . --project="$PROJECT_ID" --config=cloudbuild.yaml --substitutions="_REGISTRY=$REGISTRY,_RELEASE=$RELEASE" --service-account="projects/$PROJECT_ID/serviceAccounts/builder-build@$PROJECT_ID.iam.gserviceaccount.com" --gcs-source-staging-dir="gs://$PROJECT_ID-builds/source" --gcs-log-dir="gs://$PROJECT_ID-builds/logs"
  WORKER_DIGEST=$(gcloud artifacts docker images describe "$REGISTRY/worker:$RELEASE" --project="$PROJECT_ID" --format='value(image_summary.digest)')
  API_DIGEST=$(gcloud artifacts docker images describe "$REGISTRY/api:$RELEASE" --project="$PROJECT_ID" --format='value(image_summary.digest)')
  WORKER_IMAGE="$REGISTRY/worker@$WORKER_DIGEST"
  API_IMAGE="$REGISTRY/api@$API_DIGEST"
fi
[[ "$WORKER_IMAGE" =~ ^${REGISTRY}/worker@sha256:[a-f0-9]{64}$ ]]
[[ "$API_IMAGE" =~ ^${REGISTRY}/api@sha256:[a-f0-9]{64}$ ]]
if [[ -n "$VERSION" && "$prepared_exists" == false ]]; then
  jq -nc --arg version "$VERSION" --arg commit "$COMMIT" --arg release "$RELEASE" \
    --arg worker "$WORKER_IMAGE" --arg api "$API_IMAGE" \
    '{version:$version, infra_commit:$commit, release:$release, worker_image:$worker, api_image:$api}' > "$prepared"
  gcloud storage cp --if-generation-match=0 "$prepared" "$record_root/images.json"
fi

tf_init
uv run --frozen python scripts/adopt_firebase.py "$PROJECT_ID" "$CONFIG"
python3 scripts/deployment_history.py load "$STATE_BUCKET" "$CONFIG"
source scripts/runtime-targets.sh
runtime_args=(-var-file="$CONFIG" -var="image=$WORKER_IMAGE" -var="api_image=$API_IMAGE" -var="release_id=$RELEASE")
terraform -chdir=infrastructure apply "${RUNTIME_TARGETS[@]}" "${runtime_args[@]}" "${admission_args[@]}"
python3 scripts/save_deployment.py "$CONFIG" "$WORKER_IMAGE" "$API_IMAGE" "$RELEASE"
python3 scripts/deployment_history.py save "$STATE_BUCKET" "$CONFIG"
gcloud tasks queues resume builder --project="$PROJECT_ID" --location="$REGION"
gcloud tasks queues resume previews --project="$PROJECT_ID" --location="$REGION"
python3 scripts/hosting_config.py "$PROJECT_ID" "$REGION"
hosting_version=$pilot_hosting_version
if [[ -z "$hosting_version" ]]; then
  hosting_version=$(uv run --frozen python scripts/deploy_hosting.py "$PROJECT_ID")
fi
gcloud scheduler jobs resume builder-maintenance --project="$PROJECT_ID" --location="$REGION"

site="https://$PROJECT_ID.web.app"
check_health() {
  local enabled=$1
  for attempt in {1..12}; do
    if curl -fsS --max-time 15 "$site/api/v1/health" |
      jq -e --arg release "$RELEASE" --arg version "$VERSION" --arg commit "$COMMIT" \
        --arg environment "$ENVIRONMENT" --arg enabled "$enabled" \
        '.ok and .release == $release and .infra_commit == $commit and
         ((.version // "") == $version) and
         (.submissions_enabled | tostring) == $enabled and
         ($environment != "prod" or .app_check_required)' >/dev/null; then
      return 0
    fi
    sleep 5
  done
  echo "Live API did not report the expected version and admission policy." >&2
  return 1
}
check_health false
curl -fsS --max-time 20 "$site/?release=$RELEASE" | cmp web/dist/index.html
bundle=$(sed -n 's/.*src="\(\/assets\/[^"]*\.js\)".*/\1/p' web/dist/index.html)
[[ -n "$bundle" ]]
curl -fsS --max-time 20 "$site$bundle" | cmp "web/dist$bundle"
curl -fsS --max-time 20 "$site/runtime-config.json?release=$RELEASE" | cmp web/dist/runtime-config.json
curl -fsS --max-time 20 "$site/privacy.html?release=$RELEASE" | cmp web/dist/privacy.html

if [[ "$ENVIRONMENT" == prod ]]; then
  enabled=false
  if [[ "$PHASE" == public ]]; then enabled=true; fi
  jq --arg hosting "$hosting_version" --argjson enabled "$enabled" \
    '. + {hosting_version:$hosting, submissions_enabled:$enabled}' "$prepared" > .runtime/deployment.json
  if [[ "$PHASE" == public ]]; then
    if ! terraform -chdir=infrastructure apply -target=google_cloud_run_v2_service.api \
      "${runtime_args[@]}" -var=require_app_check=true -var=submissions_enabled=true ||
      ! check_health true ||
      ! gcloud storage cp .runtime/deployment.json "$record_root/public.json"; then
      terraform -chdir=infrastructure apply -target=google_cloud_run_v2_service.api \
        "${runtime_args[@]}" "${admission_args[@]}"
      exit 1
    fi
  else
    gcloud storage cp .runtime/deployment.json "$record_root/pilot.json"
  fi
fi
echo "Website: $site ($VERSION $RELEASE)"
