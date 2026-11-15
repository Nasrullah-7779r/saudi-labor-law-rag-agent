"""Runtime chat-model switching: an SSM parameter names the Bedrock chat model.

The active model id is read from an SSM Parameter Store ``String`` parameter at most once per
TTL. Any non-empty id is taken as-is (IAM allows any Bedrock model); if SSM fails or the value
is empty, the current model stays and a warning is logged.

Docs: ``SSM.Client.get_parameter(Name=...)`` returns ``{"Parameter": {"Value": ...}}``
(https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ssm/client/get_parameter.html).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60.0


class SsmParameterClient(Protocol):
    """The slice of the boto3 SSM client this module uses."""

    def get_parameter(self, *, Name: str) -> Any: ...  # boto3 keyword casing


class ChatModelSelector:
    """Resolves the active chat model id, refreshing from SSM at most once per TTL."""

    def __init__(
        self,
        ssm: SsmParameterClient,
        parameter_name: str,
        fallback_model_id: str,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ssm = ssm
        self._parameter_name = parameter_name
        self._ttl = ttl_seconds
        self._clock = clock
        self._model_id = fallback_model_id
        self._next_refresh = float("-inf")  # first call reads SSM

    def current_model_id(self) -> str:
        now = self._clock()
        if now < self._next_refresh:
            return self._model_id
        self._next_refresh = now + self._ttl
        try:
            wanted = str(self._ssm.get_parameter(Name=self._parameter_name)["Parameter"]["Value"])
        except Exception:
            logger.warning(
                "chat model parameter read failed; keeping %s", self._model_id, exc_info=True
            )
            return self._model_id
        wanted = wanted.strip()
        if not wanted:
            logger.warning("chat model parameter is empty; keeping %s", self._model_id)
        elif wanted != self._model_id:
            logger.info("chat model switched %s -> %s", self._model_id, wanted)
            self._model_id = wanted
        return self._model_id


class SwitchingAgentProvider:
    """Returns the agent for the selector's current model, rebuilding it when the id changes."""

    def __init__(
        self,
        selector: ChatModelSelector,
        build_agent_for: Callable[[str], CompiledStateGraph[Any]],
    ) -> None:
        self._selector = selector
        self._build = build_agent_for
        self._lock = threading.Lock()
        self._model_id: str | None = None
        self._agent: CompiledStateGraph[Any] | None = None

    def __call__(self) -> CompiledStateGraph[Any]:
        with self._lock:
            model_id = self._selector.current_model_id()
            if self._agent is None or model_id != self._model_id:
                try:
                    self._agent = self._build(model_id)
                    self._model_id = model_id
                except Exception:
                    if self._agent is None:
                        raise
                    logger.warning(
                        "building agent for %s failed; keeping %s",
                        model_id, self._model_id, exc_info=True,
                    )
            return self._agent
