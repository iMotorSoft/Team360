"""Shared schemas and constants for automation diagnosis."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


DEFAULT_ORGANIZATION_ID = "org_team360"
DEFAULT_WORKSPACE_ID = "team360_public_site"
DEFAULT_ASSISTANT_INSTANCE_ID = "team360_sales_diagnosis"
DEFAULT_AUTOMATION_PACKAGE_ID = "pkg_sales_diagnosis"
DEFAULT_KNOWLEDGE_SCOPE_ID = "ks_team360_sales_diagnosis"

RETRIEVAL_MODES = {"none", "rag", "graphrag", "hybrid"}
CLASSIFICATIONS = {
    "standard_package",
    "operational_automation",
    "consulting_required",
    "not_recommended",
}
AUTOMATION_MODES = {"read_only", "assisted", "approval_required", "execution", "blocked"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"


def to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return value
    raise TypeError(f"Cannot convert {type(value)!r} to dict")


@dataclass
# @lat: [[knowledge-rag-graphrag#Knowledge RAG GraphRAG#Phase 1 Model]]
class KnowledgeScope:
    id: str
    name: str
    retrieval_mode: str = "rag"
    workspace_id: str | None = None
    assistant_instance_id: str | None = None
    automation_package_id: str | None = None
    package_worker_id: str | None = None
    graph_enabled: bool = False
    entity_extraction_status: str = "not_started"
    relation_extraction_status: str = "not_started"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeDocument:
    id: str
    knowledge_scope_id: str
    title: str
    source_path: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeChunk:
    id: str
    knowledge_scope_id: str
    document_id: str
    title: str
    content: str
    ordinal: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
# @lat: [[automation-diagnosis#Automation Diagnosis#Intake Fields]]
class DiagnosisAnswer:
    step_id: str
    selected: list[str] = field(default_factory=list)
    free_text: str = ""
    normalized_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosisSession:
    id: str
    organization_id: str
    workspace_id: str
    assistant_instance_id: str
    automation_package_id: str
    knowledge_scope_id: str
    source_url: str = ""
    site_channel: str = ""
    lead_owner: str = ""
    locale: str = "es"
    market: str = ""
    visitor: dict[str, Any] = field(default_factory=dict)
    package_worker_ids: list[str] = field(default_factory=list)
    cost_attribution: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    correlation_id: str = field(default_factory=lambda: new_id("corr"))
    answers: dict[str, DiagnosisAnswer] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    contact: dict[str, Any] | None = None
    created_at_utc: str = field(default_factory=utc_now_iso)
    updated_at_utc: str = field(default_factory=utc_now_iso)


@dataclass
class RetrievedContext:
    knowledge_scope_id: str
    retrieval_mode: str
    query: str
    chunks: list[dict[str, Any]]


@dataclass
class AIInterpretation:
    provider: str
    model: str
    summary: str
    signals: dict[str, Any]
    risks: list[str]
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreResult:
    score_total: int
    score_breakdown: dict[str, int]
    rule_hits: list[str]
    risk_flags: list[str]


@dataclass
class ClassificationResult:
    classification: str
    automation_mode: str
    recommended_package_type: str
    suggested_worker_definitions: list[str]
    required_package_worker_config: dict[str, Any]
    required_credential_refs: list[dict[str, Any]]
    required_knowledge_scope: dict[str, Any]
    risk_flags: list[str]
    blocked_actions: list[str]
    requires_human_approval: bool


@dataclass
class DiagnosisEvent:
    event_name: str
    organization_id: str
    workspace_id: str
    assistant_instance_id: str
    automation_package_id: str
    session_id: str
    correlation_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    knowledge_scope_id: str | None = None
    site_channel: str = ""
    lead_owner: str = ""
    locale: str = ""
    timestamp_utc: str = field(default_factory=utc_now_iso)
