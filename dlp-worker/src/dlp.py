"""DLP archive service client."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from feed.channel import ChannelData
from feed.item import VideoData
from google_auth import get_id_token


def _error_code(resp: httpx.Response) -> str | None:
    """Extract a discriminator code from a JSON error body, best-effort.

    The DLP service returns ``{"detail": "...", "code": "..."}`` for
    errors it wants the worker to react to specifically. Any non-JSON
    body or missing ``code`` returns None — callers fall back to the
    generic error path."""
    try:
        body = resp.json()
    except (ValueError, TypeError):
        return None
    if isinstance(body, dict):
        code = body.get("code")
        if isinstance(code, str):
            return code
    return None


class DlpError(Exception):
    """Base class for errors raised when talking to the DLP service."""


class DlpNotFoundError(DlpError):
    """Raised when the DLP service returns 404 for a resource."""


class DlpAuthRequiredError(DlpError):
    """Raised when the DLP service signals that YouTube is gating
    requests behind a sign-in (cookies need refreshing). The DLP API
    returns this as a 502 with ``{"code": "youtube_auth_required"}``."""


@dataclass(frozen=True)
class DlpConfig:
    """Configuration for the DLP client, sourced from worker env vars."""

    base_url: str
    service_account_json: str
    timeout: float = 600.0

    @classmethod
    def from_env(cls, env: object) -> "DlpConfig":
        """Build a :class:`DlpConfig` from a Workers ``env`` JsProxy."""
        base_url = str(getattr(env, "DLP_URL", "") or "").rstrip("/")
        if not base_url:
            raise DlpError("DLP_URL env var is not configured")

        sa_raw = getattr(env, "GOOGLE_SERVICE_ACCOUNT", None)
        sa_json = str(sa_raw) if sa_raw else ""
        if not sa_json:
            raise DlpError("GOOGLE_SERVICE_ACCOUNT env var is not configured")

        return cls(base_url=base_url, service_account_json=sa_json)


class DlpClient:
    """Async client for the DLP archive service."""

    def __init__(self, config: DlpConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            headers={"Accept": "application/json"},
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
        resp = await self._client.post(
            "/download",
            json={"video_id": video_id},
            headers=await self._auth_headers(),
        )
        if resp.status_code == httpx.codes.NOT_FOUND:
            raise DlpNotFoundError(f"DLP video not found: {video_id}")
        if resp.status_code >= 400:
            if _error_code(resp) == "youtube_auth_required":
                raise DlpAuthRequiredError(
                    f"DLP reports YouTube auth required for {video_id}"
                )
            raise DlpError(
                f"DLP download error ({resp.status_code}) for {video_id}: {resp.text}"
            )

    # -- internals ---------------------------------------------------------

    async def _auth_headers(self) -> dict[str, str]:
        token = await get_id_token(
            self._config.service_account_json, self._config.base_url
        )
        return {"Authorization": f"Bearer {token}"}

    async def _get_json(self, path: str) -> dict[str, object]:
        resp = await self._client.get(path, headers=await self._auth_headers())

        if resp.status_code == httpx.codes.NOT_FOUND:
            raise DlpNotFoundError(f"DLP resource not found: {path}")

        if resp.status_code >= 400:
            if _error_code(resp) == "youtube_auth_required":
                raise DlpAuthRequiredError(
                    f"DLP reports YouTube auth required for {path}"
                )
            raise DlpError(f"DLP error ({resp.status_code}) for {path}: {resp.text}")

        return resp.json()
