"""Document embeddings via Bedrock Cohere Embed Multilingual v3.

Request/response shape: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v3.html
(``texts`` up to 96 per call, ``input_type`` ``search_document`` for stored corpus,
response ``embeddings`` is one 1024-float list per text). Model id checked with
``bedrock:ListFoundationModels`` in us-east-1 (ON_DEMAND).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol

COHERE_MULTILINGUAL_MODEL_ID = "cohere.embed-multilingual-v3"
COHERE_EMBED_DIMENSION = 1024
_MAX_TEXTS_PER_CALL = 96


class DocumentEmbedder(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class CohereBedrockEmbedder:
    def __init__(
        self, bedrock_runtime: Any, model_id: str = COHERE_MULTILINGUAL_MODEL_ID
    ) -> None:
        self._client = bedrock_runtime  # boto3 "bedrock-runtime" client
        self._model_id = model_id

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _MAX_TEXTS_PER_CALL):
            batch = list(texts[start : start + _MAX_TEXTS_PER_CALL])
            response = self._client.invoke_model(
                modelId=self._model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {"texts": batch, "input_type": "search_document", "truncate": "NONE"}
                ),
            )
            embeddings: list[list[float]] = json.loads(response["body"].read())["embeddings"]
            if len(embeddings) != len(batch):
                raise RuntimeError(f"expected {len(batch)} embeddings, got {len(embeddings)}")
            vectors.extend(embeddings)
        return vectors
