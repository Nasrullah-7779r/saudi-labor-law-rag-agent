import io
import json
from typing import Any

import pytest

from labor_law_agent.ingest.embeddings import CohereBedrockEmbedder


class FakeBedrockRuntime:
    """invoke_model fake: one vector [n] per text, n being the text's global index."""

    def __init__(self, drop_one: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._drop_one = drop_one

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        texts = json.loads(kwargs["body"])["texts"]
        embeddings = [[float(t)] for t in texts]  # texts are numeric strings
        if self._drop_one:
            embeddings = embeddings[:-1]
        return {"body": io.BytesIO(json.dumps({"embeddings": embeddings}).encode())}


def test_request_shape() -> None:
    client = FakeBedrockRuntime()
    CohereBedrockEmbedder(client).embed_documents(["1", "2"])
    (call,) = client.calls
    assert call["modelId"] == "cohere.embed-multilingual-v3"
    assert json.loads(call["body"]) == {
        "texts": ["1", "2"],
        "input_type": "search_document",
        "truncate": "NONE",
    }


def test_batches_of_96_preserve_order() -> None:
    client = FakeBedrockRuntime()
    texts = [str(i) for i in range(200)]
    vectors = CohereBedrockEmbedder(client).embed_documents(texts)
    assert [len(json.loads(c["body"])["texts"]) for c in client.calls] == [96, 96, 8]
    assert vectors == [[float(i)] for i in range(200)]


def test_empty_input_makes_no_calls() -> None:
    client = FakeBedrockRuntime()
    assert CohereBedrockEmbedder(client).embed_documents([]) == []
    assert client.calls == []


def test_embedding_count_mismatch_raises() -> None:
    with pytest.raises(RuntimeError, match="expected 3 embeddings, got 2"):
        CohereBedrockEmbedder(FakeBedrockRuntime(drop_one=True)).embed_documents(["1", "2", "3"])
