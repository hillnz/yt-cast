variable "project_id" {
  description = "GCP project ID where the Cloud Run service will be deployed."
  type        = string
}

variable "region" {
  description = "GCP region for the Cloud Run service."
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Name of the Cloud Run service."
  type        = string
  default     = "dlp-archive"
}

variable "image" {
  description = "Container image URI for the dlp service (e.g. region-docker.pkg.dev/project/repo/dlp:tag)."
  type        = string
}

variable "service_account_email" {
  description = "Email of the service account to run the Cloud Run service as. If null, a service account will be created."
  type        = string
  default     = null
}

variable "ingress" {
  description = "Ingress traffic settings for the service."
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
  validation {
    condition = contains([
      "INGRESS_TRAFFIC_ALL",
      "INGRESS_TRAFFIC_INTERNAL_ONLY",
      "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER",
    ], var.ingress)
    error_message = "ingress must be one of INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY, INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER."
  }
}

variable "allow_unauthenticated" {
  description = "Whether to allow unauthenticated invocations of the service (binds roles/run.invoker to allUsers)."
  type        = bool
  default     = false
}

variable "invokers" {
  description = "Additional IAM members granted roles/run.invoker on the service (e.g. [\"serviceAccount:foo@bar.iam.gserviceaccount.com\"])."
  type        = list(string)
  default     = []
}

