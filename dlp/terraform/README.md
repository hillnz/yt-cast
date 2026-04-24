# dlp Cloud Run Terraform module

A Terraform module that deploys the `dlp` FastAPI service as a [Google Cloud
Run v2 service](https://cloud.google.com/run/docs).

It exposes every setting from `app.config.Settings` as a module input (mapped
to the corresponding environment variable), along with the standard knobs you
need for a Cloud Run deployment: image, scaling, CPU/memory, ingress, IAM,
VPC egress, and Secret Manager wiring for the bearer token and Google service
account credentials.

## Layout

```/dev/null/layout.txt#L1-5
versions.tf   # Terraform / provider requirements
variables.tf  # All module inputs
main.tf       # Cloud Run v2 service + IAM + (optional) service account
outputs.tf    # Service URL, revision names, service account, etc.
```

## Requirements

- Terraform >= 1.5.0
- `hashicorp/google` provider >= 5.0.0
- A built and pushed container image of the `dlp` app (see `../Dockerfile`),
  e.g. in Artifact Registry.
- The following Google APIs enabled in the target project:
  - `run.googleapis.com`
  - `iam.googleapis.com`
  - `secretmanager.googleapis.com` (only if you use the secret inputs)
  - `vpcaccess.googleapis.com` (only if you set `vpc_connector`)

## Usage

Minimal example — public service, app defaults, no secrets:

```/dev/null/example-minimal.tf#L1-12
module "dlp" {
  source = "../dlp/terraform"

  project_id = "my-gcp-project"
  region     = "us-central1"

  image                 = "us-central1-docker.pkg.dev/my-gcp-project/containers/dlp:latest"
  allow_unauthenticated = true
}

output "dlp_url" {
  value = module.dlp.uri
}
```

Recommended example — bearer token and Google credentials sourced from
Secret Manager, only authenticated invokers allowed:

```/dev/null/example-secrets.tf#L1-30
resource "google_secret_manager_secret" "bearer" {
  project   = "my-gcp-project"
  secret_id = "dlp-bearer-token"
  replication { auto {} }
}

resource "google_secret_manager_secret" "creds" {
  project   = "my-gcp-project"
  secret_id = "dlp-gdrive-credentials"
  replication { auto {} }
}

module "dlp" {
  source = "../dlp/terraform"

  project_id   = "my-gcp-project"
  region       = "us-central1"
  service_name = "dlp-archive"

  image = "us-central1-docker.pkg.dev/my-gcp-project/containers/dlp:1.2.3"

  storage_backend = "gdrive"
  drive_folder    = "dlp-archive-prod"
  allowed_origins = ["https://app.example.com"]

  bearer_token_secret_id = google_secret_manager_secret.bearer.secret_id
  credentials_secret_id  = google_secret_manager_secret.creds.secret_id

  invokers = ["serviceAccount:worker@my-gcp-project.iam.gserviceaccount.com"]
}
```

## Inputs

### Cloud Run / infrastructure

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `project_id` | `string` | — | GCP project ID where the service is deployed. |
| `region` | `string` | `"us-central1"` | GCP region for the Cloud Run service. |
| `service_name` | `string` | `"dlp-archive"` | Name of the Cloud Run service (also used as the auto-created service account ID). |
| `image` | `string` | — | Container image URI for the dlp service. |
| `service_account_email` | `string` | `null` | Service account to run the service as. If `null`, the module creates one. |
| `ingress` | `string` | `"INGRESS_TRAFFIC_ALL"` | One of `INGRESS_TRAFFIC_ALL`, `INGRESS_TRAFFIC_INTERNAL_ONLY`, `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`. |
| `allow_unauthenticated` | `bool` | `false` | Grant `roles/run.invoker` to `allUsers`. |
| `invokers` | `list(string)` | `[]` | Additional IAM members granted `roles/run.invoker`. |
| `container_port` | `number` | `8000` | Port the container listens on (matches the Dockerfile). |
| `cpu` | `string` | `"1"` | CPU limit per instance. |
| `memory` | `string` | `"1Gi"` | Memory limit per instance. |
| `min_instance_count` | `number` | `0` | Minimum instances (set > 0 to keep warm). |
| `max_instance_count` | `number` | `3` | Maximum instances. |
| `max_instance_request_concurrency` | `number` | `80` | Concurrent requests per instance. |
| `timeout_seconds` | `number` | `300` | Request timeout. |
| `execution_environment` | `string` | `"EXECUTION_ENVIRONMENT_GEN2"` | `EXECUTION_ENVIRONMENT_GEN1` or `EXECUTION_ENVIRONMENT_GEN2`. |
| `cpu_idle` | `bool` | `true` | Throttle CPU when idle. |
| `startup_cpu_boost` | `bool` | `true` | Boost CPU during startup. |
| `labels` | `map(string)` | `{}` | Labels applied to the service. |
| `vpc_connector` | `string` | `null` | Optional Serverless VPC Access connector for egress. |
| `vpc_egress` | `string` | `"PRIVATE_RANGES_ONLY"` | `ALL_TRAFFIC` or `PRIVATE_RANGES_ONLY`. |

### dlp application settings

These map 1:1 onto fields of `app.config.Settings`. Each variable is
serialised to the corresponding upper-case environment variable that
`pydantic-settings` reads.

| Name | Type | Default | Env var |
| --- | --- | --- | --- |
| `app_name` | `string` | `"dlp-archive"` | `APP_NAME` |
| `debug` | `bool` | `false` | `DEBUG` |
| `allowed_origins` | `list(string)` | `["*"]` | `ALLOWED_ORIGINS` (JSON array) |
| `credentials_path` | `string` | `"/config/credentials.json"` | `CREDENTIALS_PATH` |
| `drive_folder` | `string` | `"dlp-archive"` | `DRIVE_FOLDER` |
| `storage_backend` | `string` | `"gdrive"` | `STORAGE_BACKEND` |
| `local_storage_path` | `string` | `"./archive"` | `LOCAL_STORAGE_PATH` |
| `redoc_enabled` | `bool` | `false` | `REDOC_ENABLED` |
| `bearer_token` | `string` (sensitive) | `null` | `BEARER_TOKEN` (plain env var; ignored if `bearer_token_secret_id` is set) |
| `extra_env` | `map(string)` | `{}` | Arbitrary additional env vars |

### Secret Manager wiring

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `bearer_token_secret_id` | `string` | `null` | Secret ID (short name in `project_id`) holding the bearer token. When set, mounted as the `BEARER_TOKEN` env var via `value_source.secret_key_ref`. |
| `bearer_token_secret_version` | `string` | `"latest"` | Version of the bearer token secret. |
| `credentials_secret_id` | `string` | `null` | Secret ID holding the Google service account credentials JSON. When set, mounted as a file at `credentials_path` and `GOOGLE_APPLICATION_CREDENTIALS` is set accordingly. |
| `credentials_secret_version` | `string` | `"latest"` | Version of the credentials secret. |

When either secret input is provided, the module also grants
`roles/secretmanager.secretAccessor` on that secret to the service's runtime
service account.

## Outputs

| Name | Description |
| --- | --- |
| `service_name` | Name of the Cloud Run service. |
| `service_id` | Fully qualified resource ID. |
| `location` | Service location (region). |
| `uri` | Public HTTPS URI of the service. |
| `latest_ready_revision` | Latest revision that is serving traffic. |
| `latest_created_revision` | Latest revision created. |
| `service_account_email` | Runtime service account email. |
| `service_account_created` | `true` if the module created the service account, `false` if you supplied one. |
