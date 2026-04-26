"""Google service account authentication via Web Crypto FFI.

Mints short-lived Google access tokens (Drive scope) and identity
tokens (for invoking IAM-protected Cloud Run services) using a service
account's RSA private key.  All cryptographic operations use the Web
Crypto API (``crypto.subtle``) accessed through Pyodide's JS FFI — no
C-extension packages required.

Token caching
-------------
Tokens are valid for one hour.  We cache them and the imported
``CryptoKey`` at module level so they survive across requests within
the same isolate, avoiding redundant JWT minting.
"""

from __future__ import annotations

import base64
import json
import time
from typing import TYPE_CHECKING, cast

import httpx
from js import (
    ArrayBuffer,
    CryptoKey,
    TextEncoder,
    crypto,
)

from helpers import to_js

if TYPE_CHECKING:
    from js import TextEncoderInstance

# ---------------------------------------------------------------------------
# Module-level caches (persist across requests within the same isolate)
# ---------------------------------------------------------------------------
_cached_token: str | None = None
_token_expiry: int = 0
_imported_key: CryptoKey | None = None
_key_email: str | None = None

# ID tokens are audience-specific, so cache per-audience.
_id_token_cache: dict[str, tuple[str, int]] = {}

# Lazily constructed: the dedicated snapshot taken at deploy time can't
# serialise JS proxies, so we can't hold a TextEncoder instance at module
# level.  Instantiated on first use within a request.
_encoder: TextEncoderInstance | None = None


def _get_encoder() -> TextEncoderInstance:
    global _encoder
    if _encoder is None:
        _encoder = TextEncoder.new()
    return _encoder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes | str) -> str:
    """Base64url-encode *data* without padding."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


async def _import_private_key(pem: str) -> CryptoKey:
    """Import a PKCS#8 PEM private key for RS256 signing via Web Crypto.

    Returns a ``CryptoKey`` (JsProxy) suitable for ``crypto.subtle.sign``.
    """
    # Strip PEM armour and whitespace to get raw base-64
    pem_body = (
        pem.replace("-----BEGIN PRIVATE KEY-----", "")
        .replace("-----END PRIVATE KEY-----", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace(" ", "")
    )
    der_bytes = base64.b64decode(pem_body)

    return await crypto.subtle.importKey(
        "pkcs8",
        to_js(der_bytes),
        to_js({"name": "RSASSA-PKCS1-v1_5", "hash": {"name": "SHA-256"}}),
        False,
        to_js(["sign"]),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def _ensure_key(email: str, private_key_pem: str) -> CryptoKey:
    """Return the cached imported private key, importing it if needed."""
    global _imported_key, _key_email
    if _imported_key is None or _key_email != email:
        _imported_key = await _import_private_key(private_key_pem)
        _key_email = email
    return _imported_key


async def _sign_jwt(key: CryptoKey, claims: dict[str, str | int]) -> str:
    """Sign *claims* with *key* using RS256 and return the compact JWT."""
    header: dict[str, str] = {"alg": "RS256", "typ": "JWT"}
    signing_input = (
        f"{_b64url_encode(json.dumps(header))}.{_b64url_encode(json.dumps(claims))}"
    )
    signature: ArrayBuffer = await crypto.subtle.sign(
        "RSASSA-PKCS1-v1_5",
        key,
        _get_encoder().encode(signing_input),
    )
    return f"{signing_input}.{_b64url_encode(signature.to_bytes())}"


async def get_access_token(service_account_json: str) -> str:
    """Return a cached or freshly minted Google OAuth2 access token.

    Parameters
    ----------
    service_account_json:
        The raw JSON string of a GCP service account key (the value of
        the ``GOOGLE_SERVICE_ACCOUNT`` secret).

    The token is cached at module level.  If the cached token is still
    valid (with a 60-second safety margin) it is returned immediately.
    """
    global _cached_token, _token_expiry

    now = int(time.time())
    if _cached_token and now < _token_expiry - 60:
        return _cached_token

    sa = cast(dict[str, str], json.loads(service_account_json))
    key = await _ensure_key(sa["client_email"], sa["private_key"])

    jwt_token = await _sign_jwt(key, {
        "iss": sa["client_email"],
        "scope": "https://www.googleapis.com/auth/drive",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt_token,
            },
        )

    if resp.status_code != httpx.codes.OK:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    _cached_token = str(data["access_token"])

    expires_in = 3600
    try:
        expires_in = int(data.get("expires_in", 3600))
    except (ValueError, TypeError):
        pass

    _token_expiry = now + expires_in
    return _cached_token


async def get_id_token(service_account_json: str, audience: str) -> str:
    """Return a cached or freshly minted Google ID token for *audience*.

    Used to invoke IAM-protected Cloud Run services. The audience must
    match the service's URL (no trailing slash). The signed JWT carries
    ``target_audience`` so Google's token endpoint returns an ID token
    rather than an access token.
    """
    now = int(time.time())
    cached = _id_token_cache.get(audience)
    if cached and now < cached[1] - 60:
        return cached[0]

    sa = cast(dict[str, str], json.loads(service_account_json))
    key = await _ensure_key(sa["client_email"], sa["private_key"])

    jwt_token = await _sign_jwt(key, {
        "iss": sa["client_email"],
        "target_audience": audience,
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": jwt_token,
            },
        )

    if resp.status_code != httpx.codes.OK:
        raise RuntimeError(
            f"ID token exchange failed ({resp.status_code}): {resp.text}"
        )

    id_token = str(resp.json()["id_token"])
    # Google ID tokens are valid for 1h. We don't parse the JWT exp here —
    # cache for 55 min and let the safety margin handle clock skew.
    _id_token_cache[audience] = (id_token, now + 3300)
    return id_token
