"""Black-box tests of the HTTP API: status, headers and parsed SSE events only."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fakes import FailingChatResponder
from fastapi.testclient import TestClient

from labor_law_agent.api import create_app
from labor_law_agent.chat import ChatResponder, StubChatResponder


def _client(responder: ChatResponder) -> TestClient:
    return TestClient(create_app(responder))


def _events(body: str) -> list[dict[str, Any] | str]:
    """Parse an SSE body into JSON events; the terminal marker stays the string '[DONE]'."""
    assert body.endswith("\n\n")
    out: list[dict[str, Any] | str] = []
    for frame in body.split("\n\n")[:-1]:
        assert frame.startswith("data: ")
        payload = frame[len("data: ") :]
        out.append(payload if payload == "[DONE]" else json.loads(payload))
    return out


def _types(events: list[dict[str, Any] | str]) -> list[str]:
    return [e if isinstance(e, str) else e["type"] for e in events]


def _of_type(events: list[dict[str, Any] | str], type_: str) -> list[dict[str, Any]]:
    return [e for e in events if isinstance(e, dict) and e["type"] == type_]


@pytest.fixture
def client() -> TestClient:
    return _client(StubChatResponder(delay_seconds=0))


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_response_headers(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "hello", "thread_id": "t-1"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"


def test_chat_echoes_given_thread_id(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "hello", "thread_id": "t-1"})
    assert response.headers["x-thread-id"] == "t-1"


def test_chat_generates_thread_id_when_omitted(client: TestClient) -> None:
    first = client.post("/chat", json={"message": "hello"})
    second = client.post("/chat", json={"message": "hello"})
    assert first.headers["x-thread-id"]
    assert first.headers["x-thread-id"] != second.headers["x-thread-id"]


def test_chat_stream_framing(client: TestClient) -> None:
    events = _events(client.post("/chat", json={"message": "hello"}).text)
    types = _types(events)
    assert types[0] == "start"
    assert types[-2:] == ["finish", "[DONE]"]
    assert _of_type(events, "start")[0]["messageId"]


def test_chat_text_parts_share_id_and_deltas_form_text(client: TestClient) -> None:
    events = _events(client.post("/chat", json={"message": "hello"}).text)
    types = _types(events)
    starts = _of_type(events, "text-start")
    deltas = _of_type(events, "text-delta")
    ends = _of_type(events, "text-end")
    assert len(starts) == 1
    assert len(ends) == 1
    assert len(deltas) >= 1
    assert types.index("text-start") < types.index("text-delta")
    assert types.index("text-end") > len(types) - 1 - types[::-1].index("text-delta")
    text_id = starts[0]["id"]
    assert {d["id"] for d in deltas} == {text_id}
    assert ends[0]["id"] == text_id
    assert "".join(d["delta"] for d in deltas).strip()


def test_chat_emits_tool_status(client: TestClient) -> None:
    events = _events(client.post("/chat", json={"message": "hello"}).text)
    statuses = _of_type(events, "data-tool-status")
    assert statuses
    for status in statuses:
        assert status["data"]["tool"] in {"search_labor_law", "calc_end_of_service"}
        assert status["data"]["state"] in {"running", "done"}


def test_chat_emits_citations(client: TestClient) -> None:
    events = _events(client.post("/chat", json={"message": "hello"}).text)
    citations = _of_type(events, "data-citations")
    assert len(citations) == 1
    items = citations[0]["data"]["citations"]
    assert items
    for item in items:
        assert isinstance(item["article_no"], int)
        assert isinstance(item["excerpt"], str)


def test_chat_emits_usage(client: TestClient) -> None:
    events = _events(client.post("/chat", json={"message": "hello"}).text)
    usage = _of_type(events, "data-usage")
    assert len(usage) == 1
    data = usage[0]["data"]
    assert set(data) == {"input_tokens", "output_tokens", "remaining_questions"}
    assert all(isinstance(v, int) for v in data.values())


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "x" * 2001},
        {},
        {"thread_id": "t-1"},
        {"message": "hello", "thread_id": "t" * 129},
        {"message": "hello", "thread_id": ""},
    ],
    ids=["empty", "too-long", "missing", "missing-with-thread", "thread-too-long", "thread-empty"],
)
def test_chat_rejects_invalid_request(client: TestClient, body: dict[str, Any]) -> None:
    response = client.post("/chat", json=body)
    assert response.status_code == 422
    assert not response.headers["content-type"].startswith("text/event-stream")
    assert "[DONE]" not in response.text


def test_chat_accepts_boundary_lengths(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "x" * 2000, "thread_id": "t" * 128})
    assert response.status_code == 200


def test_chat_midstream_failure_reports_error_in_band() -> None:
    response = _client(FailingChatResponder()).post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    events = _events(response.text)
    errors = _of_type(events, "error")
    assert len(errors) == 1
    assert errors[0]["errorText"]
    assert "boom" not in response.text
    assert _types(events)[0] == "start"
    assert _types(events)[-3:] == ["error", "finish", "[DONE]"]
