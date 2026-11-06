output "website" { value = local.api_url }
output "api_url" { value = try(google_cloud_run_v2_service.api[0].uri, "") }
output "preview_url" { value = try(google_cloud_run_v2_service.preview[var.release_id].uri, "") }
output "job" { value = try(google_cloud_run_v2_job.build[var.release_id].id, "") }
output "workload_identity_provider" { value = google_iam_workload_identity_pool_provider.github.name }
output "deployment_service_account" { value = google_service_account.account["deployer"].email }
output "web_app_id" { value = google_firebase_web_app.web.app_id }
