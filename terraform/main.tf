provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

locals {
  repo_root     = var.repo_root != null ? var.repo_root : "${path.module}/.."
  r2_public_url = "https://${var.r2_public_hostname}"
}

# ---------------------------------------------------------------------------
# Generated secrets (state-managed; same value re-pushed to all consumers)
# ---------------------------------------------------------------------------

resource "random_password" "feed_id_secret" {
  length  = 48
  special = false
}

# ---------------------------------------------------------------------------
# GCP Secret Manager: Drive credentials for the dlp service
# ---------------------------------------------------------------------------

resource "google_service_account" "drive" {
  count = var.google_service_account_json == null ? 1 : 0

  project      = var.gcp_project_id
  account_id   = "${var.dlp_service_name}-drive"
  display_name = "${var.dlp_service_name} Drive access"
}

resource "google_service_account_key" "drive" {
  count = var.google_service_account_json == null ? 1 : 0

  service_account_id = google_service_account.drive[0].name
}

resource "google_project_service" "iamcredentials" {
  count = length(var.dlp_local_invoker_users) > 0 ? 1 : 0

  project            = var.gcp_project_id
  service            = "iamcredentials.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account_iam_member" "drive_local_invokers" {
  for_each = length(google_service_account.drive) > 0 ? toset(var.dlp_local_invoker_users) : toset([])

  service_account_id = google_service_account.drive[0].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${each.value}"

  depends_on = [google_project_service.iamcredentials]
}

locals {
  google_service_account_json = (
    var.google_service_account_json != null
    ? var.google_service_account_json
    : base64decode(google_service_account_key.drive[0].private_key)
  )
  drive_service_account_email = nonsensitive(
    var.google_service_account_json != null
    ? jsondecode(var.google_service_account_json).client_email
    : google_service_account.drive[0].email
  )
}

resource "google_secret_manager_secret" "google_credentials" {
  project   = var.gcp_project_id
  secret_id = "${var.dlp_service_name}-gdrive-credentials"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "google_credentials" {
  secret      = google_secret_manager_secret.google_credentials.id
  secret_data = local.google_service_account_json
}

# ---------------------------------------------------------------------------
# GCP Secret Manager: YouTube cookies for the dlp service
#
# Created empty here so the secret exists for IAM and the Cloud Run mount.
# Versions are pushed manually via scripts/refresh-yt-cookies (it runs a
# fresh Firefox profile, you sign in, and the script extracts cookies and
# `gcloud secrets versions add`s them). The Cloud Run mount uses
# version = "latest", so a refresh takes effect on the next cold start.
#
# When no version exists yet (first apply), Cloud Run will fail to start;
# push a version with the script before the first invocation.
# ---------------------------------------------------------------------------

resource "google_secret_manager_secret" "yt_cookies" {
  project   = var.gcp_project_id
  secret_id = "${var.dlp_service_name}-yt-cookies"

  replication {
    auto {}
  }
}

# ---------------------------------------------------------------------------
# dlp Cloud Run service (delegated to the existing dlp/terraform module)
# ---------------------------------------------------------------------------

module "dlp" {
  source = "../dlp/terraform"

  project_id   = var.gcp_project_id
  region       = var.gcp_region
  service_name = var.dlp_service_name
  image        = var.dlp_image

  allow_unauthenticated = var.dlp_allow_unauthenticated

  # The dlp-worker (running on Cloudflare) authenticates to Cloud Run by
  # minting Google ID tokens using this same service account JSON, so the
  # Drive SA needs roles/run.invoker on the dlp service.
  invokers = ["serviceAccount:${local.drive_service_account_email}"]

  credentials_secret_id      = google_secret_manager_secret.google_credentials.secret_id
  credentials_secret_version = google_secret_manager_secret_version.google_credentials.version

  yt_cookies_secret_id = google_secret_manager_secret.yt_cookies.secret_id

  storage_backend = "gdrive"

  # Pass-through overrides for any other dlp module input.
  app_name           = try(var.dlp_extra.app_name, var.dlp_service_name)
  debug              = try(var.dlp_extra.debug, false)
  allowed_origins    = try(var.dlp_extra.allowed_origins, ["*"])
  drive_folder       = try(var.dlp_extra.drive_folder, "dlp-archive")
  redoc_enabled      = try(var.dlp_extra.redoc_enabled, false)
  cpu                = try(var.dlp_extra.cpu, "1")
  memory             = try(var.dlp_extra.memory, "1Gi")
  min_instance_count = try(var.dlp_extra.min_instance_count, 0)
  max_instance_count = try(var.dlp_extra.max_instance_count, 3)
  timeout_seconds    = try(var.dlp_extra.timeout_seconds, 300)
  labels             = try(var.dlp_extra.labels, {})
  extra_env          = try(var.dlp_extra.extra_env, {})
}
