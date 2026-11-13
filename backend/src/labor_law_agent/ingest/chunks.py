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
    """One embeddable piece of an article; one chunk = one vector in the index.

    Attributes:
        id: Deterministic vector id, e.g. ``art-002-01`` (see ``chunk_id``).
        article_no: Article this piece belongs to (shared by all its chunks).
        chunk_no: Position of this piece within the article, from 0.
        part, chapter, source_url, version: Copied from the article.
        text_ar: The piece's Arabic text (at most ``MAX_CHUNK_CHARS``).
    """

    id: str
    article_no: int
    chunk_no: int
    part: str | None
    chapter: str | None
    text_ar: str
    source_url: str
    version: date

    def vector_metadata(self) -> dict[str, str | int]:
        """Metadata stored next to the vector, used to cite and show the article.

        ``None`` fields (part/chapter) are left out because Pinecone rejects nulls.
        The text is stored under ``text``, the key langchain-pinecone reads by default.
        """
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
    """Deterministic id, so re-ingesting overwrites the same vectors.

    Example:
        >>> chunk_id(2, 1)
        'art-002-01'
    """
    return f"{CHUNK_ID_PREFIX}{article_no:03d}-{chunk_no:02d}"


def _split_long_line(line: str, max_chars: int) -> list[str]:
    """Split one line at spaces into pieces of at most ``max_chars``.

    A single word longer than the limit is cut into fixed-size slices.
    """
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
    """Pack whole lines into pieces of at most ``max_chars``, keeping their order.

    Lines longer than the limit are first split at spaces (``_split_long_line``).
    """
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
    """Split an article into ordered chunks that all share its ``article_no``.

    Args:
        article: Parsed article.
        max_chars: Upper bound per chunk; default leaves headroom under Cohere's 2048.

    Returns:
        One chunk when the article fits, otherwise several with ``chunk_no`` 0, 1, ...
    """
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
