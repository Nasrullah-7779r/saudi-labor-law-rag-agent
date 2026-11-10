"""LawRetriever port.

Adapters: Pinecone (production, added with ingest) and an in-memory fake in tests/fakes.py.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class RetrievedArticle(BaseModel):
    article_no: int
    chapter: str | None
    text_ar: str
    score: float


class LawRetriever(Protocol):
    def search(self, query: str, k: int = 4) -> list[RetrievedArticle]: ...
