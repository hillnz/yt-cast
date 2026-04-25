provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# ---------------------------------------------------------------------------
# Shared R2 bucket
#
# The bucket is used by both workers: feed-worker writes feed.xml objects and
# dlp-worker writes / streams cached audio.
# ---------------------------------------------------------------------------

resource "cloudflare_r2_bucket" "yt_cast" {
  account_id = var.cloudflare_account_id
  name       = var.bucket_name
  location   = var.bucket_location
}

resource "cloudflare_r2_bucket_lifecycle" "yt_cast" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.yt_cast.name

  rules = [
    {
      id      = "expire-10w"
      enabled = true
      delete_objects_transition = {
        condition = { type = "Age", max_age = 6048000 }
      }
    },
  ]
}

# ---------------------------------------------------------------------------
# Shared Cloudflare Queue
#
# feed-worker is the producer, dlp-worker is the consumer. The producer/
# consumer bindings themselves stay in each worker's wrangler.jsonc and are
# applied by `pywrangler deploy` — TF only owns the queue resource.
# ---------------------------------------------------------------------------

resource "cloudflare_queue" "feed" {
  account_id = var.cloudflare_account_id
  queue_name = var.queue_name
}
