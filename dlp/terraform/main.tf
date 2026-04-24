locals {
  create_service_account = var.service_account_email == null
  service_account_email  = local.create_service_account ? google_service_account.this[0].email : var.service_account_email

  # Mount the credentials secret as a file when provided. Derive the mount
  # directory and filename from var.credentials_path so the app finds the
  # file at the same location it expects.
  credentials_mount_path = var.credentials_secret_id != null ? dirname(var.credentials_path) : null
  credentials_filename   = var.credentials_secret_id != null ? basename(var.credentials_path) : null

  # Base env vars derived from the dlp Settings model. Values are stringified
  # because Cloud Run env vars are strings; pydantic-settings will coerce.
  base_env = {
    APP_NAME           = var.app_name
    DEBUG              = var.debug ? "true" : "false"
    ALLOWED_ORIGINS    = jsonencode(var.allowed_origins)
    CREDENTIALS_PATH   = var.credentials_path
    DRIVE_FOLDER       = var.drive_folder
    STORAGE_BACKEND    = var.storage_backend
    LOCAL_STORAGE_PATH = var.local_storage_path
    REDOC_ENABLED      = var.redoc_enabled ? "true" : "false"
  }

  # Plain (non-secret) bearer token: only set when provided as a literal and
  # no Secret Manager secret was configured.
  plain_bearer_env = (
    var.bearer_token != null && var.bearer_token_secret_id == null
    ? { BEARER_TOKEN = var.bearer_token }
    : {}
  )

  # When a credentials secret is mounted, point the Google SDK at it.
  google_creds_env = (
    var.credentials_secret_id != null
    ? { GOOGLE_APPLICATION_CREDENTIALS = var.credentials_path }
    : {}
  )

  plain_env = merge(
    local.base_env,
    local.plain_bearer_env,
    local.google_creds_env,
    var.extra_env,
  )

  invoker_members = toset(concat(
    var.allow_unauthenticated ? ["allUsers"] : [],
    var.invokers,
  ))
}

resource "google_service_account" "this" {
  count        = local.create_service_account ? 1 : 0
  project      = var.project_id
  account_id   = var.service_name
  display_name = "Service account for Cloud Run service ${var.service_name}"
}

resource "google_cloud_run_v2_service" "this" {
  project  = var.project_id
  location = var.region
  name     = var.service_name
  ingress  = var.ingress
  labels   = var.labels

  template {
    service_account                  = local.service_account_email
    timeout                          = "${var.timeout_seconds}s"
    max_instance_request_concurrency = var.max_instance_request_concurrency
    execution_environment            = var.execution_environment

    scaling {
      min_instance_count = var.min_instance_count
      max_instance_count = var.max_instance_count
    }

    dynamic "vpc_access" {
      for_each = var.vpc_connector == null ? [] : [1]
      content {
        connector = var.vpc_connector
        egress    = var.vpc_egress
      }
    }

    containers {
      image = var.image

      ports {
        container_port = var.container_port
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = var.cpu_idle
        startup_cpu_boost = var.startup_cpu_boost
      }

      dynamic "env" {
        for_each = local.plain_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.bearer_token_secret_id == null ? [] : [1]
        content {
          name = "BEARER_TOKEN"
          value_source {
            secret_key_ref {
              secret  = var.bearer_token_secret_id
              version = var.bearer_token_secret_version
            }
          }
        }
      }

      dynamic "volume_mounts" {
        for_each = var.credentials_secret_id == null ? [] : [1]
        content {
          name       = "credentials"
          mount_path = local.credentials_mount_path
        }
      }
    }

    dynamic "volumes" {
      for_each = var.credentials_secret_id == null ? [] : [1]
      content {
        name = "credentials"
        secret {
          secret = var.credentials_secret_id
          items {
            version = var.credentials_secret_version
            path    = local.credentials_filename
            mode    = 0400
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = local.invoker_members

  project  = google_cloud_run_v2_service.this.project
  location = google_cloud_run_v2_service.this.location
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = each.value == "allUsers" ? "allUsers" : each.value
}

resource "google_secret_manager_secret_iam_member" "bearer_token_accessor" {
  count = var.bearer_token_secret_id == null ? 0 : 1

  project   = var.project_id
  secret_id = var.bearer_token_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.service_account_email}"
}

resource "google_secret_manager_secret_iam_member" "credentials_accessor" {
  count = var.credentials_secret_id == null ? 0 : 1

  project   = var.project_id
  secret_id = var.credentials_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.service_account_email}"
}
