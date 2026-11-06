variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "Choose dev or prod."
  }
}
variable "image" {
  type    = string
  default = ""
}
variable "api_image" {
  type    = string
  default = ""
}
variable "release_id" {
  type    = string
  default = "bootstrap"
}
variable "submissions_enabled" {
  type    = bool
  default = false
}
variable "require_app_check" {
  type    = bool
  default = true
}
variable "admin_emails" {
  type    = list(string)
  default = []
}
variable "google_client_id" {
  type    = string
  default = ""
}
variable "google_client_secret" {
  type      = string
  sensitive = true
  default   = ""
}
variable "purge_data" {
  type    = bool
  default = false
}

variable "release_images" {
  type    = map(string)
  default = {}
}
variable "billing_account" {
  type    = string
  default = ""
}
