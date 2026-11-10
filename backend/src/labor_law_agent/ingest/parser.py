"""Article parser: raw BOE Arabic HTML -> list[Article]. Pure, no I/O.

Assumptions about the page (re-check against a saved real BOE page):
- each article starts at a heading whose text is ``المادة <number>`` (Arabic-Indic or
  Western digits); text up to the next heading belongs to that article;
- chapter/part headings start with ``الفصل`` or ``الباب``;
- amending-decree notes are paragraphs starting with ``عدلت``/``عُدلت``/``أضيفت`` or
  carrying the ``amendment`` CSS class, and are dropped;
- anything before the first article (the issuing decree preamble) is dropped.
"""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup
from pydantic import BaseModel

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARTICLE_RE = re.compile(r"^\s*المادة\s+([0-9٠-٩۰-۹]+)\s*[:：]?\s*$")
_CHAPTER_RE = re.compile(r"^\s*(الفصل|الباب)\b")
_AMEND_RE = re.compile(r"^\s*(عدلت|عُدلت|عُدِّلت|أضيفت|ألغيت)")


class ArticleParseError(ValueError):
    pass


class Article(BaseModel):
    article_no: int
    chapter: str | None
    text_ar: str
    source_url: str
    version: date


def to_western_digits(text: str) -> str:
    return text.translate(_DIGITS)


def parse_articles(html: str, *, source_url: str, version: date) -> list[Article]:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select(".amendment"):
        node.decompose()

    articles: list[Article] = []
    chapter: str | None = None
    current_no: int | None = None
    current_chapter: str | None = None
    lines: list[str] = []

    def flush() -> None:
        if current_no is not None:
            articles.append(
                Article(
                    article_no=current_no,
                    chapter=current_chapter,
                    text_ar="\n".join(lines).strip(),
                    source_url=source_url,
                    version=version,
                )
            )

    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if m := _ARTICLE_RE.match(text):
            flush()
            current_no = int(to_western_digits(m.group(1)))
            current_chapter = chapter
            lines = []
        elif _CHAPTER_RE.match(text):
            chapter = text
        elif current_no is not None and not _AMEND_RE.match(text):
            lines.append(text)
    flush()

    _validate(articles)
    return articles


def _validate(articles: list[Article]) -> None:
    if not articles:
        raise ArticleParseError("no articles found")
    numbers = [a.article_no for a in articles]
    seen = set(numbers)
    dupes = sorted({n for n in numbers if numbers.count(n) > 1})
    if dupes:
        raise ArticleParseError(f"duplicate article numbers: {dupes}")
    expected = set(range(1, max(numbers) + 1))
    missing = sorted(expected - seen)
    if missing:
        raise ArticleParseError(f"missing article numbers: {missing}")
    empty = [a.article_no for a in articles if not a.text_ar]
    if empty:
        raise ArticleParseError(f"articles with empty text: {empty}")
