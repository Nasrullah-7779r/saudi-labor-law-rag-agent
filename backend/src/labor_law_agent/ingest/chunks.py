"""Split articles into embeddable chunks with deterministic IDs. Pure, no I/O.

Cohere Embed v3 on Bedrock accepts at most 2048 characters per text
(https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v3.html),
so chunks stay under ``MAX_CHUNK_CHARS`` with headroom.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from labor_law_agent.ingest.parser import Article

MAX_CHUNK_CHARS = 1500
CHUNK_ID_PREFIX = "art-"
CHUNK_LANG = "ar"  # chunks hold the Arabic BOE text only


class ArticleChunk(BaseModel):
    id: str
    article_no: int
    chunk_no: int
    part: str | None
    chapter: str | None
    text_ar: str
    source_url: str
    version: date

    def vector_metadata(self) -> dict[str, str | int]:
        """Vector-store metadata; ``None`` fields are omitted (Pinecone rejects nulls)."""
        metadata: dict[str, str | int] = {
            "article_no": self.article_no,
            "chunk_no": self.chunk_no,
            "lang": CHUNK_LANG,
            "version": self.version.isoformat(),
            "source_url": self.source_url,
            "text": self.text_ar,  # langchain-pinecone's default text key
        }
        if self.chapter is not None:
            metadata["chapter"] = self.chapter
        if self.part is not None:
            metadata["part"] = self.part
        return metadata


def chunk_id(article_no: int, chunk_no: int) -> str:
    return f"{CHUNK_ID_PREFIX}{article_no:03d}-{chunk_no:02d}"


def _split_long_line(line: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for word in line.split(" "):
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
        while len(word) > max_chars:  # a single unbroken run longer than the limit
            pieces.append(word[:max_chars])
            word = word[max_chars:]
        current = word
    if current:
        pieces.append(current)
    return pieces


def _split_text(text: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        for piece in _split_long_line(line, max_chars) if len(line) > max_chars else [line]:
            candidate = f"{current}\n{piece}" if current else piece
            if len(candidate) <= max_chars:
                current = candidate
            else:
                parts.append(current)
                current = piece
    if current:
        parts.append(current)
    return parts


def chunk_article(article: Article, max_chars: int = MAX_CHUNK_CHARS) -> list[ArticleChunk]:
    """Ordered chunks sharing ``article_no``; one chunk when the article fits."""
    return [
        ArticleChunk(
            id=chunk_id(article.article_no, i),
            article_no=article.article_no,
            chunk_no=i,
            part=article.part,
            chapter=article.chapter,
            text_ar=text,
            source_url=article.source_url,
            version=article.version,
        )
        for i, text in enumerate(_split_text(article.text_ar, max_chars))
    ]
