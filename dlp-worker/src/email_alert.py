"""Operator alerts via the Cloudflare Email Routing ``send_email`` binding.

Used by the consumer when the dlp service signals that YouTube has gated
its requests behind a sign-in: the operator gets one email prompting
them to run ``scripts/refresh-yt-cookies``.

Best-effort throughout — every failure mode is logged and swallowed so
alerting can never crash the queue consumer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage as PyEmailMessage

from js import console
from pyodide.ffi import JsProxy
from workers import import_from_javascript

# Suppress duplicate alerts of the same kind for this long. A stuck queue
# can otherwise generate one email per retry per video; the operator only
# needs to be told once until they've had a chance to refresh cookies.
_DEFAULT_DEDUP_HOURS = 6.0

# R2 key prefix for alert dedup state. One file per alert id.
_DEDUP_KEY_PREFIX = "alerts/last_sent/"

_YOUTUBE_AUTH_ALERT_ID = "youtube_auth_required"
_YOUTUBE_AUTH_SUBJECT = "yt-cast: YouTube cookies need refreshing"
_YOUTUBE_AUTH_BODY = (
    "The dlp service is being blocked by YouTube's bot check.\n"
    "\n"
    "Run scripts/refresh-yt-cookies to push a fresh cookies file to\n"
    "Secret Manager, then redeploy the dlp service (or wait for the\n"
    "current Cloud Run instance to scale to zero) so the new cookies\n"
    "are picked up.\n"
)


def _env_str(env: JsProxy, name: str) -> str:
    return str(getattr(env, name, "") or "")


def _dedup_window(env: JsProxy) -> timedelta:
    raw = _env_str(env, "ALERT_DEDUP_HOURS")
    if not raw:
        return timedelta(hours=_DEFAULT_DEDUP_HOURS)
    try:
        return timedelta(hours=float(raw))
    except ValueError:
        return timedelta(hours=_DEFAULT_DEDUP_HOURS)


async def _was_recently_alerted(
    env: JsProxy, alert_id: str, window: timedelta
) -> bool:
    obj = await env.STORAGE.get(_DEDUP_KEY_PREFIX + alert_id)
    if not obj:
        return False
    text = await obj.text()
    try:
        last = datetime.fromisoformat(str(text).strip())
    except ValueError:
        return False
    return datetime.now(timezone.utc) - last < window


async def _record_alert_sent(env: JsProxy, alert_id: str) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    await env.STORAGE.put(_DEDUP_KEY_PREFIX + alert_id, now_iso)


async def send_youtube_auth_alert(env: JsProxy) -> None:
    """Email the operator that YouTube cookies need refreshing.

    Skips the send if dedup state shows a recent alert, if the email
    routing config is missing, or if the binding call fails. Errors are
    logged and never raised — the caller should keep processing.
    """
    try:
        sender = _env_str(env, "ALERT_EMAIL_FROM")
        recipient = _env_str(env, "ALERT_EMAIL_TO")
        if not sender or not recipient:
            console.warn(
                "Skipping YouTube auth alert: "
                "ALERT_EMAIL_FROM / ALERT_EMAIL_TO not configured"
            )
            return

        if await _was_recently_alerted(
            env, _YOUTUBE_AUTH_ALERT_ID, _dedup_window(env)
        ):
            console.log("YouTube auth alert suppressed (within dedup window)")
            return

        msg = PyEmailMessage()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = _YOUTUBE_AUTH_SUBJECT
        msg.set_content(_YOUTUBE_AUTH_BODY)

        cf_email = import_from_javascript("cloudflare:email")
        email_message = cf_email.EmailMessage.new(sender, recipient, msg.as_string())
        await env.ALERT_MAIL.send(email_message)

        await _record_alert_sent(env, _YOUTUBE_AUTH_ALERT_ID)
        console.log(f"Sent YouTube auth alert to {recipient}")
    except Exception as exc:  # noqa: BLE001 — alerting must not crash consumer
        console.error(f"Failed to send YouTube auth alert: {exc}")
