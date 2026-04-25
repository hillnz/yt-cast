"""DLP archive service client."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from feed.channel import ChannelData
from feed.item import VideoData


class DlpError(Exception):
    """Base class for errors raised when talking to the DLP service."""


class DlpNotFoundError(DlpError):
    """Raised when the DLP service returns 404 for a resource."""


@dataclass(frozen=True)
class DlpConfig:
    """Configuration for the DLP client, sourced from worker env vars."""

    base_url: str
    bearer_token: str | None = None
    timeout: float = 600.0

    @classmethod
    def from_env(cls, env: object) -> "DlpConfig":
        """Build a :class:`DlpConfig` from a Workers ``env`` JsProxy."""
        base_url = str(getattr(env, "DLP_URL", "") or "").rstrip("/")
        if not base_url:
            raise DlpError("DLP_URL env var is not configured")

        token_raw = getattr(env, "DLP_BEARER_TOKEN", None)
        token = str(token_raw) if token_raw else None
        return cls(base_url=base_url, bearer_token=token or None)


class DlpClient:
    """Async client for the DLP archive service."""

    def __init__(self, config: DlpConfig) -> None:
        self._config = config
        headers: dict[str, str] = {"Accept": "application/json"}
        if config.bearer_token:
            headers["Authorization"] = f"Bearer {config.bearer_token}"

        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            headers=headers,
            timeout=config.timeout,
        )

    async def __aenter__(self) -> "DlpClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- endpoints ---------------------------------------------------------

    async def get_channel(self, channel_id: str) -> ChannelData:
        """GET ``/channel/{channel_id}``."""
        return await self._get_json(f"/channel/{channel_id}")  # type: ignore[return-value]

    async def get_video(self, video_id: str) -> VideoData:
        """GET ``/video/{video_id}``."""
        return await self._get_json(f"/video/{video_id}")  # type: ignore[return-value]

    async def download_video(self, video_id: str) -> None:
        """POST ``/download`` to make DLP archive *video_id* to its store."""
        resp = await self._client.post("/download", json={"video_id": video_id})
        if resp.status_code == httpx.codes.NOT_FOUND:
            raise DlpNotFoundError(f"DLP video not found: {video_id}")
        if resp.status_code >= 400:
            raise DlpError(
                f"DLP download error ({resp.status_code}) for {video_id}: {resp.text}"
            )

    # -- internals ---------------------------------------------------------

    async def _get_json(self, path: str) -> dict[str, object]:
        resp = await self._client.get(path)

        if resp.status_code == httpx.codes.NOT_FOUND:
            raise DlpNotFoundError(f"DLP resource not found: {path}")

        if resp.status_code >= 400:
            raise DlpError(f"DLP error ({resp.status_code}) for {path}: {resp.text}")

        return resp.json()
