# Google Drive → Cloudflare Proxy

Cloudflare Worker (Python) that proxies files from a specific Google Drive folder,
caching them in R2 for subsequent requests. A Durable Object coordinates concurrent
requests to prevent duplicate downloads.

## Architecture

```
Client ──▶ Worker ──▶ R2 hit? ──▶ stream file from R2
                        │
                        ▼ (miss)
                   Durable Object (coordinator)
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
          downloader           waiter(s)
        (fetches Drive,      (hold on WS,
         streams to R2)     serve from R2 when done)
```

On a cache miss the first request becomes the **downloader** — it fetches the file
from Google Drive, streams it into R2, and notifies the coordinator. Any concurrent
requests for the same file become **waiters** — they hold a WebSocket open to the
coordinator and serve from R2 once the download completes.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Node.js](https://nodejs.org/) (required by Wrangler under the hood)
- A Cloudflare account (for Durable Objects)
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
uv run pywrangler r2 bucket create drive-proxy-cache
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

### 5. R2 lifecycle rule (optional)

To automatically expire cached files after a set number of days, configure an R2
lifecycle rule:

```sh
# Example: expire objects after 30 days
uv run pywrangler r2 bucket lifecycle set drive-proxy-cache \
  --rule '{"id":"expire-30d","enabled":true,"conditions":{"age":30},"action":"Delete"}'
```

Or configure via the Cloudflare dashboard under **R2 → drive-proxy-cache → Settings → Object lifecycle rules**.

## Development

```sh
uv run pywrangler dev
```

This starts a local development server. Note that Durable Objects and R2 are
simulated locally via Miniflare.

## Deployment

```sh
uv run pywrangler deploy
```

## Usage

```sh
curl https://drive-proxy.<your-subdomain>.workers.dev/path/to/file.pdf
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
| Download in progress by another request | Waits for download to finish, then streams from R2 |
| Download fails | `502 Bad Gateway` with error detail |

## Project structure

```
drive-proxy/
├── src/
│   ├── entry.py          # Cloudflare event handling (thin shell)
│   ├── coordinator.py    # Coordinator Durable Object (WebSocket Hibernation)
│   ├── handler.py        # Core request handling logic
│   ├── google_auth.py    # JWT signing (Web Crypto FFI) + token exchange
│   ├── drive.py          # Google Drive API client
│   └── helpers.py        # FFI utilities + WebSocket client wrapper
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

### Durable Object coordination

The `Coordinator` DO uses the **WebSocket Hibernation API** so it incurs no
billing while idle. It assigns exactly one downloader per file and holds all
concurrent requests as waiters until the download completes (or fails).

## Limitations

- **Google Docs native formats** (Sheets, Docs, Slides) cannot be downloaded
  directly via `alt=media`. Only regular files (PDFs, images, etc.) are supported.
- **Path resolution** requires one Drive API call per path segment on cache miss.
  Deeply nested paths add latency.
- **Python Workers are in beta** — the `python_workers` compatibility flag is
  required.
