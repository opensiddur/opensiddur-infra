resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.api]
}
resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == 'opensiddur/opensiddur-infra' && assertion.ref == 'refs/heads/main'"
  oidc { issuer_uri = "https://token.actions.githubusercontent.com" }
}
resource "google_service_account_iam_member" "github" {
  service_account_id = google_service_account.account["deployer"].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/opensiddur/opensiddur-infra"
}
resource "google_project_iam_member" "deploy_roles" {
  for_each = toset(["roles/run.admin", "roles/cloudbuild.builds.editor", "roles/artifactregistry.reader", "roles/firebasehosting.admin", "roles/serviceusage.serviceUsageConsumer", "roles/serviceusage.serviceUsageViewer", "roles/firebase.admin", "roles/iam.securityReviewer", "roles/iam.workloadIdentityPoolViewer", "roles/datastore.indexAdmin", "roles/cloudscheduler.admin", "roles/cloudtasks.queueAdmin", "roles/storage.admin"])
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.account["deployer"].email}"
}
resource "google_service_account_iam_member" "deploy_act_as" {
  for_each           = toset(["api", "worker", "build"])
  service_account_id = google_service_account.account[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.account["deployer"].email}"
}
resource "google_storage_bucket_iam_member" "deploy_source" {
  bucket = google_storage_bucket.builds.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.account["deployer"].email}"
}
