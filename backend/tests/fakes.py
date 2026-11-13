"""Test doubles. Not shipped in the package."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Iterable, Iterator
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from labor_law_agent.chat import ChatTurn
from labor_law_agent.ingest.parser import Article
from labor_law_agent.retrieval import RetrievedArticle
from labor_law_agent.stream_events import StreamPart, TextStartPart

_TOKEN = re.compile(r"\w+")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text)}


class InMemoryLawRetriever:
    """LawRetriever fake: token-overlap ranking, ties broken by article number."""

    def __init__(self, articles: Iterable[Article]) -> None:
        self._articles = list(articles)

    def search(self, query: str, k: int = 4) -> list[RetrievedArticle]:
        q = _tokens(query)
        scored = [(len(q & _tokens(a.text_ar)) / (len(q) or 1), a) for a in self._articles]
        scored = [s for s in scored if s[0] > 0]
        scored.sort(key=lambda s: (-s[0], s[1].article_no))
        return [
            RetrievedArticle(
                article_no=a.article_no, chapter=a.chapter, text_ar=a.text_ar, score=score
            )
            for score, a in scored[:k]
        ]


class FailingChatResponder:
    """ChatResponder fake: streams one text part, then raises mid-stream."""

    async def respond(self, turn: ChatTurn) -> AsyncIterator[StreamPart]:
        yield TextStartPart(id="text-1")
        raise RuntimeError("boom")


class ScriptedChatModel(BaseChatModel):
    """Chat model fake replaying scripted ``AIMessage``s, one per model call.

    Streams content word by word, then a final chunk carrying tool calls and usage metadata
    (what real providers do), so the agent sees the same shape as in production.
    A script entry that is an ``Exception`` is raised instead.
    """

    script: list[AIMessage | Exception]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:  # type: ignore[override]
        return self

    def _next(self) -> AIMessage:
        entry = self.script[self.calls]
        self.calls += 1
        if isinstance(entry, Exception):
            raise entry
        return entry

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next())])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        message = self._next()
        text = message.content if isinstance(message.content, str) else ""
        for piece in re.findall(r"\S+\s*", text):
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=[
                    ToolCallChunk(name=c["name"], args=json.dumps(c["args"]), id=c["id"], index=i)
                    for i, c in enumerate(message.tool_calls)
                ],
                usage_metadata=message.usage_metadata,
                chunk_position="last",
            )
        )
