"""Chat responder port and the stub used until the agent lands.

A responder yields the body of one assistant message (text, tool status, citations, usage).
Message framing (`start`/`finish`/`[DONE]`) and error reporting belong to the HTTP layer.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel

from labor_law_agent.stream_events import (
    Citation,
    Citations,
    CitationsPart,
    StreamPart,
    TextDeltaPart,
    TextEndPart,
    TextStartPart,
    ToolStatus,
    ToolStatusPart,
    Usage,
    UsagePart,
)


class ChatTurn(BaseModel):
    message: str
    thread_id: str


class ChatResponder(Protocol):
    def respond(self, turn: ChatTurn) -> AsyncIterator[StreamPart]: ...


_STUB_REPLY = (
    "This is a stubbed reply. The labor-law agent is not wired up yet, "
    "so no article was actually searched."
)


class StubChatResponder:
    """Scripted reply in the final event contract; streams word by word."""

    def __init__(self, delay_seconds: float = 0.05) -> None:
        self._delay = delay_seconds

    async def respond(self, turn: ChatTurn) -> AsyncIterator[StreamPart]:
        yield ToolStatusPart(data=ToolStatus(tool="search_labor_law", state="running"))
        yield ToolStatusPart(data=ToolStatus(tool="search_labor_law", state="done"))
        text_id = "text-1"
        yield TextStartPart(id=text_id)
        words = _STUB_REPLY.split(" ")
        for i, word in enumerate(words):
            await asyncio.sleep(self._delay)
            yield TextDeltaPart(id=text_id, delta=word if i == 0 else f" {word}")
        yield TextEndPart(id=text_id)
        yield CitationsPart(
            data=Citations(citations=[Citation(article_no=1, excerpt="(stub excerpt)")])
        )
        yield UsagePart(data=Usage(input_tokens=0, output_tokens=0, remaining_questions=0))
