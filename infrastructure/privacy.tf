resource "google_logging_project_exclusion" "share_tokens" {
  name        = "builder-share-token-redaction"
  description = "Do not retain request URLs containing bearer share tokens."
  filter      = "resource.type=\"cloud_run_revision\" AND log_id(\"run.googleapis.com/requests\") AND httpRequest.requestUrl =~ \"/api/v1/shares/\""
}
resource "google_logging_project_bucket_config" "default" {
  project        = var.project_id
  location       = "global"
  bucket_id      = "_Default"
  retention_days = 30
}
