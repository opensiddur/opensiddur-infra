#!/usr/bin/env bash
source "$(dirname "$0")/common.sh" "${1:-}"
MODE=${2:-services}
case "$MODE" in services|purge) ;; *) echo 'Usage: undeploy.sh dev|prod [services|purge]' >&2; exit 2;; esac
tf_init
gcloud tasks queues pause builder --project="$PROJECT_ID" --location="$REGION"
gcloud tasks queues pause previews --project="$PROJECT_ID" --location="$REGION"
python3 "$REPO_ROOT/scripts/quiesce.py" "$PROJECT_ID" "$REGION"
if [[ "$MODE" == services ]]; then
 # Retain all stateful resources; removing only managed compute stops ongoing charges.
 terraform -chdir="$REPO_ROOT/infrastructure" apply -var-file="$CONFIG" -var='image=' -var='api_image='
 gcloud tasks queues pause builder --project="$PROJECT_ID" --location="$REGION"
 gcloud tasks queues pause previews --project="$PROJECT_ID" --location="$REGION"
 echo 'Compute removed. Authentication, artifacts, saved settings and state are preserved.'
else
 [[ "${CONFIRM_PURGE:-}" == "$PROJECT_ID" ]] || { echo "Set CONFIRM_PURGE=$PROJECT_ID to permanently erase service data." >&2; exit 2; }
 # First stop accepting work and remove runtime, then delete identities and data.
 terraform -chdir="$REPO_ROOT/infrastructure" apply -var-file="$CONFIG" -var='image=' -var='api_image=' -var='purge_data=true'
 python3 "$REPO_ROOT/scripts/purge_auth.py" "$PROJECT_ID"
 terraform -chdir="$REPO_ROOT/infrastructure" destroy -var-file="$CONFIG" -var='image=' -var='api_image=' -var='purge_data=true'
 echo 'Managed application resources removed. GCP projects and protected Terraform state bucket remain for audit/recovery.'
 echo "To erase the state bucket too: gcloud storage rm --all-versions --recursive gs://$STATE_BUCKET"
fi
