#!/usr/bin/env bash
source "$(dirname "$0")/common.sh" "${1:-}"
[[ "${CONFIRM_PURGE:-}" == "$PROJECT_ID" && "${CONFIRM_PROJECT_DELETE:-}" == "$PROJECT_ID" ]] || {
 echo "Destructive: set both CONFIRM_PURGE and CONFIRM_PROJECT_DELETE to $PROJECT_ID." >&2
 exit 2
}
bash "$REPO_ROOT/scripts/undeploy.sh" "$ENVIRONMENT" purge
gcloud storage rm --all-versions --recursive "gs://$STATE_BUCKET"
gcloud projects delete "$PROJECT_ID" --quiet
