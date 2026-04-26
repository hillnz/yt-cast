# ---------------------------------------------------------------------------
# GCP / dlp Cloud Run service
# ---------------------------------------------------------------------------

variable "gcp_project_id" {
  description = "GCP project ID where the dlp Cloud Run service and Secret Manager secrets will live."
  type        = string
}

variable "gcp_region" {
  description = "GCP region for the dlp Cloud Run service."
  type        = string
  default     = "us-central1"
}

variable "dlp_image" {
  description = "Container image URI for the dlp service (e.g. region-docker.pkg.dev/project/repo/dlp:tag)."
  type        = string
}

variable "dlp_service_name" {
  description = "Name of the dlp Cloud Run service. Also used as a prefix for the bearer-token / credentials secrets."
  type        = string
  default     = "dlp-archive"
}

variable "dlp_allow_unauthenticated" {
  description = "Allow unauthenticated invocations of the dlp service. The bearer token still gates access at the application layer; Cloudflare Workers don't have a stable IAM identity, so this is the simplest way to let the dlp-worker reach it."
  type        = bool
  default     = true
}

variable "dlp_extra" {
  description = "Extra inputs forwarded to the inner dlp module (passed through unchanged). Use this to override knobs like cpu, memory, scaling, drive_folder, etc."
  type        = any
  default     = {}
}

# ---------------------------------------------------------------------------
# Cloudflare account + shared infra
# ---------------------------------------------------------------------------

variable "cloudflare_account_id" {
  description = "Cloudflare account ID that owns the R2 bucket, Queue, and Workers."
  type        = string
}

variable "r2_public_hostname" {
  description = "Public hostname for the R2 bucket (e.g. media.example.com). Terraform attaches this as a Cloudflare R2 custom domain on the bucket and adds a zone-level cache rule. The dlp-worker is given https://{hostname} as R2_PUBLIC_URL."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID that owns r2_public_hostname. Required for the R2 custom domain attachment and the cache ruleset."
  type        = string
}

# ---------------------------------------------------------------------------
# Worker config / secrets
# ---------------------------------------------------------------------------

variable "feed_worker_name" {
  description = "Name of the feed-worker. Must match the `name` in feed-worker/wrangler.jsonc."
  type        = string
  default     = "feed-worker"
}

variable "dlp_worker_name" {
  description = "Name of the dlp-worker. Must match the `name` in dlp-worker/wrangler.jsonc."
  type        = string
  default     = "dlp-worker"
}

variable "drive_root_id" {
  description = "Google Drive folder ID the dlp-worker proxies from (DRIVE_ROOT_ID)."
  type        = string
}

variable "google_service_account_json" {
  description = "Full JSON content of a Google service account key with access to the Drive folder. If null (default), Terraform creates a service account and key in `gcp_project_id` — share the Drive folder with the resulting `drive_service_account_email` output. Pushed to the dlp-worker as the GOOGLE_SERVICE_ACCOUNT secret AND mounted as the credentials file for the dlp Cloud Run service."
  type        = string
  sensitive   = true
  default     = null
}

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

variable "repo_root" {
  description = "Path to the repository root containing dlp/, dlp-worker/, feed-worker/. Defaults to the parent of this terraform/ directory."
  type        = string
  default     = null
}
