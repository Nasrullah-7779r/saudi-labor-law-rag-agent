"""HTTP API: `POST /chat` (SSE stream) and `GET /health`.

Run behind Lambda Web Adapter in response-stream mode; locally: `uvicorn labor_law_agent.api:app`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from labor_law_agent.chat import ChatResponder, ChatTurn, StubChatResponder
from labor_law_agent.stream_events import (
    SSE_DONE,
    UI_MESSAGE_STREAM_HEADER,
    UI_MESSAGE_STREAM_VERSION,
    ErrorPart,
    FinishPart,
    StartPart,
    encode_sse,
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 2000
MAX_THREAD_ID_CHARS = 128


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    thread_id: str | None = Field(default=None, min_length=1, max_length=MAX_THREAD_ID_CHARS)


class HealthResponse(BaseModel):
    status: str


async def _message_stream(responder: ChatResponder, turn: ChatTurn) -> AsyncIterator[str]:
    yield encode_sse(StartPart(messageId=f"msg-{uuid.uuid4().hex}"))
    try:
        async for part in responder.respond(turn):
            yield encode_sse(part)
    except Exception:
        # Headers (200) are already sent; report the failure in-band.
        logger.exception("chat stream failed", extra={"thread_id": turn.thread_id})
        yield encode_sse(ErrorPart(errorText="Something went wrong. Please try again."))
    yield encode_sse(FinishPart())
    yield SSE_DONE


def create_app(responder: ChatResponder) -> FastAPI:
    app = FastAPI(title="Saudi Labor Law RAG Agent")

    @app.get("/health")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post("/chat")
    async def chat(request: ChatRequest) -> StreamingResponse:
        turn = ChatTurn(message=request.message, thread_id=request.thread_id or uuid.uuid4().hex)
        return StreamingResponse(
            _message_stream(responder, turn),
            media_type="text/event-stream",
            headers={
                UI_MESSAGE_STREAM_HEADER: UI_MESSAGE_STREAM_VERSION,
                "Cache-Control": "no-cache",
                "X-Thread-Id": turn.thread_id,
            },
        )

    return app


app = create_app(StubChatResponder())
