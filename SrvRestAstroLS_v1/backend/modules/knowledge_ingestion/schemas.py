"""Schemas for Knowledge Ingestion Phase 1.

Defines the contract for document ingestion metadata and validation.
SQLAlchemy/Pydantic-free — uses dataclasses and TypedDict per
Team360 Pydantic Boundary policy (lat.md/postgres-driver-policy.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Valid ingestion run statuses (aligned with migration 006)
INGESTION_RUN_STATUSES = frozenset({
    "pending", "running", "validating", "converting", "chunking",
    "embedding", "indexing", "completed", "failed",
})

# Valid visibility levels
VISIBILITY_LEVELS = frozenset({"public", "internal", "restricted", "confidential"})

# Valid document types for ingestion
DOCUMENT_TYPES = frozenset({
    "policy", "guide", "procedure", "template",
    "faq", "reference", "report", "other",
})

# Valid scope types
SCOPE_TYPES = frozenset({
    "global", "package", "partner", "organization",
    "workspace", "service", "assistant_instance", "session",
})

# Valid source types for ingestion
SOURCE_TYPES = frozenset({"markdown", "pdf", "text", "html"})

# Supported locales
SUPPORTED_LOCALES = frozenset({"es", "en", "he"})


@dataclass
class IngestionMetadata:
    """Mandatory metadata contract for every ingested document.

    This is the minimum required set of fields. All fields must be
    provided at ingestion time for the document to be accepted.
    """
    knowledge_scope_code: str
    scope_type: str
    organization_code: str
    workspace_code: str
    node_path: str
    area_key: str
    topic_key: str
    document_type: str
    visibility: str
    access_tags: list[str]
    locale: str
    version: str
    title: str
    source_type: str = "markdown"
    package_code: str = ""
    assistant_instance_code: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.knowledge_scope_code:
            errors.append("knowledge_scope_code is required")

        if self.scope_type not in SCOPE_TYPES:
            errors.append(
                f"scope_type must be one of {sorted(SCOPE_TYPES)}, "
                f"got {self.scope_type!r}"
            )

        if not self.organization_code:
            errors.append("organization_code is required")

        if not self.workspace_code:
            errors.append("workspace_code is required")

        if not self.node_path or not self.node_path.startswith("/"):
            errors.append(
                "node_path is required and must start with '/'"
            )
        elif self.node_path != "/" and self.node_path.endswith("/"):
            errors.append(
                "node_path must not end with '/' (except root '/')"
            )

        if not self.area_key:
            errors.append("area_key is required")
        elif "/" in self.area_key:
            errors.append("area_key must not contain '/'")

        if not self.topic_key:
            errors.append("topic_key is required")
        elif "/" in self.topic_key:
            errors.append("topic_key must not contain '/'")

        if self.document_type not in DOCUMENT_TYPES:
            errors.append(
                f"document_type must be one of {sorted(DOCUMENT_TYPES)}, "
                f"got {self.document_type!r}"
            )

        if self.visibility not in VISIBILITY_LEVELS:
            errors.append(
                f"visibility must be one of {sorted(VISIBILITY_LEVELS)}, "
                f"got {self.visibility!r}"
            )

        if not self.access_tags:
            errors.append("access_tags must not be empty")
        elif any(not t for t in self.access_tags):
            errors.append("access_tags must not contain empty strings")

        if self.locale not in SUPPORTED_LOCALES:
            errors.append(
                f"locale must be one of {sorted(SUPPORTED_LOCALES)}, "
                f"got {self.locale!r}"
            )

        if not self.version:
            errors.append("version is required")

        if not self.title:
            errors.append("title is required")

        if self.source_type not in SOURCE_TYPES:
            errors.append(
                f"source_type must be one of {sorted(SOURCE_TYPES)}, "
                f"got {self.source_type!r}"
            )

        return errors

    def to_metadata_dict(self) -> dict[str, Any]:
        """Convert to flat dict suitable for metadata_jsonb."""
        return {
            "title": self.title,
            "knowledge_scope_code": self.knowledge_scope_code,
            "scope_type": self.scope_type,
            "organization_code": self.organization_code,
            "workspace_code": self.workspace_code,
            "package_code": self.package_code,
            "assistant_instance_code": self.assistant_instance_code,
            "node_path": self.node_path,
            "area_key": self.area_key,
            "topic_key": self.topic_key,
            "document_type": self.document_type,
            "visibility": self.visibility,
            "access_tags": self.access_tags,
            "locale": self.locale,
            "version": self.version,
            "source_type": self.source_type,
        }


@dataclass
class IngestionRunRecord:
    id: str
    knowledge_scope_id: str
    workspace_id: str | None = None
    document_source: str = ""
    metadata_snapshot: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    phases_jsonb: dict[str, Any] = field(default_factory=dict)
    chunk_count: int = 0
    token_count: int = 0
    error_code: str | None = None
    error_detail: str | None = None
    started_at_utc: str | None = None
    completed_at_utc: str | None = None
    updated_at_utc: str | None = None


# Supported ingestion phases (ordered execution steps)
# 'register_completion' is handled inline, not as a processing phase.
# @lat: [[knowledge-rag-graphrag#Phase 1 Model]]
INGESTION_PHASES = [
    "validate_metadata",
    "convert_to_markdown",
    "semantic_chunk",
    "save_document_chunks",
    "generate_embeddings",
    "index",
]
