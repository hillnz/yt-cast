from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse, Response
from js import console
from pydantic import BaseModel, Field

app = FastAPI()


class FeedRequest(BaseModel):
    model_config = {"extra": "forbid"}

    video_id: str = Field(min_length=1, max_length=20)


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


@app.post("/feed")
async def handle_feed(payload: FeedRequest, request: Request):
    env = request.scope["env"]
    await env.FEED_QUEUE.send({"video_id": payload.video_id})
    return Response(status_code=202)
