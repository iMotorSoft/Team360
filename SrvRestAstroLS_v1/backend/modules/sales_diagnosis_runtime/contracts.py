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
class SemanticMemory:
    business_context: str = ""
    current_process: str = ""
    channels: list[str] = field(default_factory=list)
    main_problem: str = ""
    desired_outcome: str = ""
    systems_and_data_sources: list[str] = field(default_factory=list)
    known_rules: list[str] = field(default_factory=list)
    human_approval: str = ""
    exceptions: list[str] = field(default_factory=list)
    volume: str = ""
    constraints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    confirmed_facts: list[str] = field(default_factory=list)
    inferred_facts: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    automation_hypotheses: list[str] = field(default_factory=list)
    diagnosis_status: str = "gathering"  # gathering | sufficient | requested | completed


@dataclass
class StructuredDiagnosis:
    feasibility: str = "needs_validation"
    automation_mode: str = "not_recommended"
    confidence: str = "low"
    summary: str | None = None
    channels: list[str] = field(default_factory=list)
    systems: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    entity_sources: dict[str, str] = field(default_factory=dict)
    human_approval: str = "unknown"
    automatable_steps: list[str] = field(default_factory=list)
    human_steps: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    validation_points: list[str] = field(default_factory=list)
    next_step: str = ""
    availability: str = "requires_validation"
    version: str = "v1"


DIAGNOSIS_VERSION = "v1"


@dataclass
class CanonicalQuestion:
    intent: str
    question_text: str
    turn: int = 0
    answered: bool = False
    answer_evidence: str = ""


@dataclass
class TurnDecision:
    action: str = "reflect_and_ask"  # gather | reflect_and_ask | diagnose
    assistant_message: str = ""
    updated_case_summary: str = ""
    confirmed_facts: list[str] = field(default_factory=list)
    inferred_facts: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    missing_critical_information: list[str] = field(default_factory=list)
    next_question: str = ""
    next_question_intent: str = ""
    diagnosis: str = ""
    readiness_reason: str = ""
    retrieval_query: str = ""


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
    semantic_memory: dict[str, Any] = field(default_factory=dict)
    asked_questions: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Input / Output
# ---------------------------------------------------------------------------


SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"es", "en", "he"})
DEFAULT_LANGUAGE: str = "es"
LANGUAGE_UNDETERMINED: str = "und"


def _is_supported_language(code: str) -> bool:
    return code in SUPPORTED_LANGUAGES


def _normalize_language(code: str | None) -> str:
    if not code:
        return DEFAULT_LANGUAGE
    c = code.strip().lower()[:2]
    return c if _is_supported_language(c) else DEFAULT_LANGUAGE


@dataclass
class AssistantTurnInput:
    session_id: str
    assistant_instance_code: str
    package_code: str
    knowledge_scope_code: str
    user_message: str
    channel: str = "web"
    metadata: dict[str, Any] = field(default_factory=dict)
    locale: str = DEFAULT_LANGUAGE
    knowledge_scope_id: str | None = None


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
    turn_decision: dict[str, Any] | None = None
    language: dict[str, Any] | None = None
    diagnosis: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SALES_DIAGNOSIS_INSTANCE_CODE = "team360_sales_diagnosis"
SALES_DIAGNOSIS_PACKAGE_CODE = "pkg_sales_diagnosis"
SALES_DIAGNOSIS_KNOWLEDGE_SCOPE_CODE = "ks_team360_sales_diagnosis"
SALES_DIAGNOSIS_ORGANIZATION_CODE = "team360_live"
SALES_DIAGNOSIS_WORKSPACE_CODE = "team360_public_site"


@dataclass(frozen=True)
class KnowledgeScopeContext:
    """Multi-tenant context for resolving a knowledge scope code to its UUID.

    This is the canonical contract for scope resolution: PostgreSQL resolves the
    UUID from these four codes; Milvus filters by the resolved UUID only.

    Archives:
        organization_code is stored in core_workspaces.metadata_jsonb until a
        dedicated organizations table exists. See migration 005 seed.
    """

    organization_code: str
    workspace_code: str
    package_code: str
    knowledge_scope_code: str

SAFE_ACK_TEXTS: dict[str, str] = {
    "es": (
        "Recibí la información, pero no pude procesarla completamente "
        "en este momento. Podés intentarlo nuevamente sin perder la conversación."
    ),
    "en": (
        "I received the information, but I couldn't fully process it "
        "right now. You can try again without losing the conversation."
    ),
    "he": (
        "קיבלתי את המידע, אך לא הצלחתי לעבד אותו במלואו "
        "ברגע זה. תוכל לנסות שוב מבלי לאבד את השיחה."
    ),
}

SAFE_ACK_TEXT = SAFE_ACK_TEXTS["es"]


def safe_ack_for_language(lang: str | None = None) -> str:
    code = _normalize_language(lang)
    return SAFE_ACK_TEXTS.get(code, SAFE_ACK_TEXT)

PLANNED_EXTENSIONS = frozenset({
    "step_to_action",
    "lead_capture",
    "diagnostic_code",
    "whatsapp_handoff",
})

FORBIDDEN_TERMS = frozenset({
    "plazo",
    "plazos",
    "sla",
    "cobertura",
    "garantía",
    "garantia",
})
