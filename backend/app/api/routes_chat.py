"""Chat endpoint: streams the agent's stages over SSE.

The agent runs as a background task that pushes stage events onto a queue; the
response generator drains the queue and writes SSE frames. If the client
disconnects, the generator stops and cancels the agent task, which cancels any
in-flight query and closes the read-only session — nothing is leaked.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.loop import AgentLoop
from app.agent.providers.factory import get_provider
from app.api.routes_artifacts import get_artifact_store
from app.config import get_settings
from app.db.engine import ReadOnlySession
from app.logging import get_logger

router = APIRouter(prefix="/api")
logger = get_logger("api.chat")

_DONE = object()          # sentinel: agent finished
_HEARTBEAT_SECONDS = 15   # send a comment if idle, and re-check disconnect


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatIn):
    settings = get_settings()
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(stage: str, payload: dict) -> None:
        await queue.put((stage, payload))

    async def drive() -> None:
        try:
            async with ReadOnlySession() as ro_session:
                provider = get_provider(settings)
                agent = AgentLoop(provider, settings, artifacts=get_artifact_store())
                await agent.run(body.message, ro_session, emit)
        except Exception as e:  # never crash the stream; surface a final error stage
            logger.exception("agent_error")
            await queue.put(("error", {"code": "agent_error", "message": str(e)[:200]}))
        finally:
            await queue.put((_DONE, None))

    task = asyncio.create_task(drive())

    async def generate():
        try:
            while True:
                try:
                    stage, payload = await asyncio.wait_for(queue.get(), _HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": ping\n\n"     # heartbeat keeps the connection open
                    continue
                if stage is _DONE:
                    break
                yield _sse(stage, payload)
                if await request.is_disconnected():
                    break
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
