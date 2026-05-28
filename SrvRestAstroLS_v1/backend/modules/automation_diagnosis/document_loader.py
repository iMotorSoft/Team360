"""Load Phase 1 knowledge documents from Markdown fixtures."""

from __future__ import annotations

from pathlib import Path

from .chunker import chunk_document
from .schemas import DEFAULT_KNOWLEDGE_SCOPE_ID, KnowledgeDocument, KnowledgeScope, new_id


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "knowledge"


def default_knowledge_scope() -> KnowledgeScope:
    return KnowledgeScope(
        id=DEFAULT_KNOWLEDGE_SCOPE_ID,
        name="Team360 Automation Diagnosis",
        retrieval_mode="rag",
        graph_enabled=False,
        metadata={
            "future_graph_ready": True,
            "description": "Internal Team360 criteria for automation diagnosis.",
        },
    )


def load_markdown_documents(
    scope_id: str = DEFAULT_KNOWLEDGE_SCOPE_ID,
    directory: Path = FIXTURES_DIR,
) -> tuple[list[KnowledgeDocument], list]:
    documents: list[KnowledgeDocument] = []
    chunks = []
    for path in sorted(directory.glob("*.md")):
        document = KnowledgeDocument(
            id=new_id("kdoc"),
            knowledge_scope_id=scope_id,
            title=path.stem.replace("_", " ").title(),
            source_path=str(path),
            content=path.read_text(encoding="utf-8"),
        )
        documents.append(document)
        chunks.extend(chunk_document(document))
    return documents, chunks
