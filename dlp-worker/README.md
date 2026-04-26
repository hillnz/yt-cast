# dlp-worker

Cloudflare Worker (Python) that rebuilds podcast feeds in response to
messages on the `feed-worker-queue` Cloudflare Queue. It is the consumer
half of the pair; the producer is `feed-worker`.

## Architecture

```
feed-worker (HTTP) ──▶ feed-worker-queue ──▶ dlp-worker (consumer)
                                                  │
                                                  ▼
                          ┌───────────────────────┴───────────────────────┐
                          │                                               │
                  GET /channel + /video                          POST /download
                  on dlp service                                 on dlp service
                          │                                               │
                          │                                  dlp uploads audio to Drive
                          ▼                                               │
                  channel + video metadata                                ▼
                          │                                Drive ──▶ R2 (`{feed_id}/{video_id}`)
                          └───────────────────────┬───────────────────────┘
                                                  ▼
                                  build feed.xml ──▶ R2 (`{feed_id}/feed.xml`)
```

Per message the worker:

1. Resolves the message to `(feed_id, channel_id)`.
2. Throttles: if the stored feed was rebuilt less than an hour ago, exits.
3. Fetches channel + video metadata from the dlp service.
4. For each video, checks SponsorBlock segments. If the cached audio in R2
   is missing or the segment hash has changed, calls `dlp /download` (which
   archives the audio to Google Drive), then streams the file from Drive
   into R2 and deletes the Drive copy.
5. Builds `feed.xml` and writes it to R2 alongside `channelId` /
   `lastBuilt` custom metadata.

## Configuration

This worker is deployed by the top-level `terraform/` module. Vars and
secrets are pushed at deploy time.

### Vars (set by terraform via `pywrangler deploy --var`)

| Name             | Purpose                                                   |
| ---------------- | --------------------------------------------------------- |
| `DRIVE_ROOT_ID`  | Drive folder ID where the dlp service uploads audio       |
| `DLP_URL`        | Base URL of the dlp Cloud Run service                     |
| `R2_PUBLIC_URL`  | Public base URL of the R2 bucket (used in feed enclosures)|

### Secrets (set by terraform via `pywrangler secret put`)

| Name                     | Purpose                                                  |
| ------------------------ | -------------------------------------------------------- |
| `DLP_BEARER_TOKEN`       | Auth token for the dlp service                           |
| `FEED_ID_SECRET`         | HMAC key shared with feed-worker for stable feed IDs     |
| `GOOGLE_SERVICE_ACCOUNT` | JSON key used to read/delete Drive files                 |

### Bindings (in `wrangler.jsonc`)

- `STORAGE` — R2 bucket (`yt-cast` by default)
- Queue consumer of `feed-worker-queue` with `max_retries=3`, `retry_delay=60s`.
  Messages that exhaust retries are dropped (no DLQ).

## Local development

```sh
uv sync
uv run pywrangler dev
```

`pywrangler dev` runs the worker against simulated R2 and queue locally
(Miniflare). To exercise the consumer end-to-end you also need a
running `dlp` service and the relevant vars/secrets set in the local
environment.

## Deployment

Normally handled by `terraform apply` from the repo root. To deploy
manually (vars / secrets must already be configured on the worker):

```sh
uv run pywrangler deploy
```

## Project structure

```
dlp-worker/
├── src/
│   ├── entry.py          # Worker entrypoint; queue() handler
│   ├── consumer.py       # Per-message orchestration
│   ├── dlp.py            # Client for the dlp Cloud Run service
│   ├── download.py       # DLP → Drive → R2 audio pipeline
│   ├── drive.py          # Google Drive API client
│   ├── google_auth.py    # Service-account JWT signing (Web Crypto FFI)
│   ├── sponsorblock.py   # SponsorBlock segment fetch + hash
│   ├── feed_builder.py   # RSS XML construction
│   ├── feed_io.py        # R2 reads/writes for feed.xml
│   ├── feed/             # Channel/video data models
│   └── helpers.py        # FFI utilities
├── wrangler.jsonc
└── pyproject.toml
```
