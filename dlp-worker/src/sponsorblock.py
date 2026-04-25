"""SponsorBlock API client + segment-hash helper.

We hit ``GET /api/skipSegments`` to discover which timestamps yt-dlp
will strip out, then hash those timestamps. The hash is stored in R2
custom metadata so a later run can detect when the segments have
changed and a re-download is needed.
"""

from __future__ import annotations

import hashlib
import json

import httpx

# Categories must mirror the ones the dlp container passes to yt-dlp's
# SponsorBlock postprocessor (see dlp/app/ytdl.py: download_audio).
SEGMENT_CATEGORIES: tuple[str, ...] = ("sponsor", "selfpromo")

_SPONSORBLOCK_BASE_URL = "https://sponsor.ajay.app"


class SponsorBlockError(Exception):
    """Raised when the SponsorBlock API can't be queried."""


async def fetch_segment_timestamps(
    client: httpx.AsyncClient,
    video_id: str,
    *,
    categories: tuple[str, ...] = SEGMENT_CATEGORIES,
) -> list[tuple[float, float]]:
    """Return ``(start, end)`` pairs for *video_id*.

    A 404 from SponsorBlock means "no segments for this video" and yields
    an empty list. Any other error raises :class:`SponsorBlockError`.
    """
    params: dict[str, str | list[str]] = {
        "videoID": video_id,
        "category": list(categories),
    }
    try:
        resp = await client.get(
            f"{_SPONSORBLOCK_BASE_URL}/api/skipSegments", params=params
        )
    except httpx.HTTPError as exc:
        raise SponsorBlockError(
            f"SponsorBlock request failed for {video_id}: {exc}"
        ) from exc

    if resp.status_code == httpx.codes.NOT_FOUND:
        return []
    if resp.status_code >= 400:
        raise SponsorBlockError(
            f"SponsorBlock error ({resp.status_code}) for {video_id}: {resp.text}"
        )

    payload = resp.json()
    if not isinstance(payload, list):
        raise SponsorBlockError(
            f"SponsorBlock returned non-list payload for {video_id}"
        )

    timestamps: list[tuple[float, float]] = []
    for entry in payload:
        segment = entry.get("segment") if isinstance(entry, dict) else None
        if not isinstance(segment, list) or len(segment) != 2:
            continue
        try:
            start = float(segment[0])
            end = float(segment[1])
        except (TypeError, ValueError):
            continue
        timestamps.append((start, end))

    return timestamps


def hash_segment_timestamps(timestamps: list[tuple[float, float]]) -> str:
    """Stable SHA-256 hex digest for a list of ``(start, end)`` pairs.

    Order-independent: pairs are sorted before hashing so the same set of
    segments always hashes to the same value, regardless of API ordering.
    """
    pairs = sorted(timestamps)
    canonical = json.dumps(pairs, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
