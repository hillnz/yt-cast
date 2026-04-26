output "dlp_url" {
  description = "Public HTTPS URI of the dlp Cloud Run service."
  value       = module.dlp.uri
}

output "dlp_service_account_email" {
  description = "Runtime service account email for the dlp Cloud Run service."
  value       = module.dlp.service_account_email
}

output "r2_bucket_name" {
  description = "Name of the shared R2 bucket."
  value       = cloudflare_r2_bucket.yt_cast.name
}

output "r2_public_url" {
  description = "Public base URL serving objects from the R2 bucket via the custom domain."
  value       = local.r2_public_url
}

output "queue_name" {
  description = "Name of the shared Cloudflare Queue."
  value       = cloudflare_queue.feed.queue_name
}

output "feed_worker_name" {
  description = "Name of the deployed feed-worker."
  value       = var.feed_worker_name
}

output "dlp_worker_name" {
  description = "Name of the deployed dlp-worker."
  value       = var.dlp_worker_name
}
