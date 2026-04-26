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

variable "cloudflare_api_token" {
  description = "Cloudflare API token with R2 + Queues + Workers Scripts read/write. Used both by the Cloudflare provider and by pywrangler when deploying the workers."
  type        = string
  sensitive   = true
}

variable "bucket_location" {
  description = "R2 bucket location hint (only honoured on initial creation)."
  type        = string
  default     = "wnam"
  validation {
    condition     = contains(["apac", "eeur", "enam", "weur", "wnam", "oc"], var.bucket_location)
    error_message = "bucket_location must be one of apac, eeur, enam, weur, wnam, oc."
  }
}

variable "r2_public_url" {
  description = "Public base URL serving objects from the R2 bucket (e.g. a custom domain like https://media.example.com). Injected as R2_PUBLIC_URL into the dlp-worker."
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
  description = "Full JSON content of a Google service account key with read access to the Drive folder. Pushed to the dlp-worker as the GOOGLE_SERVICE_ACCOUNT secret AND mounted as the credentials file for the dlp Cloud Run service."
  type        = string
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

variable "repo_root" {
  description = "Path to the repository root containing dlp/, dlp-worker/, feed-worker/. Defaults to the parent of this terraform/ directory."
  type        = string
  default     = null
}
