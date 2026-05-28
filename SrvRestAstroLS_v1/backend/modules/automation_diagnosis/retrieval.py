"""Simple keyword retrieval for Phase 1 RAG."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .schemas import KnowledgeChunk, RetrievedContext


TOKEN_RE = re.compile(r"[a-zA-Z0-9_áéíóúñÁÉÍÓÚÑ]+")
STOPWORDS = {
    "de", "la", "el", "y", "o", "que", "con", "para", "por", "un", "una",
    "the", "and", "or", "to", "with", "in", "on",
}


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "") if token.lower() not in STOPWORDS]


def score_chunk(query_tokens: list[str], chunk: KnowledgeChunk) -> float:
    if not query_tokens:
        return 0.0
    chunk_tokens = Counter(tokenize(f"{chunk.title} {chunk.content}"))
    score = 0.0
    for token in query_tokens:
        score += chunk_tokens.get(token, 0)
    return score / max(1, len(query_tokens))


def retrieve_chunks(
    chunks: list[KnowledgeChunk],
    knowledge_scope_id: str,
    query: str,
    retrieval_mode: str = "rag",
    top_k: int = 5,
) -> RetrievedContext:
    if retrieval_mode == "none":
        return RetrievedContext(knowledge_scope_id, retrieval_mode, query, [])
    query_tokens = tokenize(query)
    candidates = [
        (score_chunk(query_tokens, chunk), chunk)
        for chunk in chunks
        if chunk.knowledge_scope_id == knowledge_scope_id
    ]
    ranked = [item for item in sorted(candidates, key=lambda item: item[0], reverse=True) if item[0] > 0]
    selected = ranked[:top_k]
    return RetrievedContext(
        knowledge_scope_id=knowledge_scope_id,
        retrieval_mode=retrieval_mode,
        query=query,
        chunks=[
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "title": chunk.title,
                "content": chunk.content,
                "score": round(score, 4),
                "metadata": chunk.metadata,
            }
            for score, chunk in selected
        ],
    )


def retrieved_context_as_prompt(context: RetrievedContext) -> str:
    parts: list[str] = []
    for index, chunk in enumerate(context.chunks, start=1):
        parts.append(f"[{index}] {chunk['title']}\n{chunk['content']}")
    return "\n\n".join(parts)
