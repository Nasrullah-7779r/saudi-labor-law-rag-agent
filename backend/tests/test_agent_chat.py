"""Black-box tests of POST /chat with the real agent graph, a scripted model and in-memory law."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fakes import InMemoryLawRetriever, ScriptedChatModel
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from test_chat_api import _events, _of_type, _types

from labor_law_agent.agent import SEARCH_TOOL_NAME, build_agent
from labor_law_agent.agent_responder import AgentChatResponder
from labor_law_agent.api import create_app
from labor_law_agent.ingest.parser import parse_articles
from labor_law_agent.retrieval import RetrievedArticle

FIXTURE = (Path(__file__).parent / "fixtures" / "boe_sample.html").read_text(encoding="utf-8")
ARTICLES = parse_articles(
    FIXTURE, source_url="https://laws.boe.gov.sa/", version=date(2025, 2, 19)
)
ANSWER = "The employee is entitled to the monthly wage on time (Article 4)."


def _search_call(query: str, call_id: str = "call-1") -> dict[str, Any]:
    return {"name": SEARCH_TOOL_NAME, "args": {"query": query}, "id": call_id, "type": "tool_call"}


def _tool_turn(query: str, *, content: str = "", tokens: tuple[int, int] = (10, 2)) -> AIMessage:
    return AIMessage(
        content=content,
        tool_calls=[_search_call(query)],
        usage_metadata={
            "input_tokens": tokens[0],
            "output_tokens": tokens[1],
            "total_tokens": sum(tokens),
        },
    )


def _answer_turn(text: str = ANSWER, tokens: tuple[int, int] = (20, 8)) -> AIMessage:
    return AIMessage(
        content=text,
        usage_metadata={
            "input_tokens": tokens[0],
            "output_tokens": tokens[1],
            "total_tokens": sum(tokens),
        },
    )


def _chat(script: list[AIMessage | Exception], retriever: Any = None) -> list[Any]:
    model = ScriptedChatModel(script=script)
    agent = build_agent(model, retriever or InMemoryLawRetriever(ARTICLES))
    client = TestClient(create_app(AgentChatResponder(agent)))
    response = client.post("/chat", json={"message": "متى يستحق العامل الأجر؟", "thread_id": "t"})
    assert response.status_code == 200
    return _events(response.text)


def _text(events: list[Any]) -> str:
    return "".join(e["delta"] for e in _of_type(events, "text-delta"))


def test_agent_search_then_answer_full_event_order() -> None:
    events = _chat([_tool_turn("الأجر الشهري"), _answer_turn()])
    types = _types(events)
    assert types[0] == "start"
    assert types[-2:] == ["finish", "[DONE]"]
    assert [t for t in types if t != "text-delta"] == [
        "start",
        "data-tool-status",
        "data-tool-status",
        "text-start",
        "text-end",
        "data-citations",
        "data-usage",
        "finish",
        "[DONE]",
    ]
    states = [e["data"] for e in _of_type(events, "data-tool-status")]
    assert states == [
        {"tool": SEARCH_TOOL_NAME, "state": "running"},
        {"tool": SEARCH_TOOL_NAME, "state": "done"},
    ]


def test_agent_text_streams_in_chunks_sharing_one_id() -> None:
    events = _chat([_tool_turn("الأجر الشهري"), _answer_turn()])
    deltas = _of_type(events, "text-delta")
    assert len(deltas) > 1
    assert _text(events) == ANSWER
    ids = {e["id"] for e in deltas}
    assert ids == {_of_type(events, "text-start")[0]["id"], _of_type(events, "text-end")[0]["id"]}
    assert len(ids) == 1


def test_agent_citations_are_retrieved_articles_deduped() -> None:
    events = _chat([_tool_turn("الأجر الشهري"), _answer_turn()])
    citations = _of_type(events, "data-citations")
    assert len(citations) == 1
    items = citations[0]["data"]["citations"]
    assert [c["article_no"] for c in items] == [4]
    article_4 = next(a for a in ARTICLES if a.article_no == 4)
    assert items[0]["excerpt"] == article_4.text_ar


def test_agent_citations_dedupe_across_repeated_searches() -> None:
    events = _chat(
        [_tool_turn("الأجر الشهري"), _tool_turn("الأجر الشهري"), _answer_turn()],
    )
    items = _of_type(events, "data-citations")[0]["data"]["citations"]
    numbers = [c["article_no"] for c in items]
    assert numbers == sorted(set(numbers))
    assert 4 in numbers


def test_agent_citation_excerpt_is_truncated_for_long_articles() -> None:
    long_article = RetrievedArticle(article_no=7, chapter=None, text_ar="كلمة " * 200, score=1.0)

    class _Long:
        def search(self, query: str, k: int = 4) -> list[RetrievedArticle]:
            return [long_article]

    events = _chat(
        [_tool_turn("x"), _answer_turn("The rule is in Article 7.")], retriever=_Long()
    )
    excerpt = _of_type(events, "data-citations")[0]["data"]["citations"][0]["excerpt"]
    assert 0 < len(excerpt) < len(long_article.text_ar)
    assert long_article.text_ar.startswith(excerpt.rstrip("…"))


def test_agent_cites_only_retrieved_articles_the_answer_names() -> None:
    class _Two:
        def search(self, query: str, k: int = 4) -> list[RetrievedArticle]:
            return [
                RetrievedArticle(article_no=4, chapter=None, text_ar="نص الرابعة", score=0.9),
                RetrievedArticle(article_no=7, chapter=None, text_ar="نص السابعة", score=0.8),
            ]

    events = _chat(
        [_tool_turn("x"), _answer_turn("Pay is due on time (Article 4).")], retriever=_Two()
    )
    items = _of_type(events, "data-citations")[0]["data"]["citations"]
    assert [c["article_no"] for c in items] == [4]


def test_agent_no_citations_part_when_answer_names_no_retrieved_article() -> None:
    events = _chat([_tool_turn("الأجر الشهري"), _answer_turn("The law covers wages generally.")])
    assert _of_type(events, "data-citations") == []
    assert _text(events) == "The law covers wages generally."


def test_agent_arabic_indic_article_number_matches_retrieved_article() -> None:
    events = _chat([_tool_turn("الأجر الشهري"), _answer_turn("يستحق العامل الأجر (المادة ٤).")])
    items = _of_type(events, "data-citations")[0]["data"]["citations"]
    assert [c["article_no"] for c in items] == [4]


def test_agent_usage_sums_tokens_across_model_calls() -> None:
    events = _chat([_tool_turn("الأجر الشهري", tokens=(10, 2)), _answer_turn(tokens=(20, 8))])
    usage = _of_type(events, "data-usage")
    assert len(usage) == 1
    assert usage[0]["data"]["input_tokens"] == 30
    assert usage[0]["data"]["output_tokens"] == 10


def test_agent_no_matches_still_answers_without_citations() -> None:
    events = _chat([_tool_turn("zzzz غيرموجود"), _answer_turn("Nothing relevant was found.")])
    assert _of_type(events, "data-citations") == []
    assert _text(events) == "Nothing relevant was found."
    assert [e["data"]["state"] for e in _of_type(events, "data-tool-status")] == [
        "running",
        "done",
    ]


def test_agent_answer_without_tool_call_has_no_status_or_citations() -> None:
    events = _chat([_answer_turn("I only discuss labor law.")])
    types = _types(events)
    assert "data-tool-status" not in types
    assert "data-citations" not in types
    assert _text(events) == "I only discuss labor law."
    assert len(_of_type(events, "data-usage")) == 1


def test_agent_text_before_and_after_tool_call_gets_distinct_closed_ids() -> None:
    events = _chat(
        [_tool_turn("الأجر الشهري", content="Let me check. "), _answer_turn()],
    )
    starts = [e["id"] for e in _of_type(events, "text-start")]
    ends = [e["id"] for e in _of_type(events, "text-end")]
    assert len(starts) == 2
    assert len(set(starts)) == 2
    assert ends == starts
    types = _types(events)
    # the first text block is closed before the tool status goes out
    assert types.index("text-end") < types.index("data-tool-status")
    assert _text(events) == "Let me check. " + ANSWER


def test_agent_retriever_failure_is_reported_in_band_without_leaking_message() -> None:
    class _Broken:
        def search(self, query: str, k: int = 4) -> list[RetrievedArticle]:
            raise RuntimeError("pinecone key sk-secret exploded")

    events = _chat([_tool_turn("x"), _answer_turn()], retriever=_Broken())
    errors = _of_type(events, "error")
    assert len(errors) == 1
    assert "sk-secret" not in errors[0]["errorText"]
    assert "exploded" not in errors[0]["errorText"]
    assert _types(events)[-2:] == ["finish", "[DONE]"]
