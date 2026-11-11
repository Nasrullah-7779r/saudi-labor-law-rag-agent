"""Test doubles. Not shipped in the package."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterable

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
