provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# ---------------------------------------------------------------------------
# Shared R2 bucket
#
# The bucket is used by both workers: feed-worker writes feed.xml objects and
# dlp-worker writes / streams cached audio. Lifecycle rules below enforce the
# four expire-* prefixes the dlp-worker writes into.
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
      id         = "expire-1d"
      enabled    = true
      conditions = { prefix = "expire-1d/" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 86400 }
      }
    },
    {
      id         = "expire-3d"
      enabled    = true
      conditions = { prefix = "expire-3d/" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 259200 }
      }
    },
    {
      id         = "expire-6d"
      enabled    = true
      conditions = { prefix = "expire-6d/" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 518400 }
      }
    },
    {
      id         = "expire-8w"
      enabled    = true
      conditions = { prefix = "expire-8w/" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 4838400 }
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
