"""CLI: ``python -m labor_law_agent.ingest --html-file law.html --version 2025-02-19``.

Env: ``PINECONE_INDEX_NAME``, ``PINECONE_API_KEY_SECRET_ID`` (Secrets Manager, plain string),
AWS credentials/region from the standard chain. Creates the serverless index on first run.
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

import boto3
from pinecone import AwsRegion, CloudProvider, Pinecone, ServerlessSpec

from labor_law_agent.ingest.embeddings import COHERE_EMBED_DIMENSION, CohereBedrockEmbedder
from labor_law_agent.ingest.job import run_ingest
from labor_law_agent.ingest.vector_index import PineconeChunkIndex


def _open_chunk_index(pc: Pinecone, name: str) -> PineconeChunkIndex:
    if not pc.has_index(name):
        pc.create_index(
            name=name,
            dimension=COHERE_EMBED_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud=CloudProvider.AWS, region=AwsRegion.US_EAST_1),
        )
    return PineconeChunkIndex(pc.Index(host=pc.describe_index(name).host))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest the BOE Labor Law into Pinecone.")
    parser.add_argument("--html-file", type=Path, required=True)
    parser.add_argument("--version", type=date.fromisoformat, required=True)
    parser.add_argument("--source-url", required=True)
    args = parser.parse_args()

    secret_id = os.environ["PINECONE_API_KEY_SECRET_ID"]
    pinecone_api_key = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)[
        "SecretString"
    ]
    index = _open_chunk_index(Pinecone(api_key=pinecone_api_key), os.environ["PINECONE_INDEX_NAME"])

    summary = run_ingest(
        args.html_file.read_text(encoding="utf-8"),
        source_url=args.source_url,
        version=args.version,
        embedder=CohereBedrockEmbedder(boto3.client("bedrock-runtime")),
        index=index,
    )
    print(summary.model_dump_json())


if __name__ == "__main__":
    main()
