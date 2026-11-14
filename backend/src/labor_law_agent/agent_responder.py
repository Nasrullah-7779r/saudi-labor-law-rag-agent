"""ChatResponder backed by the agent graph: maps LangGraph stream chunks to stream parts.

Uses ``astream(stream_mode=["messages", "updates"], version="v2")``
(https://docs.langchain.com/oss/python/langchain/streaming): ``messages`` chunks carry token
deltas (``AIMessageChunk``) with the producing node in metadata; ``updates`` chunks carry the
completed ``AIMessage`` (with ``tool_calls`` and ``usage_metadata``) from the ``model`` node and
``ToolMessage``s from the ``tools`` node.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any, cast, get_args

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from labor_law_agent.agent import SEARCH_TOOL_NAME
from labor_law_agent.chat import ChatTurn
from labor_law_agent.reasoning_filter import ThinkingFilter
from labor_law_agent.retrieval import RetrievedArticle
from labor_law_agent.stream_events import (
    Citation,
    Citations,
    CitationsPart,
    StreamPart,
    TextDeltaPart,
    TextEndPart,
    TextStartPart,
    ToolName,
    ToolStatus,
    ToolStatusPart,
    Usage,
    UsagePart,
)

MODEL_NODE = "model"
TOOLS_NODE = "tools"
EXCERPT_CHARS = 300
_KNOWN_TOOLS: tuple[str, ...] = get_args(ToolName)
# "Article 84" / "المادة 84" / "المادة ٨٤", the citation forms the system prompt asks for.
_CITED_ARTICLE_RE = re.compile(r"(?:Article|Art\.|المادة)\s*([0-9٠-٩]+)", re.IGNORECASE)
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _cited_article_numbers(answer: str) -> set[int]:
    return {int(m.translate(_ARABIC_INDIC)) for m in _CITED_ARTICLE_RE.findall(answer)}


def _excerpt(text: str) -> str:
    return text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS].rstrip() + "…"


class AgentChatResponder:
    """Streams one agent run as text, tool-status, citation and usage parts."""

    def __init__(self, agent: CompiledStateGraph[Any]) -> None:
        self._agent = agent

    async def respond(self, turn: ChatTurn) -> AsyncIterator[StreamPart]:
        text_id: str | None = None
        text_count = 0
        cited: dict[int, RetrievedArticle] = {}  # best-scoring hit per article
        input_tokens = output_tokens = 0
        answer: list[str] = []
        thinking = ThinkingFilter()  # one per model turn

        def open_or_continue_text(visible: str) -> list[StreamPart]:
            """Parts for visible text; a text part is opened only once there is text."""
            nonlocal text_id, text_count
            if not visible:
                return []
            parts: list[StreamPart] = []
            if text_id is None:
                text_count += 1
                text_id = f"text-{text_count}"
                parts.append(TextStartPart(id=text_id))
            answer.append(visible)
            parts.append(TextDeltaPart(id=text_id, delta=visible))
            return parts

        async for chunk in self._agent.astream(
            {"messages": [{"role": "user", "content": turn.message}]},
            config={"configurable": {"thread_id": turn.thread_id}},
            stream_mode=["messages", "updates"],
            version="v2",
        ):
            if chunk["type"] == "messages":
                token, metadata = chunk["data"]
                if (
                    isinstance(token, AIMessageChunk)
                    and metadata.get("langgraph_node") == MODEL_NODE
                    and token.text
                ):
                    for part in open_or_continue_text(thinking.feed(token.text)):
                        yield part
                continue

            for node, update in (chunk["data"] or {}).items():
                for message in cast(dict[str, Any], update or {}).get("messages", []):
                    if node == MODEL_NODE and isinstance(message, AIMessage):
                        for part in open_or_continue_text(thinking.flush()):
                            yield part
                        thinking = ThinkingFilter()
                        if text_id is not None:
                            yield TextEndPart(id=text_id)
                            text_id = None
                        if message.usage_metadata:
                            input_tokens += message.usage_metadata["input_tokens"]
                            output_tokens += message.usage_metadata["output_tokens"]
                        for call in message.tool_calls:
                            if call["name"] in _KNOWN_TOOLS:
                                yield ToolStatusPart(
                                    data=ToolStatus(
                                        tool=cast(ToolName, call["name"]), state="running"
                                    )
                                )
                    elif node == TOOLS_NODE and isinstance(message, ToolMessage):
                        if message.name in _KNOWN_TOOLS:
                            yield ToolStatusPart(
                                data=ToolStatus(tool=cast(ToolName, message.name), state="done")
                            )
                        if message.name == SEARCH_TOOL_NAME and message.artifact:
                            for hit in cast(list[RetrievedArticle], message.artifact):
                                best = cited.get(hit.article_no)
                                if best is None or hit.score > best.score:
                                    cited[hit.article_no] = hit

        for part in open_or_continue_text(thinking.flush()):
            yield part
        if text_id is not None:
            yield TextEndPart(id=text_id)
        # Cite only retrieved articles the answer actually names, so chips match the text.
        named = _cited_article_numbers("".join(answer))
        cited = {no: a for no, a in cited.items() if no in named}
        if cited:
            ranked = sorted(cited.values(), key=lambda a: (-a.score, a.article_no))
            yield CitationsPart(
                data=Citations(
                    citations=[
                        Citation(article_no=a.article_no, excerpt=_excerpt(a.text_ar))
                        for a in ranked
                    ]
                )
            )
        # remaining_questions is filled in by the usage guard (#6); 0 until then.
        yield UsagePart(
            data=Usage(
                input_tokens=input_tokens, output_tokens=output_tokens, remaining_questions=0
            )
        )
