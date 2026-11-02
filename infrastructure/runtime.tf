resource "google_cloud_run_v2_service" "preview" {
  for_each            = local.release_images
  name                = "builder-preview-${substr(each.key, 0, 20)}"
  location            = var.region
  deletion_protection = false
  template {
    service_account                  = google_service_account.account["worker"].email
    timeout                          = "330s"
    max_instance_request_concurrency = 1
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image   = each.value
      command = ["python", "-m", "uvicorn", "opensiddur_infra.worker:preview_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
      resources {
        limits   = { cpu = "2", memory = "4Gi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = merge(local.common_env, { RELEASE_ID = each.key })
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
  depends_on = [google_project_service.api]
}
resource "google_cloud_run_v2_job" "build" {
  for_each            = local.release_images
  name                = "builder-${substr(each.key, 0, 35)}"
  location            = var.region
  deletion_protection = false
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.account["worker"].email
      timeout         = "10800s"
      max_retries     = 0
      containers {
        image   = each.value
        command = ["python", "-m", "opensiddur_infra.worker"]
        resources { limits = { cpu = "2", memory = "4Gi" } }
        dynamic "env" {
          for_each = merge(local.common_env, { RELEASE_ID = each.key })
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }
  lifecycle { create_before_destroy = true }
  depends_on = [google_project_service.api]
}
resource "google_cloud_run_v2_service" "api" {
  count               = local.runtime ? 1 : 0
  name                = "builder-api"
  location            = var.region
  deletion_protection = false
  template {
    service_account                  = google_service_account.account["api"].email
    timeout                          = "55s"
    max_instance_request_concurrency = 8
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image   = var.api_image != "" ? var.api_image : var.image
      command = ["python", "-m", "uvicorn", "opensiddur_infra.api:production_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
      resources {
        limits   = { cpu = "1", memory = "1Gi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = merge(local.common_env, {
          API_URL             = local.api_url
          PREVIEW_URL         = google_cloud_run_v2_service.preview[var.release_id].uri
          BUILD_JOB           = google_cloud_run_v2_job.build[var.release_id].id
          SUBMISSIONS_ENABLED = tostring(var.submissions_enabled)
          REQUIRE_APP_CHECK   = tostring(var.require_app_check)
          ADMIN_EMAILS        = join(",", var.admin_emails)
        })
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
}
resource "google_cloud_run_v2_service_iam_member" "public_api" {
  count    = local.runtime ? 1 : 0
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
resource "google_cloud_run_v2_service_iam_member" "private_preview" {
  for_each = local.release_images
  location = var.region
  name     = google_cloud_run_v2_service.preview[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.account["dispatcher"].email}"
}
resource "google_cloud_scheduler_job" "maintenance" {
  count            = local.runtime ? 1 : 0
  name             = "builder-maintenance"
  region           = var.region
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"
  http_target {
    http_method = "POST"
    uri         = "${local.api_url}/internal/reconcile"
    oidc_token {
      service_account_email = google_service_account.account["dispatcher"].email
      audience              = "https://opensiddur-builder/internal"
    }
  }
}
