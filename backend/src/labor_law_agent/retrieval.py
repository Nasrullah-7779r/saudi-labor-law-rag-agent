"""LawRetriever port.

Adapters: ``PineconeLawRetriever`` (production) and an in-memory fake in tests/fakes.py.
"""

from __future__ import annotations

from typing import Protocol

from langchain_core.documents import Document
from pydantic import BaseModel


class RetrievedArticle(BaseModel):
    article_no: int
    chapter: str | None
    text_ar: str
    score: float


class LawRetriever(Protocol):
    def search(self, query: str, k: int = 4) -> list[RetrievedArticle]: ...


class ScoredVectorStore(Protocol):
    """The slice of ``langchain_pinecone.PineconeVectorStore`` the adapter uses (scores are
    higher-is-better for the index's cosine metric)."""

    def similarity_search_with_score(
        self, query: str, k: int = 4
    ) -> list[tuple[Document, float]]: ...


class PineconeLawRetriever:
    """Production adapter over a langchain-pinecone ``PineconeVectorStore``.

    The index holds one vector per article chunk (see ``ingest.chunks``); several chunks of the
    same article can match, so hits are collapsed to one per article, keeping the best score.
    ``similarity_search_with_score(query, k)`` returns ``(Document, score)`` with the chunk text
    in ``page_content`` and the rest of the vector metadata in ``Document.metadata``
    (langchain-pinecone 0.2.x, default ``text_key="text"``).
    """

    def __init__(self, vector_store: ScoredVectorStore, overfetch: int = 3) -> None:
        self._store = vector_store  # langchain_pinecone.PineconeVectorStore
        self._overfetch = overfetch

    def search(self, query: str, k: int = 4) -> list[RetrievedArticle]:
        if k <= 0 or not query.strip():
            return []
        hits = self._store.similarity_search_with_score(query, k=k * self._overfetch)
        best: dict[int, RetrievedArticle] = {}
        for doc, score in hits:
            if "article_no" not in doc.metadata:  # not an ingested article chunk
                continue
            article_no = int(doc.metadata["article_no"])
            if article_no in best and best[article_no].score >= score:
                continue
            best[article_no] = RetrievedArticle(
                article_no=article_no,
                chapter=doc.metadata.get("chapter"),
                text_ar=doc.page_content,
                score=float(score),
            )
        return sorted(best.values(), key=lambda a: -a.score)[:k]
