provider "cloudflare" {}

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
      id         = "expire-10w"
      enabled    = true
      conditions = { prefix = "" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 6048000 }
      }
    },
  ]
}

# ---------------------------------------------------------------------------
# Public access via a custom subdomain
#
# Attaches r2_public_hostname (e.g. media.example.com) to the bucket as a
# Cloudflare custom domain. Public reads served via this hostname go through
# the Cloudflare edge cache, so we get free CDN caching and no per-request
# R2 read charges on cache hits.
#
# The companion cache ruleset below tells the edge to cache everything on
# this hostname and respect the origin Cache-Control headers. The dlp-worker
# sets those headers on `put` (audio: 1 day, feed.xml: 5 minutes).
# ---------------------------------------------------------------------------

resource "cloudflare_r2_custom_domain" "yt_cast" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.yt_cast.name
  domain      = var.r2_public_hostname
  zone_id     = var.cloudflare_zone_id
  enabled     = true
  min_tls     = "1.2"
}

# NOTE: Cloudflare allows only one ruleset per (zone, phase). If the zone
# already has a `http_request_cache_settings` ruleset managed elsewhere,
# this will conflict — fold those rules in here instead.
resource "cloudflare_ruleset" "yt_cast_cache" {
  zone_id     = var.cloudflare_zone_id
  name        = "yt-cast-r2-cache"
  description = "Edge caching for the yt-cast R2 custom hostname."
  kind        = "zone"
  phase       = "http_request_cache_settings"

  rules = [
    {
      action      = "set_cache_settings"
      description = "Cache all paths on the yt-cast R2 hostname using origin Cache-Control headers."
      enabled     = true
      expression  = "(http.host eq \"${var.r2_public_hostname}\")"
      action_parameters = {
        cache = true
        edge_ttl = {
          mode = "respect_origin"
        }
        browser_ttl = {
          mode = "respect_origin"
        }
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
