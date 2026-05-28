"""Simple Markdown chunker for Phase 1 RAG."""

from __future__ import annotations

import re

from .schemas import KnowledgeChunk, KnowledgeDocument, new_id


HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def _split_markdown_sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(HEADING_RE.finditer(markdown))
    if not matches:
        return [("Documento", markdown.strip())]

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        content = markdown[start:end].strip()
        if content:
            sections.append((title, content))
    return sections or [("Documento", markdown.strip())]


def chunk_document(document: KnowledgeDocument, max_chars: int = 1200) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    ordinal = 0
    for section_title, section_content in _split_markdown_sections(document.content):
        paragraphs = [part.strip() for part in section_content.split("\n\n") if part.strip()]
        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(_make_chunk(document, section_title, current, ordinal))
                ordinal += 1
            current = paragraph
        if current:
            chunks.append(_make_chunk(document, section_title, current, ordinal))
            ordinal += 1
    return chunks


def _make_chunk(document: KnowledgeDocument, title: str, content: str, ordinal: int) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=new_id("kchunk"),
        knowledge_scope_id=document.knowledge_scope_id,
        document_id=document.id,
        title=title,
        content=content,
        ordinal=ordinal,
        metadata={"source_path": document.source_path},
    )
