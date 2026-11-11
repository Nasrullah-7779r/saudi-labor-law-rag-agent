"""Pinecone writer for article chunks (pinecone SDK 7.x, pinned <8 for langchain-pinecone).

API per https://github.com/pinecone-io/pinecone-python-client/blob/v7.3.0/README.md:
``Index.upsert(vectors=[(id, values, metadata)])``, ``Index.list(prefix=...)`` yields ID pages
(serverless only), ``Index.delete(ids=...)``. Metadata values may not be null, so ``None``
fields are omitted.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from labor_law_agent.ingest.chunks import CHUNK_ID_PREFIX, ArticleChunk

_UPSERT_BATCH = 100
_DELETE_BATCH = 1000  # Pinecone delete-by-ids limit per request


class ChunkIndex(Protocol):
    def upsert_chunks(self, chunks: Sequence[ArticleChunk], vectors: Sequence[list[float]]) -> None: ...
    def delete_stale(self, keep_ids: set[str]) -> list[str]: ...


class PineconeChunkIndex:
    def __init__(self, index: Any) -> None:
        self._index = index  # pinecone.Index

    def upsert_chunks(
        self, chunks: Sequence[ArticleChunk], vectors: Sequence[list[float]]
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        rows = [(c.id, v, c.vector_metadata()) for c, v in zip(chunks, vectors, strict=True)]
        for start in range(0, len(rows), _UPSERT_BATCH):
            self._index.upsert(vectors=rows[start : start + _UPSERT_BATCH])

    def delete_stale(self, keep_ids: set[str]) -> list[str]:
        """Delete article-chunk IDs left over from a previous run (e.g. an article shrank)."""
        pages: Iterable[list[str]] = self._index.list(prefix=CHUNK_ID_PREFIX)
        stale = sorted(i for page in pages for i in page if i not in keep_ids)
        for start in range(0, len(stale), _DELETE_BATCH):
            self._index.delete(ids=stale[start : start + _DELETE_BATCH])
        return stale
