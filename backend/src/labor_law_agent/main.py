"""Production app: wires the agent to Bedrock and Pinecone from environment settings.

Env (set by Terraform): ``CHAT_MODEL_ID``, ``CHAT_MODEL_PROVIDER``, ``CHAT_MAX_OUTPUT_TOKENS``,
``PINECONE_INDEX_NAME``, ``PINECONE_API_KEY_SECRET_ID``. AWS access uses the Lambda role.

Docs: ``init_chat_model(model, model_provider="bedrock_converse", max_tokens=...)``
(https://docs.langchain.com/oss/python/langchain/models); ``BedrockEmbeddings`` embeds queries
with Cohere ``input_type="search_query"`` (langchain-aws 1.9); ``PineconeVectorStore(index=,
embedding=)`` (langchain-pinecone 0.2); ``Pinecone(api_key).Index(name=)`` (pinecone 7.x).
"""

from __future__ import annotations

import os

import boto3
from fastapi import FastAPI
from langchain.chat_models import init_chat_model
from langchain_aws import BedrockEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
from pydantic import BaseModel

from labor_law_agent.agent import build_agent
from labor_law_agent.agent_responder import AgentChatResponder
from labor_law_agent.api import create_app
from labor_law_agent.ingest.embeddings import COHERE_MULTILINGUAL_MODEL_ID
from labor_law_agent.retrieval import PineconeLawRetriever

DEFAULT_CHAT_MODEL_ID = "us.amazon.nova-lite-v1:0"  # keep in sync with infra chat_model_id
DEFAULT_CHAT_MODEL_PROVIDER = "bedrock_converse"
DEFAULT_MAX_OUTPUT_TOKENS = 1024


class AgentSettings(BaseModel):
    chat_model_id: str = DEFAULT_CHAT_MODEL_ID
    chat_model_provider: str = DEFAULT_CHAT_MODEL_PROVIDER
    chat_max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    pinecone_index_name: str
    pinecone_api_key_secret_id: str

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
    model = init_chat_model(
        settings.chat_model_id,
        model_provider=settings.chat_model_provider,
        max_tokens=settings.chat_max_output_tokens,
    )
    agent = build_agent(model, PineconeLawRetriever(vector_store))
    return create_app(AgentChatResponder(agent))


app = build_app(AgentSettings.from_env())
