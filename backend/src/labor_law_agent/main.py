"""Production app: wires the agent to Bedrock and Pinecone from environment settings.

Env (set by Terraform): ``CHAT_MODEL_ID`` (fallback), ``CHAT_MODEL_PARAMETER_NAME``,
``CHAT_MODEL_ALLOWLIST`` (comma-separated), ``CHAT_MODEL_PROVIDER``, ``CHAT_MAX_OUTPUT_TOKENS``,
``PINECONE_INDEX_NAME``, ``PINECONE_API_KEY_SECRET_ID``, ``USAGE_TABLE_NAME``,
``IP_DAILY_QUESTION_QUOTA``, ``GLOBAL_DAILY_TOKEN_BUDGET``. AWS access uses the Lambda role.

Docs: ``init_chat_model(model, model_provider="bedrock_converse", max_tokens=...)``
(https://docs.langchain.com/oss/python/langchain/models); ``BedrockEmbeddings`` embeds queries
with Cohere ``input_type="search_query"`` (langchain-aws 1.9); ``PineconeVectorStore(index=,
embedding=)`` (langchain-pinecone 0.2); ``Pinecone(api_key).Index(name=)`` (pinecone 7.x).
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from fastapi import FastAPI
from langchain.chat_models import init_chat_model
from langchain_aws import BedrockEmbeddings
from langchain_pinecone import PineconeVectorStore
from langgraph.graph.state import CompiledStateGraph
from pinecone import Pinecone
from pydantic import BaseModel

from labor_law_agent.agent import build_agent
from labor_law_agent.agent_responder import AgentChatResponder
from labor_law_agent.api import create_app
from labor_law_agent.chat_model_switch import ChatModelSelector, SwitchingAgentProvider
from labor_law_agent.ingest.embeddings import COHERE_MULTILINGUAL_MODEL_ID
from labor_law_agent.retrieval import PineconeLawRetriever
from labor_law_agent.usage_guard import DynamoUsageGuard, UsageLimits

DEFAULT_CHAT_MODEL_ID = "zai.glm-4.7-flash"  # keep in sync with infra chat_model_allowlist[0]
DEFAULT_CHAT_MODEL_PROVIDER = "bedrock_converse"
DEFAULT_MAX_OUTPUT_TOKENS = 1024
DEFAULT_IP_DAILY_QUESTION_QUOTA = 20  # keep in sync with infra ip_daily_question_quota
DEFAULT_GLOBAL_DAILY_TOKEN_BUDGET = 2_000_000  # keep in sync with infra global_daily_token_budget


class AgentSettings(BaseModel):
    chat_model_id: str = DEFAULT_CHAT_MODEL_ID
    chat_model_provider: str = DEFAULT_CHAT_MODEL_PROVIDER
    chat_model_parameter_name: str = ""  # empty: no runtime switching
    chat_model_allowlist: str = ""  # comma-separated model ids allowed by IAM
    chat_max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    pinecone_index_name: str
    pinecone_api_key_secret_id: str
    frontend_origin: str = ""
    usage_table_name: str
    ip_daily_question_quota: int = DEFAULT_IP_DAILY_QUESTION_QUOTA
    global_daily_token_budget: int = DEFAULT_GLOBAL_DAILY_TOKEN_BUDGET

    @classmethod
    def from_env(cls) -> AgentSettings:
        keys = cls.model_fields
        return cls.model_validate(
            {k: os.environ[k.upper()] for k in keys if k.upper() in os.environ}
        )


def build_app(settings: AgentSettings) -> FastAPI:
    pinecone_api_key = boto3.client("secretsmanager").get_secret_value(
        SecretId=settings.pinecone_api_key_secret_id
    )["SecretString"]
    vector_store = PineconeVectorStore(
        index=Pinecone(api_key=pinecone_api_key).Index(name=settings.pinecone_index_name),
        embedding=BedrockEmbeddings(model_id=COHERE_MULTILINGUAL_MODEL_ID),
    )
    retriever = PineconeLawRetriever(vector_store)

    def build_agent_for(model_id: str) -> CompiledStateGraph[Any]:
        model = init_chat_model(
            model_id,
            model_provider=settings.chat_model_provider,
            max_tokens=settings.chat_max_output_tokens,
        )
        return build_agent(model, retriever)

    if settings.chat_model_parameter_name:
        selector = ChatModelSelector(
            boto3.client("ssm"),
            settings.chat_model_parameter_name,
            allowlist=[m.strip() for m in settings.chat_model_allowlist.split(",") if m.strip()],
            fallback_model_id=settings.chat_model_id,
        )
        responder = AgentChatResponder.from_provider(
            SwitchingAgentProvider(selector, build_agent_for)
        )
    else:
        responder = AgentChatResponder(build_agent_for(settings.chat_model_id))
    guard = DynamoUsageGuard(
        settings.usage_table_name,
        UsageLimits(
            ip_daily_question_quota=settings.ip_daily_question_quota,
            global_daily_token_budget=settings.global_daily_token_budget,
        ),
        boto3.client("dynamodb"),
    )
    return create_app(
        responder, guard,
        cors_origins=(settings.frontend_origin,) if settings.frontend_origin else (),
    )


app = build_app(AgentSettings.from_env())
