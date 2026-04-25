from __future__ import annotations

from js import console
from pyodide.ffi import JsProxy
from workers import WorkerEntrypoint

from consumer import process_message

__all__ = ["Default"]


class Default(WorkerEntrypoint):
    """Consumes feed-build messages from the feed-worker queue."""

    async def queue(self, batch: JsProxy) -> None:
        for message in batch.messages:
            try:
                await process_message(self.env, message.body)
                message.ack()
            except Exception as exc:  # noqa: BLE001 — consumer must not crash batch
                console.error(f"Queue message failed: {exc}")
                message.retry()
