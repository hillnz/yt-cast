from __future__ import annotations

from js import console
from pyodide.ffi import JsProxy
from workers import WorkerEntrypoint

from consumer import PermanentMessageError, process_message

__all__ = ["Default"]


class Default(WorkerEntrypoint):
    """Consumes feed-build messages from the feed-worker queue."""

    async def queue(self, batch: JsProxy) -> None:
        for message in batch.messages:
            try:
                await process_message(self.env, message.body)
                message.ack()
            except PermanentMessageError as exc:
                # Won't succeed on retry — drop and move on.
                console.error(f"Dropping queue message (permanent failure): {exc}")
                message.ack()
            except Exception as exc:  # noqa: BLE001 — consumer must not crash batch
                # Treat unknown failures as transient and let the queue's
                # retry policy (max_retries / retry_delay in wrangler.jsonc)
                # decide when to give up.
                console.error(f"Queue message failed (will retry): {exc}")
                message.retry()
