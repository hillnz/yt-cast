FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder

WORKDIR /app

COPY pyproject.toml uv.lock* ./

RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/


FROM python:3.12.13-alpine AS runtime

# ffmpeg (required by yt-dlp for audio extraction / post-processing)
# quickjs (required by yt-dlp-ejs for full YouTube support)
RUN apk add --no-cache ffmpeg quickjs

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app

# Google Drive service account credentials are mounted here.
RUN mkdir -p /config
ENV GOOGLE_APPLICATION_CREDENTIALS="/config/credentials.json"
# Optional: set BEARER_TOKEN to require Authorization: Bearer <token> on all routes.
# When unset, all requests are allowed without authentication.
#ENV BEARER_TOKEN=""
VOLUME ["/config"]

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
