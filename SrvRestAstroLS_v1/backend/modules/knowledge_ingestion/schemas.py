"""Schemas for Knowledge Ingestion Phase 1.

Defines the contract for document ingestion metadata and validation.
SQLAlchemy/Pydantic-free — uses dataclasses and TypedDict per
Team360 Pydantic Boundary policy (lat.md/postgres-driver-policy.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
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

# Organization capability roles are not user roles.
ORGANIZATION_ROLE_CODES = frozenset({
    "platform_owner",
    "platform_admin",
    "service_provider",
    "technical_operator",
    "partner",
    "reseller",
    "client",
    "internal_client",
    "demo_client",
    "content_owner",
    "billing_owner",
})

# Member roles apply to a user inside one organization.
ORGANIZATION_MEMBER_ROLE_CODES = frozenset({
    "organization_owner",
    "organization_admin",
    "technical_admin",
    "content_admin",
    "billing_admin",
    "operator",
    "viewer",
})


def _validate_code(name: str, value: str, *, required: bool = True) -> list[str]:
    errors: list[str] = []
    if not value:
        if required:
            errors.append(f"{name} is required")
        return errors
    if "/" in value:
        errors.append(f"{name} must not contain '/'")
    if value.strip() != value:
        errors.append(f"{name} must not have leading or trailing whitespace")
    return errors


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
    service_code: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []

        errors.extend(_validate_code("knowledge_scope_code", self.knowledge_scope_code))
        errors.extend(_validate_code("organization_code", self.organization_code))
        errors.extend(_validate_code("workspace_code", self.workspace_code))
        errors.extend(_validate_code("package_code", self.package_code, required=False))
        errors.extend(
            _validate_code(
                "assistant_instance_code",
                self.assistant_instance_code,
                required=False,
            )
        )
        errors.extend(_validate_code("service_code", self.service_code, required=False))

        if self.scope_type not in SCOPE_TYPES:
            errors.append(
                f"scope_type must be one of {sorted(SCOPE_TYPES)}, "
                f"got {self.scope_type!r}"
            )

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
            "service_code": self.service_code,
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
class IngestionContextRequest:
    organization_code: str
    workspace_code: str
    knowledge_scope_code: str
    package_code: str | None = None
    assistant_instance_code: str | None = None
    worker_code: str = "knowledge_ingestion_worker"
    triggered_by_email: str | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        errors.extend(_validate_code("organization_code", self.organization_code))
        errors.extend(_validate_code("workspace_code", self.workspace_code))
        errors.extend(_validate_code("knowledge_scope_code", self.knowledge_scope_code))
        errors.extend(
            _validate_code("package_code", self.package_code or "", required=False)
        )
        errors.extend(
            _validate_code(
                "assistant_instance_code",
                self.assistant_instance_code or "",
                required=False,
            )
        )
        errors.extend(_validate_code("worker_code", self.worker_code))
        if self.triggered_by_email is not None:
            email = self.triggered_by_email.strip()
            if email != self.triggered_by_email:
                errors.append(
                    "triggered_by_email must not have leading or trailing whitespace"
                )
            if "@" not in email:
                errors.append("triggered_by_email must be an email-like value")
        return errors


@dataclass
class IngestionContext:
    organization_code: str
    organization_id: str
    workspace_code: str
    workspace_id: str
    knowledge_scope_code: str
    knowledge_scope_id: str
    package_code: str | None = None
    automation_package_id: str | None = None
    assistant_instance_code: str | None = None
    assistant_instance_id: str | None = None
    worker_code: str = "knowledge_ingestion_worker"
    worker_definition_id: str = ""
    triggered_by_email: str | None = None
    triggered_by_user_id: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "organization_code": self.organization_code,
            "organization_id": self.organization_id,
            "workspace_code": self.workspace_code,
            "workspace_id": self.workspace_id,
            "knowledge_scope_code": self.knowledge_scope_code,
            "knowledge_scope_id": self.knowledge_scope_id,
            "package_code": self.package_code,
            "automation_package_id": self.automation_package_id,
            "assistant_instance_code": self.assistant_instance_code,
            "assistant_instance_id": self.assistant_instance_id,
            "worker_code": self.worker_code,
            "worker_definition_id": self.worker_definition_id,
            "triggered_by_email": self.triggered_by_email,
            "triggered_by_user_id": self.triggered_by_user_id,
            "warnings": self.warnings,
        }


@dataclass
class IngestionRunRecord:
    id: str
    knowledge_scope_id: str
    organization_id: str | None = None
    workspace_id: str | None = None
    triggered_by_user_id: str | None = None
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


# ---------------------------------------------------------------------------
# Package scanner schemas (Fase 1.2)
# ---------------------------------------------------------------------------


@dataclass
class DocumentValidationIssue:
    path: str
    field: str
    message: str
    severity: str = "error"


@dataclass
class ParsedKnowledgeDocument:
    path: Path
    relative_path: str
    source_section: str
    has_frontmatter: bool
    frontmatter: dict[str, Any] | None
    valid: bool
    candidate_for_ingestion: bool
    issues: list[DocumentValidationIssue]


@dataclass
class PackageScanRequest:
    package_code: str
    package_root: str
    dry_run: bool = True
    include_drafts: bool = False
    experimental: bool = False


@dataclass
class PackageScanResult:
    package_code: str
    package_root: str
    scanned_count: int
    valid_count: int
    invalid_count: int
    candidate_count: int
    skipped_count: int
    documents: list[ParsedKnowledgeDocument]
    warnings: list[str]
    errors: list[str]


@dataclass
class PackageMetadata:
    package_profile: dict[str, Any]
    scope_mapping: dict[str, Any]
    access_tags: dict[str, Any]


# ---------------------------------------------------------------------------
# Persistence schemas (Fase 1.3b)
# ---------------------------------------------------------------------------


class DocumentUpsertStatus:
    INSERTED = "inserted"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"
    INVALID = "invalid"


@dataclass
class KnowledgeDocumentPersistenceResult:
    relative_path: str
    status: str  # DocumentUpsertStatus.*
    document_id: str | None = None
    action: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PackagePersistResult:
    package_code: str
    package_root: str
    scanned_count: int
    candidate_count: int
    persisted_count: int
    inserted_count: int
    updated_count: int
    unchanged_count: int
    skipped_count: int
    invalid_count: int
    documents: list[KnowledgeDocumentPersistenceResult]
    warnings: list[str]
    errors: list[str]
    run_id: str | None = None
