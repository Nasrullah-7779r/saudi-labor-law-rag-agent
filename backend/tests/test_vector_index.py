from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from labor_law_agent.ingest.chunks import ArticleChunk, chunk_id
from labor_law_agent.ingest.vector_index import PineconeChunkIndex


class FakePineconeIndex:
    def __init__(self, existing_pages: list[list[str]] | None = None) -> None:
        self.upserts: list[list[tuple[str, list[float], dict[str, Any]]]] = []
        self.deletes: list[list[str]] = []
        self.list_prefixes: list[str] = []
        self._pages = existing_pages or []

    def upsert(self, vectors: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        self.upserts.append(vectors)

    def list(self, prefix: str) -> list[list[str]]:
        self.list_prefixes.append(prefix)
        return self._pages

    def delete(self, ids: list[str]) -> None:
        self.deletes.append(ids)


def _chunk(no: int, part: str | None = "الباب", chapter: str | None = "الفصل") -> ArticleChunk:
    return ArticleChunk(
        id=chunk_id(no, 0),
        article_no=no,
        chunk_no=0,
        part=part,
        chapter=chapter,
        text_ar=f"نص {no}",
        source_url="https://laws.boe.gov.sa/",
        version=date(2025, 2, 19),
    )


def test_upsert_tuple_and_metadata() -> None:
    fake = FakePineconeIndex()
    PineconeChunkIndex(fake).upsert_chunks([_chunk(1)], [[0.5, 0.25]])
    ((row,),) = fake.upserts
    assert row == (
        "art-001-00",
        [0.5, 0.25],
        {
            "article_no": 1,
            "chunk_no": 0,
            "lang": "ar",
            "version": "2025-02-19",
            "source_url": "https://laws.boe.gov.sa/",
            "text": "نص 1",
            "chapter": "الفصل",
            "part": "الباب",
        },
    )


def test_metadata_omits_none_part_and_chapter() -> None:
    fake = FakePineconeIndex()
    PineconeChunkIndex(fake).upsert_chunks([_chunk(1, part=None, chapter=None)], [[0.1]])
    metadata = fake.upserts[0][0][2]
    assert "part" not in metadata
    assert "chapter" not in metadata


def test_upserts_are_batched_by_100() -> None:
    fake = FakePineconeIndex()
    chunks = [_chunk(i) for i in range(1, 251)]
    PineconeChunkIndex(fake).upsert_chunks(chunks, [[float(i)] for i in range(250)])
    assert [len(b) for b in fake.upserts] == [100, 100, 50]
    assert [row[0] for b in fake.upserts for row in b] == [c.id for c in chunks]


def test_length_mismatch_raises_before_upsert() -> None:
    fake = FakePineconeIndex()
    with pytest.raises(ValueError, match="differ in length"):
        PineconeChunkIndex(fake).upsert_chunks([_chunk(1), _chunk(2)], [[0.1]])
    assert fake.upserts == []


def test_delete_stale_removes_only_unkept_ids_and_returns_them() -> None:
    fake = FakePineconeIndex([["art-001-00", "art-002-00"], ["art-002-01", "art-003-00"]])
    stale = PineconeChunkIndex(fake).delete_stale({"art-001-00", "art-002-00", "art-003-00"})
    assert fake.list_prefixes == ["art-"]
    assert stale == ["art-002-01"]
    assert fake.deletes == [["art-002-01"]]


def test_delete_stale_with_nothing_stale_does_not_delete() -> None:
    fake = FakePineconeIndex([["art-001-00"]])
    assert PineconeChunkIndex(fake).delete_stale({"art-001-00"}) == []
    assert fake.deletes == []
