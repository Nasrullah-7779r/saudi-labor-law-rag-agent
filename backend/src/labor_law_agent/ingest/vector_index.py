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
    """Where embedded chunks are written (Pinecone in prod, fakes in tests)."""

    def upsert_chunks(self, chunks: Sequence[ArticleChunk], vectors: Sequence[list[float]]) -> None: ...
    def delete_stale(self, keep_ids: set[str]) -> list[str]: ...


class PineconeChunkIndex:
    """Writes article chunks into a Pinecone index and cleans up leftovers."""

    def __init__(self, index: Any) -> None:
        """
        Args:
            index: A ``pinecone.Index`` client for the target index.
        """
        self._index = index  # pinecone.Index

    def upsert_chunks(
        self, chunks: Sequence[ArticleChunk], vectors: Sequence[list[float]]
    ) -> None:
        """Insert or overwrite chunks by id, 100 per request.

        Args:
            chunks: Chunks to store.
            vectors: Embedding for each chunk, in the same order.

        Raises:
            ValueError: ``chunks`` and ``vectors`` differ in length.
        """
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        rows = [(c.id, v, c.vector_metadata()) for c, v in zip(chunks, vectors, strict=True)]
        for start in range(0, len(rows), _UPSERT_BATCH):
            self._index.upsert(vectors=rows[start : start + _UPSERT_BATCH])

    def delete_stale(self, keep_ids: set[str]) -> list[str]:
        """Delete ``art-*`` ids from a previous run that this run did not write.

        Example: article 2 used to have 3 chunks and now has 2, so ``art-002-02`` goes.

        Args:
            keep_ids: Ids written by the current run.

        Returns:
            The deleted ids, sorted.
        """
        pages: Iterable[list[str]] = self._index.list(prefix=CHUNK_ID_PREFIX)
        stale = sorted(i for page in pages for i in page if i not in keep_ids)
        for start in range(0, len(stale), _DELETE_BATCH):
            self._index.delete(ids=stale[start : start + _DELETE_BATCH])
        return stale
