from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from labor_law_agent.ingest.chunks import ArticleChunk
from labor_law_agent.ingest.job import (
    LAST_ARTICLE_NO,
    PENALTIES_PART_EXCLUDED,
    IngestAbortedError,
    run_ingest,
)
from labor_law_agent.ingest.parser import ArticleParseError

REAL_EXCERPT = (Path(__file__).parent / "fixtures" / "boe_real_excerpt.html").read_text(
    encoding="utf-8"
)
KW = {"source_url": "https://laws.boe.gov.sa/", "version": date(2025, 2, 19)}


class RecordingEmbedder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.texts = list(texts)
        return [[float(i)] for i in range(len(texts))]


class RecordingIndex:
    def __init__(self, stale: list[str] | None = None) -> None:
        self.events: list[str] = []
        self.chunks: list[ArticleChunk] = []
        self.vectors: list[list[float]] = []
        self.keep_ids: set[str] = set()
        self._stale = stale or []

    def upsert_chunks(self, chunks: Sequence[ArticleChunk], vectors: Sequence[list[float]]) -> None:
        self.events.append("upsert")
        self.chunks = list(chunks)
        self.vectors = list(vectors)

    def delete_stale(self, keep_ids: set[str]) -> list[str]:
        self.events.append("delete_stale")
        self.keep_ids = keep_ids
        return self._stale


def test_run_ingest_on_real_excerpt() -> None:
    embedder, index = RecordingEmbedder(), RecordingIndex(stale=["art-099-00"])
    summary = run_ingest(REAL_EXCERPT, embedder=embedder, index=index, last_article_no=3, **KW)

    assert summary.articles == 3
    assert summary.chunks == len(index.chunks) >= 3
    assert summary.deleted_stale == ["art-099-00"]
    assert embedder.texts == [c.text_ar for c in index.chunks]
    assert [c.article_no for c in index.chunks] == sorted(c.article_no for c in index.chunks)
    assert len(index.vectors) == len(index.chunks)
    assert index.events == ["upsert", "delete_stale"]
    assert index.keep_ids == {c.id for c in index.chunks}
    assert "art-001-00" in index.keep_ids


def test_penalties_part_excluded_constant() -> None:
    assert PENALTIES_PART_EXCLUDED == frozenset(range(229, 243))


def test_default_excludes_penalties_part() -> None:
    nums = [*range(1, 4), *range(229, 243)]
    html = "<html><body>" + "".join(f"<h3>المادة {n}</h3><p>نص {n}.</p>" for n in nums)
    index = RecordingIndex()
    summary = run_ingest(html, embedder=RecordingEmbedder(), index=index, last_article_no=3, **KW)
    assert summary.articles == 3
    assert {c.article_no for c in index.chunks} == {1, 2, 3}


def test_excluded_can_be_overridden() -> None:
    html = "<html><body>" + "".join(f"<h3>المادة {n}</h3><p>نص {n}.</p>" for n in (1, 2, 3))
    index = RecordingIndex()
    summary = run_ingest(
        html,
        embedder=RecordingEmbedder(),
        index=index,
        excluded=frozenset({3}),
        last_article_no=2,
        **KW,
    )
    assert summary.articles == 2
    assert {c.article_no for c in index.chunks} == {1, 2}


def test_parse_error_propagates_and_nothing_is_written() -> None:
    html = "<html><body><h3>المادة 1</h3><p>نص.</p><h3>المادة 3</h3><p>نص.</p>"
    embedder, index = RecordingEmbedder(), RecordingIndex()
    with pytest.raises(ArticleParseError, match="missing"):
        run_ingest(html, embedder=embedder, index=index, last_article_no=3, **KW)
    assert index.events == []
    assert embedder.texts == []


def test_last_article_no_default_is_245() -> None:
    assert LAST_ARTICLE_NO == 245


def test_truncated_page_aborts_before_embedding_or_upserting() -> None:
    html = "<html><body>" + "".join(f"<h3>المادة {n}</h3><p>نص {n}.</p>" for n in (1, 2, 3))
    embedder, index = RecordingEmbedder(), RecordingIndex()
    with pytest.raises(IngestAbortedError, match="last article is 3, expected 245"):
        run_ingest(html, embedder=embedder, index=index, **KW)  # default last_article_no=245
    assert embedder.texts == []
    assert index.events == []


def test_summary_lists_sorted_excluded_article_nos() -> None:
    html = "<html><body>" + "".join(f"<h3>المادة {n}</h3><p>نص {n}.</p>" for n in (1, 2, 3))
    summary = run_ingest(
        html,
        embedder=RecordingEmbedder(),
        index=RecordingIndex(),
        excluded=frozenset({9, 7}),
        last_article_no=3,
        **KW,
    )
    assert summary.excluded_article_nos == [7, 9]


def test_summary_excluded_defaults_to_penalties_part() -> None:
    html = "<html><body>" + "".join(f"<h3>المادة {n}</h3><p>نص {n}.</p>" for n in (1, 2, 3))
    summary = run_ingest(
        html, embedder=RecordingEmbedder(), index=RecordingIndex(), last_article_no=3, **KW
    )
    assert summary.excluded_article_nos == sorted(PENALTIES_PART_EXCLUDED)
