"""Local structural Markdown chunker for Fase 1.4a.

Splits Markdown by headings (# to ###), preserves hierarchy,
does NOT use LLMs or SemanticChunker.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChunkResult:
    chunk_index: int
    title: str
    content: str
    heading_path: list[str]
    heading_level: int
    char_count: int
    content_hash: str
    metadata: dict[str, Any]


HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2]


def chunk_markdown(
    markdown_text: str,
    *,
    base_metadata: dict[str, Any] | None = None,
) -> list[ChunkResult]:
    """Split Markdown into structural chunks by headings.

    Ignores YAML frontmatter. Produces stable-ordered chunks.
    No headings -> a single chunk with the entire body.
    """
    body = _strip_frontmatter(markdown_text)
    body = body.strip()

    if not body:
        return []

    meta = dict(base_metadata or {})

    matches = list(HEADING_RE.finditer(body))
    if not matches:
        raw_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        chunk_meta = dict(meta)
        chunk_meta["chunk_hash"] = raw_hash
        chunk_meta["heading_path"] = []
        chunk_meta["heading_level"] = 0
        return [
            ChunkResult(
                chunk_index=0,
                title="",
                content=body,
                heading_path=[],
                heading_level=0,
                char_count=len(body),
                content_hash=raw_hash,
                metadata=chunk_meta,
            )
        ]

    chunks: list[ChunkResult] = []
    for i, match in enumerate(matches):
        level = len(match.group(1))
        heading_text = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)

        raw = body[start:end].strip()
        if not raw:
            continue

        raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        chunk_meta = dict(meta)
        chunk_meta["chunk_hash"] = raw_hash
        chunk_meta["heading_level"] = level

        if i == 0:
            path = [heading_text]
        else:
            prev = chunks[-1]
            if level > prev.heading_level:
                path = prev.heading_path + [heading_text]
            elif level == prev.heading_level:
                path = prev.heading_path[:-1] + [heading_text]
            else:
                base_path = prev.heading_path[:level - 1] if level > 1 else []
                path = base_path + [heading_text]

        chunk_meta["heading_path"] = list(path)

        chunks.append(
            ChunkResult(
                chunk_index=i,
                title=heading_text,
                content=raw,
                heading_path=list(path),
                heading_level=level,
                char_count=len(raw),
                content_hash=raw_hash,
                metadata=chunk_meta,
            )
        )

    return chunks
