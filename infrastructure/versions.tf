terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    google      = { source = "hashicorp/google", version = "~> 7.0" }
    google-beta = { source = "hashicorp/google-beta", version = "~> 7.0" }
  }
  backend "gcs" {}
}
provider "google" {
  user_project_override = true
  billing_project       = var.project_id
  project               = var.project_id
  region                = var.region
}

provider "google-beta" {
  user_project_override = true
  billing_project       = var.project_id
  project               = var.project_id
  region                = var.region
}
