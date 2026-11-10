from datetime import date
from pathlib import Path

from fakes import InMemoryLawRetriever

from labor_law_agent.ingest.parser import parse_articles

FIXTURE = (Path(__file__).parent / "fixtures" / "boe_sample.html").read_text(encoding="utf-8")
KW = {"source_url": "https://laws.boe.gov.sa/", "version": date(2025, 2, 19)}


def test_in_memory_retriever_ranks_matching_article_first() -> None:
    retriever = InMemoryLawRetriever(parse_articles(FIXTURE, **KW))
    hits = retriever.search("الأجر الشهري", k=2)
    assert hits[0].article_no == 4


def _page(*body: str) -> str:
    return "<html><body>" + "".join(body) + "</body></html>"


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
