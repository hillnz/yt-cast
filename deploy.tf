terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# ---------------------------------------------------------------------------
# Variables (mirrors terraform/variables.tf)
# ---------------------------------------------------------------------------

variable "gcp_project_id" {
  type = string
}

variable "gcp_region" {
  type    = string
  default = "us-central1"
}

variable "dlp_image" {
  type = string
}

variable "dlp_service_name" {
  type    = string
  default = "dlp-archive"
}

variable "dlp_allow_unauthenticated" {
  type    = bool
  default = true
}

variable "dlp_extra" {
  type    = any
  default = {}
}

variable "cloudflare_account_id" {
  type = string
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "r2_public_hostname" {
  type = string
}

variable "cloudflare_zone_id" {
  type = string
}

variable "feed_worker_name" {
  type    = string
  default = "feed-worker"
}

variable "dlp_worker_name" {
  type    = string
  default = "dlp-worker"
}

variable "drive_root_id" {
  type = string
}

variable "google_service_account_json" {
  type      = string
  sensitive = true
  default   = null
}

variable "repo_root" {
  type    = string
  default = null
}

# ---------------------------------------------------------------------------
# Main module
# ---------------------------------------------------------------------------

module "main" {
  source = "./terraform"

  gcp_project_id              = var.gcp_project_id
  gcp_region                  = var.gcp_region
  dlp_image                   = var.dlp_image
  dlp_service_name            = var.dlp_service_name
  dlp_allow_unauthenticated   = var.dlp_allow_unauthenticated
  dlp_extra                   = var.dlp_extra
  cloudflare_account_id       = var.cloudflare_account_id
  cloudflare_zone_id          = var.cloudflare_zone_id
  r2_public_hostname          = var.r2_public_hostname
  feed_worker_name            = var.feed_worker_name
  dlp_worker_name             = var.dlp_worker_name
  drive_root_id               = var.drive_root_id
  google_service_account_json = var.google_service_account_json
  repo_root                   = var.repo_root
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "dlp_url" {
  description = "Public HTTPS URI of the dlp Cloud Run service."
  value       = module.main.dlp_url
}

output "dlp_service_account_email" {
  description = "Runtime service account email for the dlp Cloud Run service."
  value       = module.main.dlp_service_account_email
}

output "drive_service_account_email" {
  description = "Email of the service account that needs Editor access to the Drive folder identified by drive_root_id. Share that folder with this email."
  value       = module.main.drive_service_account_email
}

output "r2_bucket_name" {
  description = "Name of the shared R2 bucket."
  value       = module.main.r2_bucket_name
}

output "r2_public_url" {
  description = "Public base URL serving objects from the R2 bucket via the custom domain."
  value       = module.main.r2_public_url
}

output "queue_name" {
  description = "Name of the shared Cloudflare Queue."
  value       = module.main.queue_name
}

output "feed_worker_name" {
  description = "Name of the deployed feed-worker."
  value       = module.main.feed_worker_name
}

output "dlp_worker_name" {
  description = "Name of the deployed dlp-worker."
  value       = module.main.dlp_worker_name
}
