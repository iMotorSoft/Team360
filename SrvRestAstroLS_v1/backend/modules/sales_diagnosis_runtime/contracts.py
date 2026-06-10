from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------------------
# Primitive contracts
# ---------------------------------------------------------------------------


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    knowledge_scope_id: str
    source_uri: str
    title: str | None = None
    node_path: str | None = None
    score: float = 0.0
    content_preview: str = ""
    content: str = ""


@dataclass
class GuardrailResult:
    passed: bool = True
    forbidden_claims: list[str] = field(default_factory=list)
    planned_extension_misrepresented: bool = False
    pricing_sla_hallucination: bool = False
    max_questions_exceeded: bool = False
    empty_response: bool = False
    fallback_applied: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class ProgressiveEvent:
    event_type: str
    elapsed_ms: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    safe_to_show: bool = True


@dataclass
class RuntimeMetrics:
    retrieval_latency_ms: int | None = None
    llm_latency_ms: int | None = None
    total_latency_ms: int | None = None
    time_to_first_ack_ms: int | None = None
    model: str | None = None
    token_usage: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Conversation state
# ---------------------------------------------------------------------------


@dataclass
class ConversationState:
    session_id: str
    assistant_instance_code: str
    package_code: str
    knowledge_scope_code: str
    slots: dict[str, Any] = field(default_factory=dict)
    history_summary: str | None = None
    turn_count: int = 0
    risk_flags: list[str] = field(default_factory=list)
    last_sources: list[RetrievedChunk] = field(default_factory=list)
    pending_questions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Input / Output
# ---------------------------------------------------------------------------


@dataclass
class AssistantTurnInput:
    session_id: str
    assistant_instance_code: str
    package_code: str
    knowledge_scope_code: str
    user_message: str
    channel: str = "web"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantTurnOutput:
    response_text: str
    response_type: str = "ack"
    asked_questions: list[str] = field(default_factory=list)
    slots_updated: dict[str, Any] = field(default_factory=dict)
    retrieved_sources: list[RetrievedChunk] = field(default_factory=list)
    guardrail_result: GuardrailResult = field(default_factory=GuardrailResult)
    events: list[ProgressiveEvent] = field(default_factory=list)
    metrics: RuntimeMetrics = field(default_factory=RuntimeMetrics)
    next_state: ConversationState | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SALES_DIAGNOSIS_INSTANCE_CODE = "team360_sales_diagnosis"
SALES_DIAGNOSIS_PACKAGE_CODE = "pkg_sales_diagnosis"
SALES_DIAGNOSIS_KNOWLEDGE_SCOPE_CODE = "ks_team360_sales_diagnosis"

SAFE_ACK_TEXT = (
    "Recibí tu consulta. Estoy revisando el contexto disponible "
    "para orientarte sin prometer capacidades no confirmadas."
)

PLANNED_EXTENSIONS = frozenset({
    "step_to_action",
    "lead_capture",
    "diagnostic_code",
    "whatsapp_handoff",
})

FORBIDDEN_TERMS = frozenset({
    "precio",
    "precios",
    "plazo",
    "plazos",
    "sla",
    "cobertura",
    "garantía",
    "garantia",
})
