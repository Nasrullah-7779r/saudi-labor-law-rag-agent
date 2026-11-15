"""Chat model switching against moto SSM (moto 5: `mock_aws`) with a fake clock."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any, cast

import boto3
import pytest
from langgraph.graph.state import CompiledStateGraph
from moto import mock_aws

from labor_law_agent.chat_model_switch import ChatModelSelector, SwitchingAgentProvider

PARAM = "/labor-law/chat-model-id"
MODEL_A = "model-a"
MODEL_B = "model-b"
TTL = 60.0


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def ssm() -> Iterator[Any]:
    with mock_aws():
        yield boto3.client("ssm", region_name="us-east-1")


def put(ssm: Any, value: str) -> None:
    ssm.put_parameter(Name=PARAM, Value=value, Type="String", Overwrite=True)


def make_selector(ssm: Any, clock: FakeClock) -> ChatModelSelector:
    return ChatModelSelector(ssm, PARAM, MODEL_A, ttl_seconds=TTL, clock=clock)


def test_reads_parameter_first_then_switches_only_after_ttl(ssm: Any) -> None:
    clock = FakeClock()
    put(ssm, MODEL_B)
    selector = make_selector(ssm, clock)

    assert selector.current_model_id() == MODEL_B  # first call reads SSM

    put(ssm, MODEL_A)
    clock.now += TTL - 1
    assert selector.current_model_id() == MODEL_B  # cached within TTL

    clock.now += 1
    assert selector.current_model_id() == MODEL_A  # TTL elapsed


def test_empty_parameter_value_is_ignored_and_warned(
    ssm: Any, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    put(ssm, MODEL_B)
    selector = make_selector(ssm, clock)
    assert selector.current_model_id() == MODEL_B  # switch first so "kept" means current, not fallback

    put(ssm, "   ")  # whitespace-only counts as empty after strip()
    clock.now += TTL
    with caplog.at_level(logging.WARNING, logger="labor_law_agent.chat_model_switch"):
        assert selector.current_model_id() == MODEL_B

    assert any("is empty" in r.getMessage() for r in caplog.records)


def test_missing_parameter_falls_back_then_keeps_current(
    ssm: Any, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FakeClock()
    selector = make_selector(ssm, clock)  # parameter does not exist

    with caplog.at_level(logging.WARNING, logger="labor_law_agent.chat_model_switch"):
        assert selector.current_model_id() == MODEL_A
    assert any("read failed" in r.getMessage() for r in caplog.records)

    put(ssm, MODEL_B)
    clock.now += TTL
    assert selector.current_model_id() == MODEL_B

    ssm.delete_parameter(Name=PARAM)
    clock.now += TTL
    assert selector.current_model_id() == MODEL_B  # SSM failure keeps current


class StubSelector:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    def current_model_id(self) -> str:
        return self.model_id


def test_provider_rebuilds_only_when_id_changes() -> None:
    selector = StubSelector(MODEL_A)
    built: list[str] = []

    def build(model_id: str) -> CompiledStateGraph[Any]:
        built.append(model_id)
        return cast("CompiledStateGraph[Any]", object())

    provider = SwitchingAgentProvider(cast(ChatModelSelector, selector), build)

    first = provider()
    assert provider() is first
    assert built == [MODEL_A]

    selector.model_id = MODEL_B
    second = provider()
    assert second is not first
    assert provider() is second
    assert built == [MODEL_A, MODEL_B]


def test_provider_keeps_old_agent_when_build_fails_after_first_success() -> None:
    selector = StubSelector(MODEL_A)
    fail = False
    calls: list[str] = []

    def build(model_id: str) -> CompiledStateGraph[Any]:
        calls.append(model_id)
        if fail:
            raise RuntimeError("boom")
        return cast("CompiledStateGraph[Any]", object())

    provider = SwitchingAgentProvider(cast(ChatModelSelector, selector), build)
    first = provider()

    fail = True
    selector.model_id = MODEL_B
    assert provider() is first
    assert provider() is first
    assert calls == [MODEL_A, MODEL_B, MODEL_B]  # retried, old agent served


def test_provider_raises_when_first_build_fails() -> None:
    def build(model_id: str) -> CompiledStateGraph[Any]:
        raise RuntimeError("boom")

    provider = SwitchingAgentProvider(cast(ChatModelSelector, StubSelector(MODEL_A)), build)
    with pytest.raises(RuntimeError):
        provider()
