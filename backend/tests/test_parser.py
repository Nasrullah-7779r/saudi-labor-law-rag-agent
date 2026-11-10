from datetime import date
from pathlib import Path

import pytest

from labor_law_agent.ingest.parser import ArticleParseError, parse_articles
from labor_law_agent.retrieval import InMemoryLawRetriever

FIXTURE = (Path(__file__).parent / "fixtures" / "boe_sample.html").read_text(encoding="utf-8")
KW = {"source_url": "https://laws.boe.gov.sa/", "version": date(2025, 2, 19)}


def test_parses_articles_with_continuous_numbers() -> None:
    articles = parse_articles(FIXTURE, **KW)
    assert [a.article_no for a in articles] == [1, 2, 3, 4]


def test_converts_arabic_indic_digits_and_tracks_chapter() -> None:
    art = parse_articles(FIXTURE, **KW)[3]
    assert art.article_no == 4
    assert art.chapter == "الفصل الثاني: الأجور"


def test_excludes_preamble_and_amendment_notes() -> None:
    text = "\n".join(a.text_ar for a in parse_articles(FIXTURE, **KW))
    assert "مرسوم ملكي" not in text
    assert "عدلت هذه المادة" not in text
    assert "ملاحظة تعديل" not in text


@pytest.mark.parametrize(
    ("old", "new", "msg"),
    [("المادة ٣", "المادة ٥", "missing"), ("المادة ٣", "المادة ٢", "duplicate")],
)
def test_fails_on_gap_or_duplicate(old: str, new: str, msg: str) -> None:
    with pytest.raises(ArticleParseError, match=msg):
        parse_articles(FIXTURE.replace(old, new), **KW)


def test_in_memory_retriever_ranks_matching_article_first() -> None:
    retriever = InMemoryLawRetriever(parse_articles(FIXTURE, **KW))
    hits = retriever.search("الأجر الشهري", k=2)
    assert hits[0].article_no == 4
