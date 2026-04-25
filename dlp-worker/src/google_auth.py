"""Google service account authentication via Web Crypto FFI.

Mints short-lived Google access tokens using a service account's RSA
private key.  All cryptographic operations use the Web Crypto API
(``crypto.subtle``) accessed through Pyodide's JS FFI — no C-extension
packages required.

Token caching
-------------
Access tokens are valid for one hour.  We cache the token and the
imported ``CryptoKey`` at module level so they survive across requests
within the same isolate, avoiding redundant JWT minting.
"""

import base64
import json
import time
from typing import cast

import httpx
from js import (
    ArrayBuffer,
    CryptoKey,
    TextEncoder,
    TextEncoderInstance,
    crypto,
)

from helpers import to_js

# ---------------------------------------------------------------------------
# Module-level caches (persist across requests within the same isolate)
# ---------------------------------------------------------------------------
_cached_token: str | None = None
_token_expiry: int = 0
_imported_key: CryptoKey | None = None
_key_email: str | None = None

_encoder: TextEncoderInstance = TextEncoder.new()


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
    global _cached_token, _token_expiry, _imported_key, _key_email

    now = int(time.time())
    if _cached_token and now < _token_expiry - 60:
        return _cached_token

    sa = cast(dict[str, str], json.loads(service_account_json))
    email: str = sa["client_email"]
    private_key_pem: str = sa["private_key"]

    # Re-import the CryptoKey only when the service account changes (or on
    # first call).
    if _imported_key is None or _key_email != email:
        _imported_key = await _import_private_key(private_key_pem)
        _key_email = email

    # -- Build JWT --------------------------------------------------------
    header: dict[str, str] = {"alg": "RS256", "typ": "JWT"}
    claims: dict[str, str | int] = {
        "iss": email,
        "scope": "https://www.googleapis.com/auth/drive",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }

    signing_input = (
        f"{_b64url_encode(json.dumps(header))}.{_b64url_encode(json.dumps(claims))}"
    )

    # -- Sign with RS256 via Web Crypto -----------------------------------
    signature: ArrayBuffer = await crypto.subtle.sign(
        "RSASSA-PKCS1-v1_5",
        _imported_key,
        _encoder.encode(signing_input),
    )

    # ``signature`` is a JS ArrayBuffer — convert directly to Python bytes.
    sig_bytes = signature.to_bytes()
    jwt_token = f"{signing_input}.{_b64url_encode(sig_bytes)}"

    # -- Exchange JWT for an access token ---------------------------------
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
