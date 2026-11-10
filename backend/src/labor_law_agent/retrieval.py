"""LawRetriever port and an in-memory adapter for tests.

The Pinecone adapter (langchain-pinecone, classic serverless index) lands with ingest.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel

from labor_law_agent.ingest.parser import Article


class RetrievedArticle(BaseModel):
    article_no: int
    chapter: str | None
    text_ar: str
    score: float


class LawRetriever(Protocol):
    def search(self, query: str, k: int = 4) -> list[RetrievedArticle]: ...


_TOKEN = re.compile(r"\w+")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text)}


class InMemoryLawRetriever:
    """Token-overlap ranking; deterministic, for tests only."""

    def __init__(self, articles: Iterable[Article]) -> None:
        self._articles = list(articles)

    def search(self, query: str, k: int = 4) -> list[RetrievedArticle]:
        q = _tokens(query)
        scored = [
            (len(q & _tokens(a.text_ar)) / (len(q) or 1), a) for a in self._articles
        ]
        scored = [s for s in scored if s[0] > 0]
        scored.sort(key=lambda s: (-s[0], s[1].article_no))
        return [
            RetrievedArticle(
                article_no=a.article_no, chapter=a.chapter, text_ar=a.text_ar, score=score
            )
            for score, a in scored[:k]
        ]