variable "container_port" {
  description = "Port the container listens on."
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "CPU allocation for each container instance (e.g. \"1\", \"2\", \"4\")."
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memory allocation for each container instance (e.g. \"512Mi\", \"1Gi\", \"2Gi\")."
  type        = string
  default     = "1Gi"
}

variable "min_instance_count" {
  description = "Minimum number of container instances."
  type        = number
  default     = 0
}

variable "max_instance_count" {
  description = "Maximum number of container instances."
  type        = number
  default     = 3
}

variable "max_instance_request_concurrency" {
  description = "Maximum number of concurrent requests per container instance."
  type        = number
  default     = 80
}

variable "timeout_seconds" {
  description = "Request timeout in seconds for the Cloud Run service."
  type        = number
  default     = 300
}

variable "execution_environment" {
  description = "Execution environment for the service (gen1 or gen2)."
  type        = string
  default     = "EXECUTION_ENVIRONMENT_GEN2"
  validation {
    condition     = contains(["EXECUTION_ENVIRONMENT_GEN1", "EXECUTION_ENVIRONMENT_GEN2"], var.execution_environment)
    error_message = "execution_environment must be EXECUTION_ENVIRONMENT_GEN1 or EXECUTION_ENVIRONMENT_GEN2."
  }
}

variable "cpu_idle" {
  description = "Whether CPU is throttled when there are no active requests (true = CPU only allocated during requests)."
  type        = bool
  default     = true
}

variable "startup_cpu_boost" {
  description = "Whether to boost CPU during container startup."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Labels to apply to the Cloud Run service."
  type        = map(string)
  default     = {}
}

variable "vpc_connector" {
  description = "Optional Serverless VPC Access connector ID (projects/*/locations/*/connectors/*) for egress."
  type        = string
  default     = null
}

variable "vpc_egress" {
  description = "VPC egress setting when vpc_connector is set."
  type        = string
  default     = "PRIVATE_RANGES_ONLY"
  validation {
    condition     = contains(["ALL_TRAFFIC", "PRIVATE_RANGES_ONLY"], var.vpc_egress)
    error_message = "vpc_egress must be ALL_TRAFFIC or PRIVATE_RANGES_ONLY."
  }
}

# ---------------------------------------------------------------------------
# dlp application settings (mapped to env vars for app.config.Settings)
# ---------------------------------------------------------------------------

variable "app_name" {
  description = "Application name (APP_NAME)."
  type        = string
  default     = "dlp-archive"
}

variable "debug" {
  description = "Enable debug mode (DEBUG)."
  type        = bool
  default     = false
}

variable "allowed_origins" {
  description = "CORS allowed origins (ALLOWED_ORIGINS). Serialised as a JSON array for pydantic-settings."
  type        = list(string)
  default     = ["*"]
}

variable "credentials_path" {
  description = "Path inside the container to the Google service account credentials file (CREDENTIALS_PATH)."
  type        = string
  default     = "/config/credentials.json"
}

variable "drive_folder" {
  description = "Google Drive folder used for archived content (DRIVE_FOLDER)."
  type        = string
  default     = "dlp-archive"
}

variable "storage_backend" {
  description = "Storage backend to use (STORAGE_BACKEND), e.g. \"gdrive\" or \"local\"."
  type        = string
  default     = "gdrive"
}

variable "local_storage_path" {
  description = "Path used by the local storage backend (LOCAL_STORAGE_PATH)."
  type        = string
  default     = "./archive"
}

variable "redoc_enabled" {
  description = "Whether the ReDoc UI is enabled (REDOC_ENABLED)."
  type        = bool
  default     = false
}

variable "credentials_secret_id" {
  description = "Optional Secret Manager secret ID (short name, in the same project) holding the Google service account credentials JSON. When set, it is mounted as a file at credentials_path and GOOGLE_APPLICATION_CREDENTIALS is set accordingly."
  type        = string
  default     = null
}

variable "credentials_secret_version" {
  description = "Version of the credentials secret to mount."
  type        = string
  default     = "latest"
}

variable "yt_cookies_path" {
  description = "Path inside the container to the Netscape-format YouTube cookies file (YT_COOKIES_PATH). yt-dlp reads this when it exists, allowing authenticated access to videos that block anonymous traffic from cloud IPs. Must be in a directory distinct from credentials_path because Cloud Run rejects overlapping volume mounts."
  type        = string
  default     = "/cookies/cookies.txt"
}

variable "yt_cookies_secret_id" {
  description = "Optional Secret Manager secret ID (short name, in the same project) holding the YouTube cookies file (Netscape format). When set, it is mounted at yt_cookies_path and YT_COOKIES_PATH is exported to the app."
  type        = string
  default     = null
}

variable "yt_cookies_secret_version" {
  description = "Version of the cookies secret to mount. Defaults to \"latest\" so refreshing the secret picks up on the next cold start without redeploying."
  type        = string
  default     = "latest"
}

variable "extra_env" {
  description = "Additional environment variables to inject into the container."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# Tailscale sidecar (optional)
#
# When tailscale_exit_node is set, a tailscale userspace container is added
# to the Cloud Run service. It exposes a SOCKS5 proxy on localhost that the
# dlp container is configured to use via YTDL_PROXY, so yt-dlp egress flows
# through the tailnet exit node instead of Google's IP ranges.
# ---------------------------------------------------------------------------

variable "tailscale_exit_node" {
  description = "Tailscale exit node hostname or IP. When set, the tailscale sidecar is enabled and yt-dlp is routed through its SOCKS5 proxy. tailscale_auth_key_secret_id must also be set."
  type        = string
  default     = null
}

variable "tailscale_auth_key_secret_id" {
  description = "Secret Manager secret ID (short name, in the same project) holding the Tailscale auth key. Required when tailscale_exit_node is set. Use a reusable + ephemeral key so cold-started instances can authenticate without manual intervention."
  type        = string
  default     = null
}

variable "tailscale_auth_key_secret_version" {
  description = "Version of the tailscale auth key secret to mount."
  type        = string
  default     = "latest"
}

variable "tailscale_image" {
  description = "Container image for the tailscale sidecar."
  type        = string
  default     = "ghcr.io/tailscale/tailscale:stable"
}

variable "tailscale_hostname" {
  description = "Hostname tailscale registers on the tailnet. Defaults to the Cloud Run service name."
  type        = string
  default     = null
}

variable "tailscale_socks5_port" {
  description = "Port the tailscale sidecar exposes its SOCKS5 proxy on (loopback only)."
  type        = number
  default     = 1055
}

variable "tailscale_cpu" {
  description = "CPU allocation for the tailscale sidecar. Cloud Run requires the per-container limits to sum to a valid instance total — bump var.cpu/memory if you change this."
  type        = string
  default     = "1"
}

variable "tailscale_memory" {
  description = "Memory allocation for the tailscale sidecar."
  type        = string
  default     = "512Mi"
}
