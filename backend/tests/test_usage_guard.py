"""Usage guard through `POST /chat`, backed by moto DynamoDB (moto 5: `mock_aws`)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from fakes import RecordingChatResponder
from fastapi.testclient import TestClient
from moto import mock_aws

from labor_law_agent.api import create_app
from labor_law_agent.usage_guard import DynamoUsageGuard, UsageLimits

TABLE = "usage-guard-test"
IP_QUOTA = 3
TOKEN_BUDGET = 100


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def ddb(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=TABLE,
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield client


@pytest.fixture
def clock() -> Clock:
    return Clock(datetime(2026, 1, 10, 12, 0, tzinfo=UTC))


@pytest.fixture
def responder() -> RecordingChatResponder:
    return RecordingChatResponder(input_tokens=10, output_tokens=5)


@pytest.fixture
def client(ddb: Any, clock: Clock, responder: RecordingChatResponder) -> TestClient:
    guard = DynamoUsageGuard(
        TABLE,
        UsageLimits(ip_daily_question_quota=IP_QUOTA, global_daily_token_budget=TOKEN_BUDGET),
        ddb,
        now=clock,
    )
    return TestClient(create_app(responder, guard))


def _ask(client: TestClient, ip: str | None = None, **headers: str) -> Any:
    h = dict(headers)
    if ip is not None:
        h["x-amzn-request-context"] = json.dumps({"identity": {"sourceIp": ip}})
    return client.post("/chat", json={"message": "hello"}, headers=h)


def _usage(response: Any) -> dict[str, int]:
    for frame in response.text.split("\n\n"):
        if frame.startswith("data: {"):
            event = json.loads(frame[len("data: ") :])
            if event["type"] == "data-usage":
                return event["data"]  # type: ignore[no-any-return]
    raise AssertionError("no data-usage event")


def test_ip_quota_returns_429_and_skips_responder(
    client: TestClient, responder: RecordingChatResponder
) -> None:
    for _ in range(IP_QUOTA):
        assert _ask(client, "1.1.1.1").status_code == 200
    assert len(responder.turns) == IP_QUOTA

    blocked = _ask(client, "1.1.1.1")
    assert blocked.status_code == 429
    assert blocked.json() == {"error": "ip_quota"}
    assert len(responder.turns) == IP_QUOTA


def test_different_ips_have_independent_quotas(client: TestClient) -> None:
    for _ in range(IP_QUOTA):
        _ask(client, "1.1.1.1")
    assert _ask(client, "1.1.1.1").status_code == 429
    assert _ask(client, "2.2.2.2").status_code == 200


def test_x_forwarded_for_cannot_bypass_quota(client: TestClient) -> None:
    for i in range(IP_QUOTA):
        assert _ask(client, "1.1.1.1", **{"x-forwarded-for": f"9.9.9.{i}"}).status_code == 200
    blocked = _ask(client, "1.1.1.1", **{"x-forwarded-for": "9.9.9.200"})
    assert blocked.status_code == 429
    assert blocked.json() == {"error": "ip_quota"}


def test_falls_back_to_client_host_without_request_context(client: TestClient) -> None:
    for _ in range(IP_QUOTA):
        assert _ask(client, None, **{"x-forwarded-for": "8.8.8.8"}).status_code == 200
    assert _ask(client, None, **{"x-forwarded-for": "7.7.7.7"}).status_code == 429


def test_tokens_recorded_after_stream_and_global_budget_blocks(
    client: TestClient, responder: RecordingChatResponder, ddb: Any
) -> None:
    # 15 tokens per turn; budget 100 -> 7 turns reach 105 >= 100. Spread over IPs.
    for i in range(7):
        assert _ask(client, f"10.0.0.{i}").status_code == 200
    item = ddb.get_item(TableName=TABLE, Key={"pk": {"S": "global#2026-01-10"}})["Item"]
    assert int(item["tokens"]["N"]) == 105

    calls = len(responder.turns)
    blocked = _ask(client, "10.0.0.99")
    assert blocked.status_code == 429
    assert blocked.json() == {"error": "global_budget"}
    assert len(responder.turns) == calls


def test_global_budget_rejection_does_not_consume_ip_quota(
    client: TestClient, ddb: Any
) -> None:
    ddb.put_item(
        TableName=TABLE,
        Item={"pk": {"S": "global#2026-01-10"}, "tokens": {"N": str(TOKEN_BUDGET)}},
    )
    assert _ask(client, "1.1.1.1").json() == {"error": "global_budget"}
    assert "Item" not in ddb.get_item(
        TableName=TABLE, Key={"pk": {"S": "ip#2026-01-10#1.1.1.1"}}
    )


def test_remaining_questions_decrements(client: TestClient) -> None:
    remaining = [_usage(_ask(client, "1.1.1.1"))["remaining_questions"] for _ in range(IP_QUOTA)]
    assert remaining == [IP_QUOTA - 1 - i for i in range(IP_QUOTA)]


def test_new_utc_day_resets_ip_quota_and_global_budget(client: TestClient, clock: Clock) -> None:
    for _ in range(IP_QUOTA):
        _ask(client, "1.1.1.1")
    assert _ask(client, "1.1.1.1").status_code == 429

    clock.now = datetime(2026, 1, 11, 0, 0, 1, tzinfo=UTC)
    response = _ask(client, "1.1.1.1")
    assert response.status_code == 200
    assert _usage(response)["remaining_questions"] == IP_QUOTA - 1


def test_items_carry_expires_at_after_their_day(client: TestClient, ddb: Any) -> None:
    _ask(client, "1.1.1.1")
    day_end = int(datetime(2026, 1, 11, tzinfo=UTC).timestamp())
    for pk in ("ip#2026-01-10#1.1.1.1", "global#2026-01-10"):
        item = ddb.get_item(TableName=TABLE, Key={"pk": {"S": pk}})["Item"]
        assert int(item["expires_at"]["N"]) > day_end
