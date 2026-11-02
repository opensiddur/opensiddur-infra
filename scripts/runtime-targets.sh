# Application promotion deliberately excludes privileged foundation/IAM/billing edits.
RUNTIME_TARGETS=(
 -target=google_cloud_run_v2_service.api
 -target=google_cloud_run_v2_service.preview
 -target=google_cloud_run_v2_job.build
 -target=google_cloud_run_v2_service_iam_member.public_api
 -target=google_cloud_run_v2_service_iam_member.private_preview
 -target=google_cloud_scheduler_job.maintenance
)
