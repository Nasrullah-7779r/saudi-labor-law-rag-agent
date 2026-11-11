from datetime import date

from labor_law_agent.ingest.chunks import ArticleChunk, chunk_article, chunk_id
from labor_law_agent.ingest.parser import Article


def _article(text: str, no: int = 1) -> Article:
    return Article(
        article_no=no,
        part="الباب الأول",
        chapter="الفصل الأول",
        text_ar=text,
        source_url="https://laws.boe.gov.sa/",
        version=date(2025, 2, 19),
    )


def test_short_article_is_one_chunk_with_padded_id() -> None:
    (chunk,) = chunk_article(_article("نص قصير."))
    assert chunk.id == "art-001-00"
    assert chunk.chunk_no == 0
    assert chunk.text_ar == "نص قصير."
    assert (chunk.part, chunk.chapter) == ("الباب الأول", "الفصل الأول")
    assert chunk.version == date(2025, 2, 19)


def test_chunk_id_format() -> None:
    assert chunk_id(7, 3) == "art-007-03"
    assert chunk_id(242, 12) == "art-242-12"


def test_long_multiline_article_splits_in_order_under_limit() -> None:
    lines = [f"سطر رقم {i} " + "ك" * 30 for i in range(40)]
    chunks = chunk_article(_article("\n".join(lines), no=5), max_chars=200)
    assert len(chunks) > 1
    assert all(len(c.text_ar) <= 200 for c in chunks)
    assert {c.article_no for c in chunks} == {5}
    assert [c.chunk_no for c in chunks] == list(range(len(chunks)))
    assert [c.id for c in chunks] == [f"art-005-{i:02d}" for i in range(len(chunks))]
    assert "\n".join(c.text_ar for c in chunks).split("\n") == lines


def test_ids_are_deterministic_across_calls() -> None:
    art = _article("\n".join(f"سطر {i} " + "ب" * 40 for i in range(20)))
    assert [c.id for c in chunk_article(art, max_chars=150)] == [
        c.id for c in chunk_article(art, max_chars=150)
    ]


def test_single_overlong_line_splits_on_words() -> None:
    words = [f"كلمة{i}" for i in range(100)]
    chunks = chunk_article(_article(" ".join(words)), max_chars=100)
    assert len(chunks) > 1
    assert all(len(c.text_ar) <= 100 for c in chunks)
    assert " ".join(c.text_ar for c in chunks).split(" ") == words


def test_unbroken_run_longer_than_limit_is_hard_split() -> None:
    text = "ا" * 250
    chunks = chunk_article(_article(text), max_chars=100)
    assert [len(c.text_ar) for c in chunks] == [100, 100, 50]
    assert "".join(c.text_ar for c in chunks) == text


def _meta_chunk(part: str | None, chapter: str | None) -> ArticleChunk:
    return ArticleChunk(
        id=chunk_id(5, 2),
        article_no=5,
        chunk_no=2,
        part=part,
        chapter=chapter,
        text_ar="نص",
        source_url="https://laws.boe.gov.sa/",
        version=date(2025, 2, 19),
    )


def test_vector_metadata_full() -> None:
    assert _meta_chunk("الباب", "الفصل").vector_metadata() == {
        "article_no": 5,
        "chunk_no": 2,
        "lang": "ar",
        "version": "2025-02-19",
        "source_url": "https://laws.boe.gov.sa/",
        "text": "نص",
        "chapter": "الفصل",
        "part": "الباب",
    }


def test_vector_metadata_omits_none_part_and_chapter() -> None:
    metadata = _meta_chunk(None, None).vector_metadata()
    assert "part" not in metadata
    assert "chapter" not in metadata
    assert metadata["lang"] == "ar"
    assert None not in metadata.values()
