output "service_name" {
  description = "Name of the Cloud Run service."
  value       = google_cloud_run_v2_service.this.name
}

output "service_id" {
  description = "Fully qualified ID of the Cloud Run service."
  value       = google_cloud_run_v2_service.this.id
}

output "location" {
  description = "Location of the Cloud Run service."
  value       = google_cloud_run_v2_service.this.location
}

output "uri" {
  description = "Public URI of the Cloud Run service."
  value       = google_cloud_run_v2_service.this.uri
}

output "latest_ready_revision" {
  description = "Name of the latest ready revision."
  value       = google_cloud_run_v2_service.this.latest_ready_revision
}

output "latest_created_revision" {
  description = "Name of the latest created revision."
  value       = google_cloud_run_v2_service.this.latest_created_revision
}

output "service_account_email" {
  description = "Email of the service account used by the Cloud Run service."
  value       = local.service_account_email
}

output "service_account_created" {
  description = "Whether this module created the service account."
  value       = local.create_service_account
}
