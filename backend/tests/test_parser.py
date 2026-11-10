from datetime import date
from pathlib import Path

import pytest

from labor_law_agent.ingest.parser import (
    ArticleParseError,
    article_number_from_heading,
    parse_articles,
    to_western_digits,
)

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


def test_article_gets_part_and_chapter() -> None:
    html = _page(
        "<h2>الباب الأول: أحكام عامة</h2>",
        "<h2>الفصل الأول: التعريفات</h2>",
        "<h3>المادة ١</h3><p>نص.</p>",
    )
    (art,) = parse_articles(html, **KW)
    assert art.part == "الباب الأول: أحكام عامة"
    assert art.chapter == "الفصل الأول: التعريفات"


def test_new_part_resets_chapter() -> None:
    html = _page(
        "<h2>الباب الأول: أحكام عامة</h2>",
        "<h2>الفصل الأول: التعريفات</h2>",
        "<h3>المادة ١</h3><p>نص.</p>",
        "<h2>الباب الثاني: عقد العمل</h2>",
        "<h3>المادة ٢</h3><p>نص.</p>",
        "<h2>الفصل الأول: إبرام العقد</h2>",
        "<h3>المادة ٣</h3><p>نص.</p>",
    )
    first, second, third = parse_articles(html, **KW)
    assert (first.part, first.chapter) == ("الباب الأول: أحكام عامة", "الفصل الأول: التعريفات")
    assert (second.part, second.chapter) == ("الباب الثاني: عقد العمل", None)
    assert (third.part, third.chapter) == ("الباب الثاني: عقد العمل", "الفصل الأول: إبرام العقد")


def test_article_before_any_heading_has_no_part_or_chapter() -> None:
    (art,) = parse_articles(_page("<h3>المادة ١</h3><p>نص.</p>"), **KW)
    assert art.part is None
    assert art.chapter is None


def test_fixture_articles_carry_part() -> None:
    articles = parse_articles(FIXTURE, **KW)
    assert {a.part for a in articles} == {"الباب الأول: أحكام عامة"}



@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("المادة الأولى", 1),
        ("المادة الرابعة والثمانون", 84),
        ("المادة المائة", 100),
        ("المادة الأولى بعد المائة", 101),
        ("المادة الثالثة والتسعون بعد المائة", 193),
        ("المادة المئتان", 200),
        ("المادة الأولى بعد المائتين", 201),
        ("المادة الخامسة والأربعون بعد المائتين", 245),
        ("المادة 7", 7),
        ("المادة ١٢", 12),
        ("المادة ۱۵", 15),
        (": Article Changesالمادة الثالثة عشرة", 13),
        (":المادة الثالثة:", 3),
        ("Article Changes المادة ٤ :", 4),
        ("  المادة   الأولى  ", 1),
    ],
)
def test_article_number_from_heading(heading: str, expected: int) -> None:
    assert article_number_from_heading(heading) == expected


@pytest.mark.parametrize(
    "text",
    [
        "المادة الخامسة من هذا النظام تسري على العمال.",
        "تطبق المادة الخامسة على العامل.",
        "المادة",
        "الفصل الأول",
        "",
    ],
)
def test_article_number_from_heading_rejects_body_text(text: str) -> None:
    assert article_number_from_heading(text) is None


def test_parse_articles_with_word_headings_and_ordinal_reference() -> None:
    reference = "المادة الخامسة من هذا النظام تسري على جميع العمال."
    html = _page(
        "<h3>المادة الأولى</h3><p>نص أول.</p>",
        "<h3>المادة الثانية</h3><p>نص ثان.</p>",
        f"<p>: Article Changes</p><h3>: Article Changesالمادة الثالثة</h3><p>{reference}</p>",
        "<h3>المادة الرابعة</h3><p>نص رابع.</p>",
        "<h3>المادة الخامسة</h3><p>نص خامس.</p>",
        "<h3>المادة السادسة</h3><p>نص سادس.</p>",
        "<h3>المادة السابعة</h3><p>نص سابع.</p>",
        "<h3>المادة الثامنة</h3><p>نص ثامن.</p>",
        "<h3>المادة التاسعة</h3><p>نص تاسع.</p>",
        "<h3>المادة العاشرة</h3><p>نص عاشر.</p>",
        "<h3>المادة الحادية عشرة</h3><p>نص.</p>",
        "<h3>المادة الثانية عشرة</h3><p>نص.</p>",
    )
    articles = parse_articles(html, **KW)
    assert [a.article_no for a in articles] == list(range(1, 13))
    assert articles[2].text_ar == reference
