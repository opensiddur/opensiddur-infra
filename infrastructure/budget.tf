data "google_project" "current" { project_id = var.project_id }
resource "google_project_service" "budgets" {
  count              = var.billing_account != "" ? 1 : 0
  service            = "billingbudgets.googleapis.com"
  disable_on_destroy = false
}
resource "google_billing_budget" "builder" {
  count           = var.billing_account != "" ? 1 : 0
  billing_account = var.billing_account
  display_name    = "Open Siddur ${var.environment}: $10/$25/$50 alerts"
  budget_filter { projects = ["projects/${data.google_project.current.number}"] }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = "50"
    }
  }
  threshold_rules { threshold_percent = 0.2 }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 1.0 }
  depends_on = [google_project_service.budgets]
}
