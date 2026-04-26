# feed-worker

Cloudflare Worker (Python) that:

- accepts feed-build requests on `POST /feed`, enqueueing them onto
  the `feed-worker-queue` Cloudflare Queue for `dlp-worker` to consume; and
- serves the resulting `feed.xml` documents on `GET /feed/{feed_id}`,
  re-enqueueing a refresh request as a side-effect.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- [Node.js](https://nodejs.org/) (required by Wrangler)
- A Cloudflare account with Queues enabled

## Setup

This worker is deployed by the top-level `terraform/` module, which also
creates the queue and R2 bucket. To run locally:

```sh
uv sync
uv run pywrangler dev
```

## Deployment

Normally via `terraform apply`. To deploy manually:

```sh
uv run pywrangler deploy
```

## API

### `POST /feed`

Request body:

```json
{ "channel": "<youtube-channel-handle-or-id>" }
```

`channel` is required, 1–20 characters.

| Scenario     | Response                                           |
| ------------ | -------------------------------------------------- |
| Valid body   | `200 OK` with `{ "feed_id": "<id>" }`              |
| Invalid body | `400 Bad Request` (no detail)                      |

The `feed_id` is a deterministic HMAC of `channel` and the
`FEED_ID_SECRET`, so the same channel always resolves to the same id.
The actual feed build happens asynchronously on the queue — clients
should poll `GET /feed/{feed_id}` until it returns `200`.

Validation failures deliberately return an opaque `400 Bad Request`
with no information about which field failed.

### `GET /feed/{feed_id}`

| Scenario           | Response                                       |
| ------------------ | ---------------------------------------------- |
| Feed exists in R2  | `200 OK`, `application/xml`, RSS body          |
| Feed not yet built | `404 Not Found`                                |

A successful read also enqueues a queue message asking `dlp-worker`
to refresh the feed if it is older than the per-feed throttle window.

## Bindings

- `STORAGE` — R2 bucket (`yt-cast` by default)
- `FEED_QUEUE` — producer for `feed-worker-queue`

## Secrets

- `FEED_ID_SECRET` — HMAC key shared with `dlp-worker` so both services
  derive the same `feed_id` for a given channel.
