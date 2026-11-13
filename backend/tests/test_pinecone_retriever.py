"""PineconeLawRetriever adapter, driven through a fake vector store."""

from __future__ import annotations

from langchain_core.documents import Document

from labor_law_agent.retrieval import PineconeLawRetriever


class FakeVectorStore:
    """Exposes the one langchain-pinecone method the adapter uses."""

    def __init__(self, hits: list[tuple[Document, float]]) -> None:
        self._hits = hits
        self.calls: list[tuple[str, int]] = []

    def similarity_search_with_score(self, query: str, k: int = 4) -> list[tuple[Document, float]]:
        self.calls.append((query, k))
        return self._hits[:k]


def _doc(article_no: int, text: str = "نص", chapter: str | None = "الباب") -> Document:
    metadata: dict[str, object] = {"article_no": article_no}
    if chapter is not None:
        metadata["chapter"] = chapter
    return Document(page_content=text, metadata=metadata)


def test_maps_document_to_retrieved_article() -> None:
    store = FakeVectorStore([(_doc(4, "يستحق العامل الأجر", "الباب الثاني"), 0.8)])
    [hit] = PineconeLawRetriever(store).search("الأجر")
    assert (hit.article_no, hit.chapter, hit.text_ar, hit.score) == (
        4,
        "الباب الثاني",
        "يستحق العامل الأجر",
        0.8,
    )


def test_chapter_is_optional() -> None:
    store = FakeVectorStore([(_doc(4, chapter=None), 0.8)])
    assert PineconeLawRetriever(store).search("q")[0].chapter is None


def test_dedupes_chunks_of_same_article_keeping_best_score() -> None:
    store = FakeVectorStore(
        [(_doc(4, "low"), 0.3), (_doc(4, "best"), 0.9), (_doc(4, "mid"), 0.5), (_doc(7), 0.6)]
    )
    hits = PineconeLawRetriever(store).search("q", k=4)
    assert [h.article_no for h in hits] == [4, 7]
    assert hits[0].score == 0.9
    assert hits[0].text_ar == "best"


def test_results_sorted_by_score_descending() -> None:
    store = FakeVectorStore([(_doc(1), 0.2), (_doc(2), 0.9), (_doc(3), 0.5)])
    hits = PineconeLawRetriever(store).search("q", k=3)
    assert [h.article_no for h in hits] == [2, 3, 1]


def test_k_limits_results() -> None:
    store = FakeVectorStore([(_doc(n), 1.0 - n / 10) for n in range(1, 6)])
    hits = PineconeLawRetriever(store).search("q", k=2)
    assert [h.article_no for h in hits] == [1, 2]


def test_overfetches_so_dedupe_can_still_fill_k() -> None:
    store = FakeVectorStore([(_doc(1), 0.9), (_doc(1), 0.8), (_doc(1), 0.7), (_doc(2), 0.6)])
    hits = PineconeLawRetriever(store).search("q", k=2)
    assert [h.article_no for h in hits] == [1, 2]


def test_non_positive_k_returns_empty_without_calling_store() -> None:
    store = FakeVectorStore([(_doc(1), 0.9)])
    retriever = PineconeLawRetriever(store)
    assert retriever.search("q", k=0) == []
    assert retriever.search("q", k=-1) == []
    assert store.calls == []


def test_blank_query_returns_empty_without_calling_store() -> None:
    store = FakeVectorStore([(_doc(1), 0.9)])
    retriever = PineconeLawRetriever(store)
    assert retriever.search("") == []
    assert retriever.search("   \n") == []
    assert store.calls == []


def test_no_hits_returns_empty() -> None:
    assert PineconeLawRetriever(FakeVectorStore([])).search("q") == []


def test_hit_without_article_no_metadata_is_skipped() -> None:
    untagged = Document(page_content="غير مفهرس", metadata={"chapter": "الباب"})
    store = FakeVectorStore([(untagged, 0.99), (_doc(4), 0.5)])
    hits = PineconeLawRetriever(store).search("q", k=2)
    assert [h.article_no for h in hits] == [4]
