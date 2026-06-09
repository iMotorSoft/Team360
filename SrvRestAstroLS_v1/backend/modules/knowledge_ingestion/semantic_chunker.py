"""Semantic chunker wrapper for Fase 1.4b.

Uses langchain_experimental SemanticChunker if available.
Requires langchain_experimental + OpenAIEmbeddings (already installed via langchain-openai).
"""

from __future__ import annotations

import hashlib
from typing import Any

from modules.knowledge_ingestion.markdown_chunker import ChunkResult

_SEMANTIC_CHUNKER_AVAILABLE: bool = False
_SEMANTIC_CHUNKER_IMPORT_ERROR: str | None = None

try:
    from langchain_experimental.text_splitter import SemanticChunker as _SemanticChunker
    from langchain_openai import OpenAIEmbeddings

    _SEMANTIC_CHUNKER_AVAILABLE = True
except ImportError as _exc:
    _SEMANTIC_CHUNKER_IMPORT_ERROR = str(_exc)


def is_semantic_chunker_available() -> bool:
    return _SEMANTIC_CHUNKER_AVAILABLE


def semantic_chunker_import_error() -> str | None:
    return _SEMANTIC_CHUNKER_IMPORT_ERROR


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2]


def _extract_title(content: str, max_chars: int = 100) -> str:
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:max_chars]
    return lines[0][:max_chars] if lines else ""


def chunk_semantic(
    markdown_text: str,
    *,
    base_metadata: dict[str, Any] | None = None,
) -> list[ChunkResult]:
    """Split Markdown into semantic chunks using SemanticChunker.

    Requires langchain_experimental and langchain-openai.
    Raises RuntimeError if SemanticChunker is not available.
    """
    if not _SEMANTIC_CHUNKER_AVAILABLE:
        raise RuntimeError(
            f"SemanticChunker is not available. "
            f"Import error: {_SEMANTIC_CHUNKER_IMPORT_ERROR or 'unknown'}. "
            "Install langchain_experimental to enable semantic chunking."
        )

    body = _strip_frontmatter(markdown_text)
    body = body.strip()
    if not body:
        return []

    global _SemanticChunker, OpenAIEmbeddings  # noqa: PLW0602

    embeddings = OpenAIEmbeddings()
    splitter = _SemanticChunker(
        embeddings=embeddings,
        breakpoint_threshold_type="percentile",
    )

    docs = splitter.split_text(body)
    meta = dict(base_metadata or {})

    chunks: list[ChunkResult] = []
    for i, doc_content in enumerate(docs):
        content = (
            doc_content.strip()
            if isinstance(doc_content, str)
            else str(doc_content).strip()
        )
        if not content:
            continue

        raw_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk_meta = dict(meta)
        chunk_meta["chunk_hash"] = raw_hash
        chunk_meta["chunk_strategy"] = "semantic"
        chunk_meta["semantic_chunk_index"] = i

        title = _extract_title(content)

        chunks.append(
            ChunkResult(
                chunk_index=i,
                title=title,
                content=content,
                heading_path=[],
                heading_level=0,
                char_count=len(content),
                content_hash=raw_hash,
                metadata=chunk_meta,
            )
        )

    return chunks
