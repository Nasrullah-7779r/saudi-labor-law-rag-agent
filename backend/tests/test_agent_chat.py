"""Black-box tests of POST /chat with the real agent graph, a scripted model and in-memory law."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fakes import InMemoryLawRetriever, ScriptedChatModel
from fastapi.testclient import TestClient
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from pydantic import Field
from test_chat_api import _events, _of_type, _types

from labor_law_agent.agent import SEARCH_TOOL_NAME, build_agent
from labor_law_agent.agent_responder import AgentChatResponder
from labor_law_agent.api import create_app
from labor_law_agent.calculator import EndOfServiceResult
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


def _chat(
    script: list[AIMessage | Exception], retriever: Any = None, *, streaming: bool = True
) -> list[Any]:
    model = ScriptedChatModel(script=script, disable_streaming=not streaming)
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
    retrieved = [h.article_no for h in InMemoryLawRetriever(ARTICLES).search("الأجر الشهري")]
    assert retrieved
    assert states == [
        {"tool": SEARCH_TOOL_NAME, "state": "running", "article_nos": None},
        {"tool": SEARCH_TOOL_NAME, "state": "done", "article_nos": retrieved},
    ]


def test_agent_text_streams_in_chunks_sharing_one_id() -> None:
    events = _chat([_tool_turn("الأجر الشهري"), _answer_turn()])
    deltas = _of_type(events, "text-delta")
    assert len(deltas) > 1
    assert _text(events) == ANSWER
    ids = {e["id"] for e in deltas}
    assert ids == {_of_type(events, "text-start")[0]["id"], _of_type(events, "text-end")[0]["id"]}
    assert len(ids) == 1


def test_agent_non_streaming_model_text_is_emitted_once() -> None:
    # Models LangChain runs without streaming (MiniMax on Bedrock Converse) make LangGraph's
    # messages stream yield one whole AIMessage rather than AIMessageChunk deltas.
    events = _chat([_tool_turn("الأجر الشهري"), _answer_turn()], streaming=False)
    deltas = _of_type(events, "text-delta")
    assert [e["delta"] for e in deltas] == [ANSWER]
    assert len(_of_type(events, "text-start")) == 1
    assert len(_of_type(events, "text-end")) == 1
    assert {e["id"] for e in deltas} == {_of_type(events, "text-start")[0]["id"]}
    assert _text(events) == ANSWER


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


class _Scored:
    """Retriever fake returning fixed hits, with a duplicate article and a score tie."""

    def search(self, query: str, k: int = 4) -> list[RetrievedArticle]:
        def hit(no: int, score: float) -> RetrievedArticle:
            return RetrievedArticle(article_no=no, chapter=None, text_ar=f"نص {no}", score=score)

        return [hit(7, 0.5), hit(4, 0.5), hit(111, 0.9), hit(7, 0.2), hit(109, 0.1)]


def test_agent_done_status_lists_unique_articles_by_score_then_article_no() -> None:
    events = _chat([_tool_turn("x"), _answer_turn("No article named.")], retriever=_Scored())
    done = [e["data"] for e in _of_type(events, "data-tool-status") if e["data"]["state"] == "done"]
    assert done == [{"tool": SEARCH_TOOL_NAME, "state": "done", "article_nos": [111, 4, 7, 109]}]


def test_agent_done_status_article_nos_null_when_search_has_no_hits() -> None:
    events = _chat([_tool_turn("zzzz غيرموجود"), _answer_turn("Nothing found.")])
    statuses = [e["data"] for e in _of_type(events, "data-tool-status")]
    assert [s["article_nos"] for s in statuses] == [None, None]


def test_agent_preamble_article_mention_is_not_cited() -> None:
    class _Pair:
        def search(self, query: str, k: int = 4) -> list[RetrievedArticle]:
            return [
                RetrievedArticle(article_no=109, chapter=None, text_ar="نص ١٠٩", score=0.9),
                RetrievedArticle(article_no=111, chapter=None, text_ar="نص ١١١", score=0.8),
            ]

    events = _chat(
        [
            _tool_turn("x", content="Let me check Article 111. "),
            _answer_turn("Leave is governed by Article 109."),
        ],
        retriever=_Pair(),
    )
    items = _of_type(events, "data-citations")[0]["data"]["citations"]
    assert [c["article_no"] for c in items] == [109]


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


def _assert_no_empty_text_parts(events: list[Any]) -> None:
    """Every text-start is followed by at least one delta before its text-end; no empty deltas."""
    open_id: str | None = None
    deltas_in_part = 0
    for e in events:
        if not isinstance(e, dict):
            continue
        if e["type"] == "text-start":
            assert open_id is None
            open_id, deltas_in_part = e["id"], 0
        elif e["type"] == "text-delta":
            assert e["id"] == open_id
            assert e["delta"] != ""
            deltas_in_part += 1
        elif e["type"] == "text-end":
            assert e["id"] == open_id
            assert deltas_in_part > 0
            open_id = None
    assert open_id is None


def test_agent_thinking_blocks_are_stripped_from_stream_and_citations_use_visible_text() -> None:
    events = _chat(
        [
            _tool_turn(
                "الأجر الشهري", content="<thinking>I should search the law first.</thinking>"
            ),
            _answer_turn(
                "<thinking>Article 7 maybe? No, Article 4.</thinking>\n" + ANSWER
            ),
        ]
    )
    assert "thinking" not in json.dumps(events)
    _assert_no_empty_text_parts(events)
    # the tool turn had only thinking: no text part for it, just the answer's one
    assert len(_of_type(events, "text-start")) == 1
    assert len(_of_type(events, "text-end")) == 1
    assert _text(events) == ANSWER
    items = _of_type(events, "data-citations")[0]["data"]["citations"]
    assert [c["article_no"] for c in items] == [4]


def test_agent_thinking_only_answer_emits_no_text_parts() -> None:
    events = _chat([_answer_turn("<thinking>nothing to say</thinking>")])
    assert "thinking" not in json.dumps(events)
    assert _of_type(events, "text-start") == []
    assert _of_type(events, "text-end") == []
    assert _of_type(events, "text-delta") == []
    assert _types(events)[-2:] == ["finish", "[DONE]"]


def test_agent_visible_text_before_tool_call_survives_thinking_strip() -> None:
    events = _chat(
        [
            _tool_turn(
                "الأجر الشهري", content="<thinking>plan</thinking>\nLet me check. "
            ),
            _answer_turn("<thinking>done</thinking>" + ANSWER),
        ]
    )
    assert "thinking" not in json.dumps(events)
    _assert_no_empty_text_parts(events)
    assert len(_of_type(events, "text-start")) == 2
    assert _text(events) == "Let me check. " + ANSWER


class _ToolResultRecordingModel(ScriptedChatModel):
    """Capture the public model input so calculator output cannot be a scripted echo."""

    received_tool_results: list[ToolMessage] = Field(default_factory=list)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        self.received_tool_results.extend(m for m in messages if isinstance(m, ToolMessage))
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


def test_agent_calculator_returns_award_breakdown_and_articles_to_model() -> None:
    model = _ToolResultRecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calc_end_of_service",
                        "args": {
                            "last_monthly_wage": "10000",
                            "start_date": "2010-01-01",
                            "end_date": "2015-01-01",
                            "reason": "resignation",
                            "calendar": "gregorian",
                        },
                        "id": "award-1",
                        "type": "tool_call",
                    }
                ],
            ),
            _answer_turn("Your award is SAR 8,333.33 (Articles 84 and 85)."),
        ]
    )
    agent = build_agent(model, InMemoryLawRetriever(ARTICLES))
    client = TestClient(create_app(AgentChatResponder(agent)))
    response = client.post(
        "/chat",
        json={
            "message": (
                "Calculate my award: last monthly wage SAR 10000, "
                "2010-01-01 to 2015-01-01, resignation, Gregorian contract."
            )
        },
    )
    assert response.status_code == 200
    events = _events(response.text)
    assert _of_type(events, "error") == []
    assert [event["data"] for event in _of_type(events, "data-tool-status")] == [
        {"tool": "calc_end_of_service", "state": "running", "article_nos": None},
        {"tool": "calc_end_of_service", "state": "done", "article_nos": None},
    ]
    assert len(model.received_tool_results) == 1
    tool_result = model.received_tool_results[0]
    assert tool_result.name == "calc_end_of_service"
    assert tool_result.status == "success"
    assert isinstance(tool_result.content, str)
    result = EndOfServiceResult.model_validate_json(tool_result.content)
    # Five years at half a month per year = 25000; Art. 85 pays one third at exactly 5y.
    assert result.amount == Decimal("8333.33")
    assert result.full_award == Decimal("25000.00")
    assert result.applied_articles == [84, 85]
    assert len(result.breakdown) == 1
    assert result.breakdown[0].years == Decimal("5.00")
    assert result.breakdown[0].months_of_wage_per_year == Decimal("0.5")
    assert result.breakdown[0].amount == Decimal("25000.00")
    assert _text(events) == "Your award is SAR 8,333.33 (Articles 84 and 85)."


def test_agent_incomplete_calculator_input_returns_validation_for_clarification() -> None:
    clarification = "What are your employment start date, end date and termination reason?"
    model = _ToolResultRecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calc_end_of_service",
                        "args": {"last_monthly_wage": "10000"},
                        "id": "incomplete-award-1",
                        "type": "tool_call",
                    }
                ],
            ),
            _answer_turn(clarification),
        ]
    )
    agent = build_agent(model, InMemoryLawRetriever(ARTICLES))
    client = TestClient(create_app(AgentChatResponder(agent)))
    response = client.post(
        "/chat", json={"message": "Calculate my end-of-service award; my wage is SAR 10000."}
    )
    assert response.status_code == 200
    events = _events(response.text)
    assert _of_type(events, "error") == []
    assert len(model.received_tool_results) == 1
    rejection = model.received_tool_results[0]
    assert rejection.name == "calc_end_of_service"
    assert rejection.status == "error"
    assert isinstance(rejection.content, str)
    for missing_input in ("start_date", "end_date", "reason"):
        assert missing_input in rejection.content
    assert _text(events) == clarification
    assert _types(events)[-2:] == ["finish", "[DONE]"]
