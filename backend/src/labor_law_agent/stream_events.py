"""Chat stream event contract (wire format of `POST /chat`).

Follows the AI SDK UI "UI message stream" protocol (SSE, `x-vercel-ai-ui-message-stream: v1`),
https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol . Project-specific payloads use its custom
`data-*` part types. See docs/stream-protocol.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

UI_MESSAGE_STREAM_HEADER = "x-vercel-ai-ui-message-stream"
UI_MESSAGE_STREAM_VERSION = "v1"
SSE_DONE = "data: [DONE]\n\n"

# camelCase fields (messageId, errorText) are the protocol's wire names; keep them.


class StartPart(BaseModel):
    type: Literal["start"] = "start"
    messageId: str


class TextStartPart(BaseModel):
    type: Literal["text-start"] = "text-start"
    id: str


class TextDeltaPart(BaseModel):
    type: Literal["text-delta"] = "text-delta"
    id: str
    delta: str


class TextEndPart(BaseModel):
    type: Literal["text-end"] = "text-end"
    id: str


class ToolStatus(BaseModel):
    tool: Literal["search_labor_law", "calc_end_of_service"]
    state: Literal["running", "done"]


class ToolStatusPart(BaseModel):
    type: Literal["data-tool-status"] = "data-tool-status"
    data: ToolStatus


class Citation(BaseModel):
    article_no: int
    excerpt: str


class Citations(BaseModel):
    citations: list[Citation]


class CitationsPart(BaseModel):
    type: Literal["data-citations"] = "data-citations"
    data: Citations


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    remaining_questions: int


class UsagePart(BaseModel):
    type: Literal["data-usage"] = "data-usage"
    data: Usage


class ErrorPart(BaseModel):
    type: Literal["error"] = "error"
    errorText: str


class FinishPart(BaseModel):
    type: Literal["finish"] = "finish"


StreamPart = (
    StartPart
    | TextStartPart
    | TextDeltaPart
    | TextEndPart
    | ToolStatusPart
    | CitationsPart
    | UsagePart
    | ErrorPart
    | FinishPart
)


def encode_sse(part: StreamPart) -> str:
    """One SSE event: `data: <json>` followed by a blank line."""
    return f"data: {part.model_dump_json()}\n\n"
