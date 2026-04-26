# ---------------------------------------------------------------------------
# Worker deploys
#
# The Cloudflare provider has no clean way to attach secrets to a script that
# was not also created by TF, and Python workers aren't bundle-able by the
# provider directly, so we keep `pywrangler deploy` as the deploy mechanism
# and let TF orchestrate it through a null_resource. Triggers are file/value
# hashes so that any change to source, wrangler config, runtime vars, or
# secret values forces a redeploy on the next apply.
# ---------------------------------------------------------------------------

locals {
  feed_worker_dir = "${local.repo_root}/feed-worker"
  dlp_worker_dir  = "${local.repo_root}/dlp-worker"
  shared_dir      = "${local.repo_root}/shared"

  # Files whose contents should bust the deploy cache. We hash src/, the
  # wrangler config, the python project files, and the shared package.
  feed_worker_tracked = setunion(
    fileset(local.feed_worker_dir, "src/**"),
    [
      for f in ["wrangler.jsonc", "pyproject.toml", "uv.lock"] :
      f if fileexists("${local.feed_worker_dir}/${f}")
    ],
  )
  dlp_worker_tracked = setunion(
    fileset(local.dlp_worker_dir, "src/**"),
    [
      for f in ["wrangler.jsonc", "pyproject.toml", "uv.lock"] :
      f if fileexists("${local.dlp_worker_dir}/${f}")
    ],
  )
  shared_tracked = fileset(local.shared_dir, "src/**")

  feed_worker_src_hash = sha1(join("", concat(
    [for f in local.feed_worker_tracked : filesha1("${local.feed_worker_dir}/${f}")],
    [for f in local.shared_tracked : filesha1("${local.shared_dir}/${f}")],
  )))
  dlp_worker_src_hash = sha1(join("", concat(
    [for f in local.dlp_worker_tracked : filesha1("${local.dlp_worker_dir}/${f}")],
    [for f in local.shared_tracked : filesha1("${local.shared_dir}/${f}")],
  )))

  dlp_worker_runtime_vars = {
    DRIVE_ROOT_ID = var.drive_root_id
    DLP_URL       = module.dlp.uri
    R2_PUBLIC_URL = local.r2_public_url
  }
}

resource "null_resource" "feed_worker_deploy" {
  triggers = {
    src     = local.feed_worker_src_hash
    secrets = sha1(random_password.feed_id_secret.result)
  }

  provisioner "local-exec" {
    working_dir = local.feed_worker_dir
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      uv sync
      uv run pywrangler deploy
      printf '%s' "$FEED_ID_SECRET" | uv run pywrangler secret put FEED_ID_SECRET
    EOT
    environment = {
      CLOUDFLARE_ACCOUNT_ID = var.cloudflare_account_id
      FEED_ID_SECRET        = random_password.feed_id_secret.result
    }
  }

  depends_on = [
    cloudflare_r2_bucket.yt_cast,
    cloudflare_queue.feed,
  ]
}

resource "null_resource" "dlp_worker_deploy" {
  triggers = {
    src  = local.dlp_worker_src_hash
    vars = sha1(jsonencode(local.dlp_worker_runtime_vars))
    secrets = sha1(jsonencode({
      bearer = random_password.dlp_bearer_token.result
      feed   = random_password.feed_id_secret.result
      gsa    = local.google_service_account_json
    }))
  }

  provisioner "local-exec" {
    working_dir = local.dlp_worker_dir
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      uv sync
      uv run pywrangler deploy \
        --var "DRIVE_ROOT_ID:$DRIVE_ROOT_ID" \
        --var "DLP_URL:$DLP_URL" \
        --var "R2_PUBLIC_URL:$R2_PUBLIC_URL"
      printf '%s' "$DLP_BEARER_TOKEN"       | uv run pywrangler secret put DLP_BEARER_TOKEN
      printf '%s' "$FEED_ID_SECRET"         | uv run pywrangler secret put FEED_ID_SECRET
      printf '%s' "$GOOGLE_SERVICE_ACCOUNT" | uv run pywrangler secret put GOOGLE_SERVICE_ACCOUNT
    EOT
    environment = {
      CLOUDFLARE_ACCOUNT_ID  = var.cloudflare_account_id
      DRIVE_ROOT_ID          = var.drive_root_id
      DLP_URL                = module.dlp.uri
      R2_PUBLIC_URL          = local.r2_public_url
      DLP_BEARER_TOKEN       = random_password.dlp_bearer_token.result
      FEED_ID_SECRET         = random_password.feed_id_secret.result
      GOOGLE_SERVICE_ACCOUNT = local.google_service_account_json
    }
  }

  depends_on = [
    cloudflare_r2_bucket.yt_cast,
    cloudflare_r2_custom_domain.yt_cast,
    cloudflare_queue.feed,
    module.dlp,
  ]
}
