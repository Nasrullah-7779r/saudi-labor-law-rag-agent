"""Ingest job: BOE HTML -> articles -> chunks -> embeddings -> vector index."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from labor_law_agent.ingest.chunks import chunk_article
from labor_law_agent.ingest.embeddings import DocumentEmbedder
from labor_law_agent.ingest.parser import parse_articles
from labor_law_agent.ingest.vector_index import ChunkIndex

# Penalties part (articles 229-242): the BOE page mixes pre-2013 numbering with renumbered
# and added articles (duplicate 233-235, "229 bis", unheaded "currently X / formerly Y"
# items). Skipped in v1 until a confirmed mapping exists.
PENALTIES_PART_EXCLUDED = frozenset(range(229, 243))
# Last article of the consolidated law; guards against a truncated page passing the gap check.
LAST_ARTICLE_NO = 245


class IngestAbortedError(RuntimeError):
    """Raised when the parsed law looks incomplete (e.g. a truncated page)."""


class IngestSummary(BaseModel):
    """What one ingest run did; printed as JSON by the CLI."""

    articles: int
    chunks: int
    excluded_article_nos: list[int]
    deleted_stale: list[str]


def run_ingest(
    html: str,
    *,
    source_url: str,
    version: date,
    embedder: DocumentEmbedder,
    index: ChunkIndex,
    excluded: frozenset[int] = PENALTIES_PART_EXCLUDED,
    last_article_no: int = LAST_ARTICLE_NO,
) -> IngestSummary:
    """Parse, chunk, embed and store the law; safe to re-run.

    Args:
        html: Raw BOE page HTML.
        source_url: URL stored on every article.
        version: Law version date stored on every article.
        embedder: Turns chunk texts into vectors.
        index: Stores the vectors and removes stale ones.
        excluded: Article numbers to skip (default: penalties part 229-242).
        last_article_no: Expected last article; guards against a truncated page.

    Returns:
        Counts of articles and chunks, the skipped numbers and the deleted stale ids.

    Raises:
        ArticleParseError: The page failed parser validation.
        IngestAbortedError: The last article is not ``last_article_no``.
    """
    articles = parse_articles(html, source_url=source_url, version=version, excluded=excluded)
    if (found := articles[-1].article_no) != last_article_no:
        raise IngestAbortedError(f"last article is {found}, expected {last_article_no}")
    chunks = [c for a in articles for c in chunk_article(a)]
    vectors = embedder.embed_documents([c.text_ar for c in chunks])
    index.upsert_chunks(chunks, vectors)
    deleted = index.delete_stale({c.id for c in chunks})
    return IngestSummary(
        articles=len(articles),
        chunks=len(chunks),
        excluded_article_nos=sorted(excluded),
        deleted_stale=deleted,
    )
