# Feed Worker

Cloudflare Worker (Python) that accepts feed build requests on
`POST /feed` and enqueues them onto a Cloudflare Queue for downstream
processing.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- [Node.js](https://nodejs.org/) (required by Wrangler)
- A Cloudflare account with Queues enabled

## Setup

```sh
uv sync
uv run pywrangler queues create feed-worker-queue
```

## Development

```sh
uv run pywrangler dev
```

## Deployment

```sh
uv run pywrangler deploy
```

## API

### `POST /feed`

Body:

```json
{ "video_id": "abc123" }
```

| Scenario | Response |
| --- | --- |
| Valid body | `202 Accepted` (message enqueued) |
| Invalid body | `400 Bad Request` (no detail) |

Validation failures deliberately return an opaque `400 Bad Request`
with no information about which field failed or why.
