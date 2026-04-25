from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse, Response
from js import console
from pydantic import BaseModel, Field

from ytcast_shared import get_feed_id

app = FastAPI()


class FeedRequest(BaseModel):
    model_config = {"extra": "forbid"}

    channel: str = Field(min_length=1, max_length=20)


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    # Intentionally opaque: do not leak which field failed or why.
    return PlainTextResponse("Bad Request", status_code=400)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    console.error(f"Unhandled error: {exc}")
    return PlainTextResponse(f"Internal server error: {exc}", status_code=500)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _feed_path(feed_id: str):
    return f"{feed_id}/feed.xml"


@app.post("/feed")
async def create_feed(payload: FeedRequest, request: Request):
    env = request.scope["env"]
    await env.FEED_QUEUE.send({"channel": payload.channel})
    feed_id = get_feed_id(payload.channel, str(env.FEED_ID_SECRET))
    return {"feed_id": feed_id}


@app.get("/feed/{feed_id}")
async def get_feed(feed_id: str, request: Request):
    env = request.scope["env"]
    obj = await env.STORAGE.get(_feed_path(feed_id))
    if obj is None:
        return Response(status_code=404)
    await env.FEED_QUEUE.send({"feed_id": feed_id})
    content = await obj.text()
    return Response(content=content, media_type="application/xml")
