"""Deterministic feed ID derivation."""

from __future__ import annotations

import base64
import hashlib
import hmac

_FEED_ID_BYTES = 10


def get_feed_id(channel: str, secret: str) -> str:
    """Return a deterministic feed ID

    Truncated HMAC-SHA256 keyed with ``secret`` — not reversible, not
    high-security, just hard enough to guess that callers must POST
    /feed to obtain one. Encoded as unpadded URL-safe base64.
    """
    digest = hmac.new(
        secret.encode("utf-8"),
        channel.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return (
        base64.urlsafe_b64encode(digest[:_FEED_ID_BYTES]).rstrip(b"=").decode("ascii")
    )
