mock_provider "google" {}
mock_provider "google-beta" {}

variables {
  project_id  = "opensiddur-policy-test"
  environment = "dev"
  release_id  = "policy-test"
  image       = "us-central1-docker.pkg.dev/opensiddur-policy-test/builder/worker@sha256:0000000000000000000000000000000000000000000000000000000000000000"
}

run "user_data_retention" {
  command = plan

  assert {
    condition     = google_firestore_database.default.point_in_time_recovery_enablement == "POINT_IN_TIME_RECOVERY_DISABLED"
    error_message = "Unused Firestore recovery must remain disabled."
  }
  assert {
    condition = alltrue([
      for bucket in [google_storage_bucket.artifacts, google_storage_bucket.builds] :
      !one(bucket.versioning).enabled && one(bucket.soft_delete_policy).retention_duration_seconds == 0
    ])
    error_message = "User object versioning and soft deletion must remain disabled."
  }
  assert {
    condition = alltrue(flatten([
      for bucket in [google_storage_bucket.artifacts, google_storage_bucket.builds] : [
        for rule in bucket.lifecycle_rule : [for condition in rule.condition : condition.age <= 30]
      ]
    ]))
    error_message = "User object retention must never exceed 30 days."
  }
  assert {
    condition = anytrue([
      for rule in google_storage_bucket.artifacts.lifecycle_rule :
      one(rule.condition).age == 1 && contains(one(rule.condition).matches_prefix, "exports/")
    ])
    error_message = "Generated account ZIPs must expire after 24 hours."
  }
  assert {
    condition     = one(one(google_cloud_run_v2_job.data[0].template).template).timeout == "3600s"
    error_message = "Data job timeout must remain below the 65-minute erasure lease."
  }
  assert {
    condition     = google_logging_project_bucket_config.default.retention_days <= 30
    error_message = "Operational logs must not be retained above 30 days."
  }
}
