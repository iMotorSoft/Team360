"""Internal/dev HTTP endpoint for Sales Diagnosis Assistant Runtime.

This is a development-only endpoint. It uses fake providers by default:
fake retrieval (no Milvus), fake LLM (no OpenAI/LiteLLM), in-memory state.
Production wiring (Postgres state, real Milvus, real LLM) is NOT active here.

Endpoint: POST /api/dev/sales-diagnosis-runtime/turn

Request metadata flags:
- ``dev_test_unsafe_llm`` (bool): if true, uses a FakeLLMProvider that returns
  unsafe text to exercise guardrail policy. Dev-only, not for prod.
"""

from __future__ import annotations

from dataclasses import asdict

from litestar import post
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_400_BAD_REQUEST

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    ConversationState,
    GuardrailPolicy,
    PromptPolicy,
    RetrievedChunk,
)
from modules.sales_diagnosis_runtime.errors import (
    InvalidAssistantRuntimeInputError,
    UnsafeResponseError,
)
from modules.sales_diagnosis_runtime.providers import (
    InMemoryStateRepository,
    LLMProvider,
    RetrievalProvider,
)
from modules.sales_diagnosis_runtime.state_repository import (
    InMemoryConversationStateRepository,
)

from .sales_diagnosis_runtime_schemas import DevTurnRequest, DevTurnResponse


# ---------------------------------------------------------------------------
# Prohibited identifier patterns
# ---------------------------------------------------------------------------

_PROHIBITED_CODES: frozenset[str] = frozenset({
    "vera_team360_sales_diagnosis",
    "pkg_vera_sales_diagnosis",
    "ks_vera_team360_sales_diagnosis",
    "svc_vera_sales_diagnosis",
})

# ---------------------------------------------------------------------------
# Fake providers for dev endpoint
# ---------------------------------------------------------------------------

_DEV_CHUNKS = [
    RetrievedChunk(
        chunk_id="dev_doc_1",
        document_id="dev_doc_1",
        knowledge_scope_id="ks_team360_sales_diagnosis",
        source_uri="/knowledge/dev/automation.md",
        title="Procesos automatizables",
        node_path="/ventas/automatizacion",
        score=0.92,
        content_preview="Los procesos de venta repetitivos son candidatos a automatizacion.",
        content="Los procesos de venta repetitivos, como la calificacion de leads "
        "y el envio de cotizaciones, son candidatos ideales para automatizacion.",
    ),
    RetrievedChunk(
        chunk_id="dev_doc_2",
        document_id="dev_doc_2",
        knowledge_scope_id="ks_team360_sales_diagnosis",
        source_uri="/knowledge/dev/crm.md",
        title="Integracion CRM",
        node_path="/ventas/crm",
        score=0.85,
        content_preview="Team360 se integra con CRM via API REST.",
        content="Team360 se integra con sistemas CRM externos mediante API REST "
        "estandar para sincronizar oportunidades y contactos.",
    ),
]


class _DevFakeRetrievalProvider:
    """Fake retrieval that returns controlled chunks, no Milvus."""

    def retrieve(self, input: AssistantTurnInput, state: ConversationState, top_k: int = 5, top_n: int = 20) -> list[RetrievedChunk]:
        return list(_DEV_CHUNKS)


class _DevFakeLLMProvider:
    """Fake LLM that returns safe ack text, no OpenAI/LiteLLM."""

    def generate(self, input: AssistantTurnInput, state: ConversationState, context: list[RetrievedChunk]) -> str:
        from modules.sales_diagnosis_runtime.contracts import SAFE_ACK_TEXT
        return SAFE_ACK_TEXT


_UNSAFE_RESPONSE = (
    "Tengo listo el lead_capture para empezar a capturar leads automaticamente "
    "y el WhatsApp handoff con SLA de 2 minutos."
)


class _DevUnsafeFakeLLMProvider:
    """Fake LLM that returns unsafe text to trigger guardrail rejection."""

    def generate(self, input: AssistantTurnInput, state: ConversationState, context: list[RetrievedChunk]) -> str:
        return _UNSAFE_RESPONSE


# ---------------------------------------------------------------------------
# Runtime factory
# ---------------------------------------------------------------------------

_SHARED_STATE_REPO = InMemoryConversationStateRepository()


def _build_dev_runtime(metadata: dict) -> AssistantConversationRuntime:
    retrieval: RetrievalProvider = _DevFakeRetrievalProvider()
    if metadata.get("dev_test_unsafe_llm"):
        llm: LLMProvider = _DevUnsafeFakeLLMProvider()
    else:
        llm = _DevFakeLLMProvider()
    return AssistantConversationRuntime(
        retrieval_provider=retrieval,
        llm_provider=llm,
        state_repository=_SHARED_STATE_REPO,
        prompt_policy=PromptPolicy(),
        guardrail_policy=GuardrailPolicy(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_codes(data: DevTurnRequest) -> None:
    for field_name in ("assistant_instance_code", "package_code", "knowledge_scope_code"):
        value = getattr(data, field_name, "")
        if value in _PROHIBITED_CODES:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Prohibited {field_name}: {value!r}. Use standard team360 codes.",
            )


def _chunk_to_dict(chunk: RetrievedChunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "knowledge_scope_id": chunk.knowledge_scope_id,
        "source_uri": chunk.source_uri,
        "title": chunk.title,
        "node_path": chunk.node_path,
        "score": chunk.score,
        "content_preview": chunk.content_preview,
    }


def _event_to_dict(event) -> dict:
    return {
        "event_type": event.event_type,
        "elapsed_ms": event.elapsed_ms,
        "payload": event.payload,
        "safe_to_show": event.safe_to_show,
    }


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@post("/api/dev/sales-diagnosis-runtime/turn")
async def dev_sales_diagnosis_turn(data: DevTurnRequest) -> dict:
    _validate_codes(data)

    runtime = _build_dev_runtime(data.metadata)

    input_ = AssistantTurnInput(
        session_id=data.session_id,
        assistant_instance_code=data.assistant_instance_code,
        package_code=data.package_code,
        knowledge_scope_code=data.knowledge_scope_code,
        user_message=data.message,
        channel=data.metadata.get("channel", "dev"),
        metadata=data.metadata,
    )

    try:
        output = runtime.handle_turn(input_)
    except UnsafeResponseError as exc:
        return DevTurnResponse(
            session_id=data.session_id,
            response_text=str(exc),
            response_type="unsafe_blocked",
            fallback_applied=False,
            guardrail_flags=["unsafe_response_blocked"],
            turn_count=0,
            runtime_mode="dev_fake",
        ).model_dump()
    except InvalidAssistantRuntimeInputError as exc:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(exc))

    guardrail_flags: list[str] = []
    if output.guardrail_result.fallback_applied:
        guardrail_flags.append("fallback_applied")
    if output.guardrail_result.max_questions_exceeded:
        guardrail_flags.append("max_questions_exceeded")
    if output.guardrail_result.pricing_sla_hallucination:
        guardrail_flags.append("pricing_sla_hallucination")

    turn_count = output.next_state.turn_count if output.next_state else 0

    return DevTurnResponse(
        session_id=data.session_id,
        response_text=output.response_text,
        response_type=output.response_type,
        fallback_applied=output.guardrail_result.fallback_applied,
        guardrail_flags=guardrail_flags,
        retrieved_sources=[_chunk_to_dict(c) for c in output.retrieved_sources],
        turn_count=turn_count,
        events=[_event_to_dict(e) for e in output.events],
        runtime_mode="dev_fake",
    ).model_dump()
