# Google Drive → Cloudflare Proxy

Cloudflare Worker (Python) that proxies files from a specific Google Drive folder,
caching them in R2 for subsequent requests.

## Architecture

```
Client ──▶ Worker ──▶ R2 hit? ──▶ stream file from R2
                        │
                        ▼ (miss)
                   fetch from Drive ──▶ write to R2 ──▶ stream from R2
```

On a cache miss the worker fetches the file from Google Drive, streams it into R2,
then serves it from R2.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Node.js](https://nodejs.org/) (required by Wrangler under the hood)
- A Cloudflare account
- A Google Cloud service account with access to the target Drive folder

## Setup

### 1. Install dependencies

```sh
uv sync
```

This installs `workers-py` (which provides `pywrangler`) and `workers-runtime-sdk`
for type hints.

### 2. Create the R2 bucket

```sh
uv run pywrangler r2 bucket create dlp-worker-cache
```

### 3. Configure variables

Edit `wrangler.jsonc` and set `DRIVE_ROOT_ID` to the Google Drive folder ID you
want to serve files from. The folder ID is the last segment of the folder's URL:

```
https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ
                                        └──────── this part ────────┘
```

### 4. Set secrets

```sh
# Google Cloud service account JSON key
# (paste the entire JSON contents when prompted)
uv run pywrangler secret put GOOGLE_SERVICE_ACCOUNT
```

#### Google service account setup

1. Create a service account in your GCP project.
2. Create a JSON key for the service account.
3. Share the target Google Drive folder with the service account's email address
   (grant at least **Viewer** access).
4. Store the full JSON key as the `GOOGLE_SERVICE_ACCOUNT` secret (above).

### 5. R2 lifecycle rules (required)

Cached video objects are written under one of four prefixes, chosen at download
time based on the age of the YouTube video. Each prefix needs a matching
"delete after N days" lifecycle rule on the R2 bucket — without these rules
nothing is ever deleted.

| Prefix | Applies to videos uploaded… | Retention |
| --- | --- | --- |
| `expire-1d/` | within the last 3 days | 1 day |
| `expire-3d/` | within the last 7 days | 3 days |
| `expire-6d/` | within the last 14 days | 6 days |
| `expire-8w/` | older than 14 days | 56 days |

When a video ages past a bucket boundary the next feed rebuild re-downloads
it into the new bucket; the stale copy is deleted by the previous bucket's
lifecycle rule.

Configure the rules via the Cloudflare dashboard
(**R2 → yt-cast → Settings → Object lifecycle rules**) or the API. Example
using `wrangler`:

```sh
uv run pywrangler r2 bucket lifecycle add yt-cast --id expire-1d \
  --prefix expire-1d/ --expire-days 1
uv run pywrangler r2 bucket lifecycle add yt-cast --id expire-3d \
  --prefix expire-3d/ --expire-days 3
uv run pywrangler r2 bucket lifecycle add yt-cast --id expire-6d \
  --prefix expire-6d/ --expire-days 6
uv run pywrangler r2 bucket lifecycle add yt-cast --id expire-8w \
  --prefix expire-8w/ --expire-days 56
```

`feed.xml` documents live at `{feed_id}/feed.xml` (no `expire-*` prefix) and
are unaffected by these rules.

## Development

```sh
uv run pywrangler dev
```

This starts a local development server. R2 is simulated locally via Miniflare.

## Deployment

```sh
uv run pywrangler deploy
```

## Usage

```sh
curl https://dlp-worker.<your-subdomain>.workers.dev/path/to/file.pdf
```

The request path maps directly to the folder structure inside the configured
Google Drive root folder. For example, if your Drive folder contains:

```
My Folder/
  reports/
    2025/
      summary.pdf
```

Then the request path would be `/reports/2025/summary.pdf`.

### Response behaviour

| Scenario | Response |
| --- | --- |
| File cached in R2 | Streams from R2 (fast) |
| Cache miss, file exists in Drive | Downloads → caches → streams from R2 |
| Cache miss, file not found in Drive | `404 Not Found` |
| Download fails | `502 Bad Gateway` with error detail |

## Project structure

```
dlp-worker/
├── src/
│   ├── entry.py          # Cloudflare event handling (thin shell)
│   ├── handler.py        # Core request handling logic
│   ├── google_auth.py    # JWT signing (Web Crypto FFI) + token exchange
│   ├── drive.py          # Google Drive API client
│   └── helpers.py        # FFI utilities
├── wrangler.jsonc        # Cloudflare Worker configuration
├── pyproject.toml        # Python project configuration
├── .python-version       # Python version pin (3.12)
├── plan.md               # Original design document
└── README.md             # This file
```

## How it works

### Google authentication

The worker mints short-lived Google access tokens using the service account's
RSA private key. JWT signing is done via the Web Crypto API (`crypto.subtle`)
accessed through Pyodide's FFI — no native C extensions needed. Tokens are
cached in module scope (reused across requests within the same isolate).

### Streaming

Files are streamed end-to-end without buffering the entire content in memory:

- **Drive → R2:** `CACHE.put(key, driveResponse.body)` pipes the `ReadableStream`
  directly into R2 storage.
- **R2 → Client:** `CACHE.get(key).body` returns a `ReadableStream` that is set
  as the response body.

This keeps memory usage constant regardless of file size, well within the
128 MB Worker isolate limit.

## Limitations

- **Google Docs native formats** (Sheets, Docs, Slides) cannot be downloaded
  directly via `alt=media`. Only regular files (PDFs, images, etc.) are supported.
- **Path resolution** requires one Drive API call per path segment on cache miss.
  Deeply nested paths add latency.
- **Python Workers are in beta** — the `python_workers` compatibility flag is
  required.
