"""HTTP API: `POST /chat` (SSE stream) and `GET /health`.

Run behind Lambda Web Adapter in response-stream mode. Production app: `labor_law_agent.main:app`;
stub app with no AWS access: `uvicorn labor_law_agent.api:app`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from labor_law_agent.chat import ChatResponder, ChatTurn, StubChatResponder
from labor_law_agent.stream_events import (
    SSE_DONE,
    UI_MESSAGE_STREAM_HEADER,
    UI_MESSAGE_STREAM_VERSION,
    ErrorPart,
    FinishPart,
    StartPart,
    UsagePart,
    encode_sse,
)
from labor_law_agent.usage_guard import Admission, QuotaExceeded, QuotaReason, UsageGuard

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 2000
MAX_THREAD_ID_CHARS = 128
# Set by Lambda Web Adapter from the API Gateway event
# (https://aws.github.io/aws-lambda-web-adapter/features/request-context.html).
REQUEST_CONTEXT_HEADER = "x-amzn-request-context"


class ChatRequest(BaseModel):
    # Stripped before the length check, so whitespace-only input is rejected.
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]
    thread_id: str | None = Field(default=None, min_length=1, max_length=MAX_THREAD_ID_CHARS)


class HealthResponse(BaseModel):
    status: Literal["ok"]


class QuotaExceededResponse(BaseModel):
    error: QuotaReason


def _source_ip(request: Request) -> str:
    """API Gateway's `identity.sourceIp`; `X-Forwarded-For` is client-controlled, so ignored.

    Falls back to the socket peer when run without the adapter (local dev, tests).
    """
    raw = request.headers.get(REQUEST_CONTEXT_HEADER)
    if raw:
        try:
            ip = json.loads(raw)["identity"]["sourceIp"]
            if isinstance(ip, str) and ip:
                return ip
        except (ValueError, KeyError, TypeError):
            logger.warning("unparseable request context header")
    return request.client.host if request.client else "unknown"


async def _message_stream(
    responder: ChatResponder,
    turn: ChatTurn,
    guard: UsageGuard | None,
    admission: Admission | None,
) -> AsyncIterator[str]:
    yield encode_sse(StartPart(messageId=f"msg-{uuid.uuid4().hex}"))
    try:
        async for part in responder.respond(turn):
            if isinstance(part, UsagePart) and guard is not None and admission is not None:
                part.data.remaining_questions = admission.remaining_questions
                await asyncio.to_thread(
                    guard.record, part.data.input_tokens + part.data.output_tokens
                )
            yield encode_sse(part)
    except Exception:
        # Headers (200) are already sent; report the failure in-band.
        logger.exception("chat stream failed", extra={"thread_id": turn.thread_id})
        yield encode_sse(ErrorPart(errorText="Something went wrong. Please try again."))
    yield encode_sse(FinishPart())
    yield SSE_DONE


def create_app(responder: ChatResponder, guard: UsageGuard | None = None) -> FastAPI:
    """``guard=None`` disables quotas (stub app, tests that don't exercise them)."""
    app = FastAPI(title="Saudi Labor Law RAG Agent")

    @app.get("/health")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post(
        "/chat", response_model=None, responses={429: {"model": QuotaExceededResponse}}
    )
    async def chat(
        request: ChatRequest, http_request: Request
    ) -> StreamingResponse | JSONResponse:
        admission: Admission | None = None
        if guard is not None:
            try:
                admission = await asyncio.to_thread(guard.admit, _source_ip(http_request))
            except QuotaExceeded as e:
                return JSONResponse(
                    status_code=429, content=QuotaExceededResponse(error=e.reason).model_dump()
                )
        turn = ChatTurn(message=request.message, thread_id=request.thread_id or uuid.uuid4().hex)
        return StreamingResponse(
            _message_stream(responder, turn, guard, admission),
            media_type="text/event-stream",
            headers={
                UI_MESSAGE_STREAM_HEADER: UI_MESSAGE_STREAM_VERSION,
                "Cache-Control": "no-cache",
                "X-Thread-Id": turn.thread_id,
            },
        )

    return app


app = create_app(StubChatResponder())
