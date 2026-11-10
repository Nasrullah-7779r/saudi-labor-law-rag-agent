from datetime import date
from pathlib import Path

import pytest

from labor_law_agent.ingest.parser import (
    ArticleParseError,
    parse_articles,
    to_western_digits,
)
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


def _page(*body: str) -> str:
    return "<html><body>" + "".join(body) + "</body></html>"


def test_to_western_digits_converts_arabic_indic_and_persian() -> None:
    assert to_western_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789"
    assert to_western_digits("۰۱۲۳۴۵۶۷۸۹") == "0123456789"
    assert to_western_digits("المادة ١٢ abc 3") == "المادة 12 abc 3"


def test_accepts_western_and_persian_digit_headings() -> None:
    html = _page(
        "<h3>المادة 1</h3><p>نص أول.</p>",
        "<h3>المادة ۲</h3><p>نص ثان.</p>",
        "<h3>المادة ٣</h3><p>نص ثالث.</p>",
    )
    assert [a.article_no for a in parse_articles(html, **KW)] == [1, 2, 3]


def test_multi_digit_article_numbers() -> None:
    body = [f"<h3>المادة {to_arabic(n)}</h3><p>نص {n}.</p>" for n in range(1, 13)]
    assert [a.article_no for a in parse_articles(_page(*body), **KW)] == list(range(1, 13))


def to_arabic(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def test_source_url_and_version_carried_onto_every_record() -> None:
    articles = parse_articles(FIXTURE, **KW)
    assert len(articles) == 4
    assert {a.source_url for a in articles} == {KW["source_url"]}
    assert {a.version for a in articles} == {KW["version"]}


def test_article_text_and_chapter_assignment() -> None:
    articles = parse_articles(FIXTURE, **KW)
    assert articles[0].text_ar == "يسمى هذا النظام نظام العمل."
    assert articles[0].chapter == "الفصل الأول: التعريفات"
    assert articles[2].chapter == "الفصل الأول: التعريفات"
    assert articles[3].text_ar == "يستحق العامل الأجر الشهري في موعده."


def test_fails_when_no_articles() -> None:
    with pytest.raises(ArticleParseError, match="no articles"):
        parse_articles(_page("<p>بموجب مرسوم ملكي</p>"), **KW)


def test_fails_when_article_has_empty_text() -> None:
    html = _page(
        "<h3>المادة ١</h3><p>نص.</p>",
        "<h3>المادة ٢</h3>",
        "<h3>المادة ٣</h3><p>نص.</p>",
    )
    with pytest.raises(ArticleParseError, match=r"empty text: \[2\]"):
        parse_articles(html, **KW)


def test_article_with_only_amendment_note_is_empty() -> None:
    html = _page("<h3>المادة ١</h3><p>عدلت هذه المادة بموجب مرسوم.</p>")
    with pytest.raises(ArticleParseError, match="empty text"):
        parse_articles(html, **KW)


def test_numbering_must_start_at_one() -> None:
    html = _page("<h3>المادة ٢</h3><p>نص.</p>")
    with pytest.raises(ArticleParseError, match=r"missing.*\[1\]"):
        parse_articles(html, **KW)


def test_gap_error_names_missing_numbers() -> None:
    with pytest.raises(ArticleParseError, match=r"missing article numbers: \[3\]"):
        parse_articles(FIXTURE.replace("المادة ٣", "المادة ٥"), **KW)


def test_duplicate_error_names_duplicate_numbers() -> None:
    with pytest.raises(ArticleParseError, match=r"duplicate article numbers: \[2\]"):
        parse_articles(FIXTURE.replace("المادة ٣", "المادة ٢"), **KW)


def test_preamble_before_first_article_is_excluded() -> None:
    html = _page(
        "<p>ديباجة المرسوم</p>",
        "<h3>المادة ١</h3><p>نص.</p>",
    )
    (art,) = parse_articles(html, **KW)
    assert art.text_ar == "نص."
    assert art.chapter is None


@pytest.mark.parametrize("amend", ["عدلت", "أضيفت", "ألغيت", "عُدلت"])
def test_amendment_paragraph_prefixes_excluded(amend: str) -> None:
    html = _page("<h3>المادة ١</h3><p>نص.</p>", f"<p>{amend} بموجب مرسوم</p>")
    (art,) = parse_articles(html, **KW)
    assert art.text_ar == "نص."


def test_in_memory_retriever_no_match_returns_empty() -> None:
    retriever = InMemoryLawRetriever(parse_articles(FIXTURE, **KW))
    assert retriever.search("zzzz غيرموجود") == []
    assert retriever.search("") == []


def test_in_memory_retriever_k_limits_results() -> None:
    html = _page(*[f"<h3>المادة {n}</h3><p>العامل والأجر {n}.</p>" for n in (1, 2, 3)])
    retriever = InMemoryLawRetriever(parse_articles(html, **KW))
    assert len(retriever.search("العامل", k=2)) == 2
    assert len(retriever.search("العامل", k=1)) == 1
    assert len(retriever.search("العامل", k=10)) == 3
    assert retriever.search("العامل", k=0) == []
    assert retriever.search("العامل", k=2)[0].article_no == 1  # ties broken by article_no
