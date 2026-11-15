"""POST /chat conversation memory: real agent, moto DynamoDB checkpointer, scripted model."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fakes import InMemoryLawRetriever, ScriptedChatModel
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph_checkpoint_aws import DynamoDBSaver
from moto import mock_aws
from test_agent_chat import ARTICLES, _answer_turn, _text, _tool_turn
from test_chat_api import _events, _of_type, _types

from labor_law_agent import agent as agent_module
from labor_law_agent.agent import MODEL_CALLS_PER_TURN, build_agent
from labor_law_agent.agent_responder import AgentChatResponder
from labor_law_agent.api import create_app

TABLE = "checkpoints-test"
REGION = "us-east-1"
THREAD_TTL_SECONDS = 7 * 24 * 60 * 60  # ticket: threads expire after 7 days


@pytest.fixture(autouse=True)
def _aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def table() -> Iterator[Any]:
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        yield ddb.create_table(
            TableName=TABLE,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )


def _client(model: ScriptedChatModel) -> TestClient:
    saver = DynamoDBSaver(table_name=TABLE, region_name=REGION, ttl_seconds=THREAD_TTL_SECONDS)
    agent = build_agent(model, InMemoryLawRetriever(ARTICLES), saver)
    return TestClient(create_app(AgentChatResponder(agent)))


def _say(client: TestClient, message: str, thread_id: str) -> list[Any]:
    response = client.post("/chat", json={"message": message, "thread_id": thread_id})
    assert response.status_code == 200
    return _events(response.text)


def _human_texts(messages: list[BaseMessage]) -> list[str]:
    return [str(m.content) for m in messages if isinstance(m, HumanMessage)]


def test_follow_up_in_same_thread_sees_earlier_turn(table: Any) -> None:
    model = ScriptedChatModel(script=[_answer_turn("first answer"), _answer_turn("second answer")])
    client = _client(model)
    _say(client, "question one", "thread-a")
    events = _say(client, "question two", "thread-a")

    assert _text(events) == "second answer"
    turn_2 = model.seen[1]
    assert _human_texts(turn_2) == ["question one", "question two"]
    assert any(isinstance(m, AIMessage) and m.content == "first answer" for m in turn_2)


def test_new_thread_id_starts_clean(table: Any) -> None:
    model = ScriptedChatModel(script=[_answer_turn("first answer"), _answer_turn("second answer")])
    client = _client(model)
    _say(client, "question one", "thread-a")
    _say(client, "question two", "thread-b")

    turn_2 = model.seen[1]
    assert _human_texts(turn_2) == ["question two"]
    assert not any(isinstance(m, AIMessage) for m in turn_2)


def test_checkpoint_items_expire_in_seven_days(table: Any) -> None:
    model = ScriptedChatModel(script=[_answer_turn()])
    before = int(time.time())
    _say(_client(model), "question one", "thread-a")
    after = int(time.time())

    items = table.scan()["Items"]
    assert items
    for item in items:
        ttl = int(item["ttl"])
        assert before + THREAD_TTL_SECONDS - 5 <= ttl <= after + THREAD_TTL_SECONDS + 5


def test_runaway_tool_loop_stops_at_step_limit_and_stream_finishes(table: Any) -> None:
    script = [_tool_turn("الأجر الشهري") for _ in range(MODEL_CALLS_PER_TURN + 3)]
    model = ScriptedChatModel(script=script)
    events = _say(_client(model), "loop forever", "thread-a")

    assert model.calls == MODEL_CALLS_PER_TURN
    types = _types(events)
    assert types[-2:] == ["finish", "[DONE]"]
    assert "error" not in types


def test_long_thread_is_summarised_and_summary_not_streamed(
    table: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_module, "SUMMARY_TRIGGER_TOKENS", 30)
    monkeypatch.setattr(agent_module, "SUMMARY_KEEP_MESSAGES", 2)
    long_question = "word " * 40
    model = ScriptedChatModel(
        script=[
            _answer_turn("answer one"),
            AIMessage(content="SUMMARY-OF-EARLIER-TURNS"),  # summariser call on turn 2
            _answer_turn("answer two"),
        ]
    )
    client = _client(model)
    _say(client, long_question + "one", "thread-a")
    events = _say(client, "question two", "thread-a")

    assert model.calls == 3
    summariser_call, final_call = model.seen[1], model.seen[2]
    assert long_question + "one" in "".join(str(m.content) for m in summariser_call)
    assert any("SUMMARY-OF-EARLIER-TURNS" in str(m.content) for m in final_call)
    assert long_question + "one" not in _human_texts(final_call)
    assert _text(events) == "answer two"
    assert "SUMMARY" not in "".join(e["delta"] for e in _of_type(events, "text-delta"))
