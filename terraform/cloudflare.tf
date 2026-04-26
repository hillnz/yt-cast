provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# ---------------------------------------------------------------------------
# Shared R2 bucket
#
# The bucket is used by both workers: feed-worker writes feed.xml objects and
# dlp-worker writes / streams cached audio.
#
# The name is hardcoded here and in both workers' wrangler.jsonc files.
# Wrangler doesn't support variable substitution for R2 bucket bindings, so
# keeping it in sync with a terraform variable would give a false sense of
# flexibility — change one and the binding silently breaks. Keep them in
# lockstep manually.
# ---------------------------------------------------------------------------

resource "cloudflare_r2_bucket" "yt_cast" {
  account_id = var.cloudflare_account_id
  name       = "yt-cast"
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
#
# Same caveat as the bucket above: the queue name is hardcoded in both
# wrangler.jsonc files, so we hardcode it here too.
# ---------------------------------------------------------------------------

resource "cloudflare_queue" "feed" {
  account_id = var.cloudflare_account_id
  queue_name = "feed-worker-queue"
}
