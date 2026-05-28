"""Knowledge repository and connector for RAG/GraphRAG-ready scopes."""

from __future__ import annotations

from typing import Any

from .document_loader import default_knowledge_scope, load_markdown_documents
from .retrieval import retrieve_chunks
from .schemas import KnowledgeChunk, KnowledgeDocument, KnowledgeScope, RetrievedContext


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self.scopes: dict[str, KnowledgeScope] = {}
        self.documents: dict[str, KnowledgeDocument] = {}
        self.chunks: dict[str, KnowledgeChunk] = {}

    def add_scope(self, scope: KnowledgeScope) -> None:
        self.scopes[scope.id] = scope

    def add_documents(self, documents: list[KnowledgeDocument], chunks: list[KnowledgeChunk]) -> None:
        for document in documents:
            self.documents[document.id] = document
        for chunk in chunks:
            self.chunks[chunk.id] = chunk

    def get_scope(self, scope_id: str) -> KnowledgeScope:
        try:
            return self.scopes[scope_id]
        except KeyError as exc:
            raise ValueError(f"Unknown knowledge scope: {scope_id}") from exc

    def search(self, scope_id: str, query: str, retrieval_mode: str | None = None, top_k: int = 5) -> RetrievedContext:
        scope = self.get_scope(scope_id)
        mode = retrieval_mode or scope.retrieval_mode
        return retrieve_chunks(list(self.chunks.values()), scope_id, query, mode, top_k)

    def scope_debug(self, scope_id: str) -> dict[str, Any]:
        scope = self.get_scope(scope_id)
        return {
            "scope": scope,
            "document_count": sum(1 for doc in self.documents.values() if doc.knowledge_scope_id == scope_id),
            "chunk_count": sum(1 for chunk in self.chunks.values() if chunk.knowledge_scope_id == scope_id),
        }


def build_default_knowledge_repository() -> InMemoryKnowledgeRepository:
    repository = InMemoryKnowledgeRepository()
    scope = default_knowledge_scope()
    documents, chunks = load_markdown_documents(scope.id)
    repository.add_scope(scope)
    repository.add_documents(documents, chunks)
    return repository
