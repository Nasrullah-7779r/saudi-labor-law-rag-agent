"""Article parser: raw BOE Arabic HTML -> list[Article]. Pure, no I/O.

Assumptions about the page (re-check against a saved real BOE page):
- each article starts at a heading whose text is ``المادة <number>``, where the number is
  an ordinal in words (``المادة الرابعة والثمانون``, as on the BOE site) or digits
  (Arabic-Indic, Persian or Western); colons and Latin words (the site's "Article Changes" label) around
  the heading are ignored; text up to the next heading belongs to that article;
- part headings start with ``الباب`` and chapter headings with ``الفصل``; a new part
  resets the current chapter;
- amending-decree notes are lines starting with ``عدلت``/``عُدلت``/``أضيفت``/``ألغيت`` or
  blocks carrying the ``amendment`` CSS class, and are dropped;
- on the real BOE page an article's current text sits in ``div.HTMLContainer`` (often inside a
  ``<p>`` that itself wraps further ``<p>``s), and earlier versions sit in a hidden
  ``.popup-list`` next to it; the popup and ``.article_btns`` are dropped, and only the
  outermost content block is read so nested ``<p>``s are not read twice;
- anything before the first article (the issuing decree preamble) is dropped.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from bs4 import BeautifulSoup
from pydantic import BaseModel

from labor_law_agent.ingest.ordinals import arabic_ordinal_to_int

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARTICLE_RE = re.compile(r"^المادة\s+(.+)$")
_DIGITS_RE = re.compile(r"^[0-9٠-٩۰-۹]+$")
_HEADING_NOISE_RE = re.compile(r"[A-Za-z]+|[:：]")  # "Article Changes" label, colons
_PART_RE = re.compile(r"^\s*الباب\b")
_CHAPTER_RE = re.compile(r"^\s*الفصل\b")
_DROPPED_SELECTOR = ".amendment, .popup-list, .article_btns"
_CONTENT_SELECTOR = "h1, h2, h3, h4, p, li, div.HTMLContainer"
_AMEND_RE = re.compile(r"^\s*(عدلت|عُدلت|عُدِّلت|أضيفت|ألغيت)")


class ArticleParseError(ValueError):
    pass


class Article(BaseModel):
    article_no: int
    part: str | None
    chapter: str | None
    text_ar: str
    source_url: str
    version: date


def to_western_digits(text: str) -> str:
    return text.translate(_DIGITS)


def article_number_from_heading(text: str) -> int | None:
    """Article number if ``text`` is a whole article heading, else None."""
    cleaned = " ".join(_HEADING_NOISE_RE.sub(" ", text).split())
    m = _ARTICLE_RE.match(cleaned)
    if not m:
        return None
    number = m.group(1)
    if _DIGITS_RE.match(number):
        return int(to_western_digits(number))
    return arabic_ordinal_to_int(number)


def parse_articles(
    html: str,
    *,
    source_url: str,
    version: date,
    excluded: frozenset[int] = frozenset(),
) -> list[Article]:
    """Parse the page; articles numbered in ``excluded`` (and any unheaded text after them)
    are dropped and not expected by the continuity check."""
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select(_DROPPED_SELECTOR):
        node.decompose()

    articles: list[Article] = []
    part: str | None = None
    chapter: str | None = None
    current_no: int | None = None
    current_part: str | None = None
    current_chapter: str | None = None
    lines: list[str] = []

    def flush() -> None:
        if current_no is not None and current_no not in excluded:
            articles.append(
                Article(
                    article_no=current_no,
                    part=current_part,
                    chapter=current_chapter,
                    text_ar="\n".join(lines).strip(),
                    source_url=source_url,
                    version=version,
                )
            )

    for el in soup.select(_CONTENT_SELECTOR):
        if el.find_parent(["p", "li"]) or el.find_parent("div", class_="HTMLContainer"):
            continue  # already read as part of its outermost content block
        if el.name in {"h1", "h2", "h3", "h4"}:
            text = " ".join(el.get_text(" ", strip=True).split())
            if (number := article_number_from_heading(text)) is not None:
                flush()
                current_no = number
                current_part = part
                current_chapter = chapter
                lines = []
                continue
            if _PART_RE.match(text):
                part = text
                chapter = None
                continue
            if _CHAPTER_RE.match(text):
                chapter = text
                continue
        if current_no is None:
            continue
        for raw in el.get_text("\n").splitlines():
            line = " ".join(raw.split())
            if line and not _AMEND_RE.match(line):
                lines.append(line)
    flush()

    _validate(articles, excluded)
    return articles


def _validate(articles: list[Article], excluded: frozenset[int]) -> None:
    if not articles:
        raise ArticleParseError("no articles found")
    numbers = [a.article_no for a in articles]
    counts = Counter(numbers)
    seen = set(counts)
    dupes = sorted(n for n, c in counts.items() if c > 1)
    if dupes:
        raise ArticleParseError(f"duplicate article numbers: {dupes}")
    expected = set(range(1, max(numbers) + 1)) - excluded
    missing = sorted(expected - seen)
    if missing:
        raise ArticleParseError(f"missing article numbers: {missing}")
    empty = [a.article_no for a in articles if not a.text_ar]
    if empty:
        raise ArticleParseError(f"articles with empty text: {empty}")
