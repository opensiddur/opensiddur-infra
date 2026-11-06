locals {
  services = toset(["run.googleapis.com", "cloudbuild.googleapis.com", "artifactregistry.googleapis.com",
    "firestore.googleapis.com", "storage.googleapis.com", "cloudtasks.googleapis.com", "cloudscheduler.googleapis.com",
    "firebase.googleapis.com", "firebasehosting.googleapis.com", "identitytoolkit.googleapis.com",
  "iam.googleapis.com", "iamcredentials.googleapis.com", "sts.googleapis.com", "logging.googleapis.com", "firebaserules.googleapis.com"])
  accounts       = toset(["api", "worker", "dispatcher", "build", "deployer"])
  runtime        = var.image != ""
  job_name       = "builder-${substr(var.release_id, 0, 35)}"
  api_url        = "https://${var.project_id}.web.app"
  release_images = var.image != "" ? merge(var.release_images, { (var.release_id) = var.image }) : {}
  common_env = {
    GOOGLE_CLOUD_PROJECT = var.project_id
    REGION               = var.region
    ARTIFACT_BUCKET      = google_storage_bucket.artifacts.name
    RELEASE_ID           = var.release_id
    WORKER_EMAIL         = google_service_account.account["worker"].email
    DISPATCHER_EMAIL     = google_service_account.account["dispatcher"].email
    INTERNAL_AUDIENCE    = "https://opensiddur-builder/internal"
  }
}
resource "google_project_service" "api" {
  for_each           = local.services
  service            = each.key
  disable_on_destroy = false
}
resource "google_service_account" "account" {
  for_each     = local.accounts
  account_id   = "builder-${each.key}"
  display_name = "Open Siddur ${each.key}"
  depends_on   = [google_project_service.api]
}
resource "google_artifact_registry_repository" "images" {
  location               = var.region
  repository_id          = "builder"
  format                 = "DOCKER"
  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "old-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "2678400s"
    }
  }
  depends_on = [google_project_service.api]
}
resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.purge_data
  soft_delete_policy { retention_duration_seconds = 0 }
  lifecycle_rule {
    action { type = "Delete" }
    condition {
      age            = 31
      matches_prefix = ["builds/"]
    }
  }
}
resource "google_storage_bucket" "builds" {
  name                        = "${var.project_id}-builds"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.purge_data
  soft_delete_policy { retention_duration_seconds = 0 }
  lifecycle_rule {
    action { type = "Delete" }
    condition { age = 30 }
  }
}
resource "google_firestore_database" "default" {
  name                    = "(default)"
  location_id             = var.region
  type                    = "FIRESTORE_NATIVE"
  delete_protection_state = var.purge_data ? "DELETE_PROTECTION_DISABLED" : "DELETE_PROTECTION_ENABLED"
  deletion_policy         = var.purge_data ? "DELETE" : "ABANDON"
  depends_on              = [google_project_service.api]
}
resource "google_firestore_index" "owner" {
  collection = "builder_records"
  fields {
    field_path = "kind"
    order      = "ASCENDING"
  }
  fields {
    field_path = "owner"
    order      = "ASCENDING"
  }
  depends_on = [google_firestore_database.default]
}
resource "google_firebase_project" "default" {
  provider   = google-beta
  project    = var.project_id
  depends_on = [google_project_service.api]
}
resource "google_firebase_web_app" "web" {
  provider        = google-beta
  project         = var.project_id
  display_name    = "Open Siddur Builder"
  deletion_policy = "DELETE"
  depends_on      = [google_firebase_project.default]
}
resource "google_identity_platform_config" "auth" {
  project            = var.project_id
  authorized_domains = ["localhost", "${var.project_id}.firebaseapp.com", "${var.project_id}.web.app"]
  sign_in {
    allow_duplicate_emails = false
    phone_number {
      enabled = false
    }
    email {
      enabled           = true
      password_required = false
    }
  }
  depends_on = [google_firebase_project.default]
}
resource "google_identity_platform_default_supported_idp_config" "google" {
  count         = var.google_client_id != "" ? 1 : 0
  enabled       = true
  idp_id        = "google.com"
  client_id     = var.google_client_id
  client_secret = var.google_client_secret
  depends_on    = [google_identity_platform_config.auth]
}
resource "google_cloud_tasks_queue" "queue" {
  for_each = toset(["builder", "previews"])
  name     = each.key
  location = var.region
  rate_limits {
    max_dispatches_per_second = each.key == "previews" ? 2 : 1
    max_concurrent_dispatches = each.key == "previews" ? 2 : 1
  }
  retry_config {
    max_attempts       = 100
    max_retry_duration = "86400s"
    min_backoff        = "10s"
    max_backoff        = "300s"
    max_doublings      = 5
  }
  depends_on = [google_project_service.api]
}
resource "google_project_iam_member" "datastore" {
  for_each = toset(["api", "worker", "dispatcher"])
  project  = var.project_id
  role     = "roles/datastore.user"
  member   = "serviceAccount:${google_service_account.account[each.key].email}"
}
resource "google_storage_bucket_iam_member" "artifacts" {
  for_each = toset(["api", "worker"])
  bucket   = google_storage_bucket.artifacts.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${google_service_account.account[each.key].email}"
}
resource "google_project_iam_member" "api_roles" {
  for_each = toset(["roles/cloudtasks.enqueuer", "roles/firebaseauth.admin", "roles/run.jobsExecutorWithOverrides", "roles/run.viewer"])
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.account["api"].email}"
}
resource "google_service_account_iam_member" "signer" {
  service_account_id = google_service_account.account["worker"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.account["api"].email}"
}
resource "google_service_account_iam_member" "task_identity" {
  service_account_id = google_service_account.account["dispatcher"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.account["api"].email}"
}
resource "google_project_iam_member" "build_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.account["build"].email}"
}
resource "google_storage_bucket_iam_member" "build_source" {
  bucket = google_storage_bucket.builds.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.account["build"].email}"
}
resource "google_project_iam_member" "build_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.account["build"].email}"
}
resource "google_firestore_index" "build_state" {
  collection = "builder_records"
  fields {
    field_path = "kind"
    order      = "ASCENDING"
  }
  fields {
    field_path = "state"
    order      = "ASCENDING"
  }
  depends_on = [google_firestore_database.default]
}
resource "google_firestore_index" "expiry" {
  collection = "builder_records"
  fields {
    field_path = "kind"
    order      = "ASCENDING"
  }
  fields {
    field_path = "expires"
    order      = "ASCENDING"
  }
  depends_on = [google_firestore_database.default]
}
resource "google_storage_bucket_iam_member" "build_bucket_metadata" {
  bucket = google_storage_bucket.builds.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.account["build"].email}"
}
resource "google_firestore_field" "expiry_ttl" {
  collection = "builder_records"
  field      = "expires_at"
  ttl_config {}
  index_config {}
  depends_on = [google_firestore_database.default]
}

resource "google_firebase_hosting_site" "default" {
  provider = google-beta
  project  = var.project_id
  site_id  = var.project_id
  app_id   = google_firebase_web_app.web.app_id
}
resource "google_firebaserules_ruleset" "firestore" {
  provider = google-beta
  project  = var.project_id
  source {
    files {
      name    = "firestore.rules"
      content = "rules_version = '2'; service cloud.firestore { match /databases/{database}/documents { match /{document=**} { allow read, write: if false; } } }"
    }
  }
  depends_on = [google_firebase_project.default]
}
resource "google_firebaserules_release" "firestore" {
  provider     = google-beta
  project      = var.project_id
  name         = "cloud.firestore"
  ruleset_name = google_firebaserules_ruleset.firestore.name
}
