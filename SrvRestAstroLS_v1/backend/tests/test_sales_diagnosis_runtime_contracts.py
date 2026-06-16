"""Tests for sales diagnosis runtime contracts, policies, providers and runtime skeleton.

No network calls. No DB. No Milvus. No LLM.
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

import pytest

from modules.sales_diagnosis_runtime import (
    AssistantConversationRuntime,
    AssistantTurnInput,
    AssistantTurnOutput,
    ConversationState,
    GuardrailPolicy,
    GuardrailResult,
    GuardrailViolationError,
    InMemoryStateRepository,
    InvalidAssistantRuntimeInputError,
    NullLLMProvider,
    NullRetrievalProvider,
    ProgressiveEvent,
    PromptPolicy,
    RetrievedChunk,
    RuntimeMetrics,
    UnsafeResponseError,
)
from modules.sales_diagnosis_runtime.contracts import (
    FORBIDDEN_TERMS,
    PLANNED_EXTENSIONS,
    SAFE_ACK_TEXT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_input() -> AssistantTurnInput:
    return AssistantTurnInput(
        session_id=str(uuid4()),
        assistant_instance_code="team360_sales_diagnosis",
        package_code="pkg_sales_diagnosis",
        knowledge_scope_code="ks_team360_sales_diagnosis",
        user_message="Quiero automatizar mi negocio",
    )


@pytest.fixture
def runtime() -> AssistantConversationRuntime:
    return AssistantConversationRuntime()


# ---------------------------------------------------------------------------
# 1. Contracts
# ---------------------------------------------------------------------------


class TestContracts:
    def test_turn_input_requires_core_fields(self):
        with pytest.raises(InvalidAssistantRuntimeInputError, match="session_id"):
            AssistantConversationRuntime().handle_turn(
                AssistantTurnInput(
                    session_id="",
                    assistant_instance_code="test",
                    package_code="test",
                    knowledge_scope_code="test",
                    user_message="hola",
                )
            )

    def test_turn_input_requires_assistant_instance_code(self):
        with pytest.raises(
            InvalidAssistantRuntimeInputError, match="assistant_instance_code"
        ):
            AssistantConversationRuntime().handle_turn(
                AssistantTurnInput(
                    session_id="s1",
                    assistant_instance_code="",
                    package_code="test",
                    knowledge_scope_code="test",
                    user_message="hola",
                )
            )

    def test_turn_input_requires_user_message(self):
        with pytest.raises(InvalidAssistantRuntimeInputError, match="user_message"):
            AssistantConversationRuntime().handle_turn(
                AssistantTurnInput(
                    session_id="s1",
                    assistant_instance_code="test",
                    package_code="test",
                    knowledge_scope_code="test",
                    user_message="",
                )
            )

    def test_turn_output_is_dataclass(self):
        output = AssistantTurnOutput(response_text="test")
        assert asdict(output) is not None

    def test_conversation_state_defaults(self):
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
        )
        assert state.turn_count == 0
        assert state.risk_flags == []
        assert state.pending_questions == []
        assert state.last_sources == []

    def test_retrieved_chunk_serializable(self):
        chunk = RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            knowledge_scope_id="k1",
            source_uri="/doc.md",
            title="Test",
            score=0.95,
            content_preview="preview",
            content="full content",
        )
        d = asdict(chunk)
        assert d["chunk_id"] == "c1"
        assert d["score"] == 0.95

    def test_guardrail_result_defaults_passed(self):
        gr = GuardrailResult()
        assert gr.passed is True
        assert gr.forbidden_claims == []
        assert gr.notes == []

    def test_progressive_event_required_fields(self):
        ev = ProgressiveEvent(event_type="team360.done")
        assert ev.safe_to_show is True
        d = asdict(ev)
        assert d["event_type"] == "team360.done"

    def test_runtime_metrics_defaults_none(self):
        m = RuntimeMetrics()
        assert m.retrieval_latency_ms is None
        assert m.llm_latency_ms is None
        assert m.total_latency_ms is None


# ---------------------------------------------------------------------------
# 2. Runtime skeleton without providers
# ---------------------------------------------------------------------------


class TestRuntimeSkeleton:
    def test_runtime_returns_safe_fallback_without_llm_provider(
        self, runtime, sample_input
    ):
        output = runtime.handle_turn(sample_input)
        assert output.response_text == SAFE_ACK_TEXT
        assert output.response_type == "skeleton_ack"

    def test_runtime_output_contains_progressive_events(
        self, runtime, sample_input
    ):
        output = runtime.handle_turn(sample_input)
        event_types = [e.event_type for e in output.events]
        assert "team360.status.received" in event_types
        assert "team360.answer.quick_ack" in event_types
        assert "team360.done" in event_types

    def test_runtime_returns_skeleton_ack_without_llm(self, runtime, sample_input):
        output = runtime.handle_turn(sample_input)
        assert output.response_type == "skeleton_ack"

    def test_runtime_guardrail_applied_to_fallback(self, runtime, sample_input):
        output = runtime.handle_turn(sample_input)
        assert output.guardrail_result is not None
        assert isinstance(output.guardrail_result, GuardrailResult)

    def test_runtime_with_in_memory_state_repo(self, sample_input):
        repo = InMemoryStateRepository()
        rt = AssistantConversationRuntime(state_repository=repo)
        output = rt.handle_turn(sample_input)
        assert output.next_state is not None
        loaded = repo.load(sample_input.session_id)
        assert loaded is not None
        assert loaded.session_id == sample_input.session_id

    def test_runtime_does_not_activate_future_capabilities(
        self, runtime, sample_input
    ):
        output = runtime.handle_turn(sample_input)
        text_lower = output.response_text.lower()
        for cap in PLANNED_EXTENSIONS:
            label = cap.replace("_", " ")
            if label in text_lower:
                assert "disponible" not in text_lower or "no" in text_lower


# ---------------------------------------------------------------------------
# 3. Guardrail policy
# ---------------------------------------------------------------------------


class TestGuardrailPolicy:
    def test_guardrail_policy_flags_step_to_action_ready_claim(self):
        policy = GuardrailPolicy()
        assert policy.is_step_to_action_ready(
            "Podemos activar Step-to-Action para vos."
        )
        assert not policy.is_step_to_action_ready(
            "Step-to-Action no está disponible actualmente."
        )

    def test_guardrail_policy_allows_planned_extension_decline(self):
        policy = GuardrailPolicy()
        text = "Lead capture no está disponible todavía."
        result = policy.evaluate_response(text)
        assert not result.planned_extension_misrepresented

    def test_guardrail_policy_detects_forbidden_claim_without_negation(self):
        policy = GuardrailPolicy()
        text = "El SLA de respuesta es de 2 horas."
        result = policy.evaluate_response(text)
        assert not result.passed
        assert result.pricing_sla_hallucination

    def test_guardrail_policy_allows_forbidden_term_with_negation(self):
        policy = GuardrailPolicy()
        text = "No contamos con información de precios en el knowledge actual."
        result = policy.evaluate_response(text)
        assert result.passed

    def test_guardrail_policy_flags_pricing_hallucination(self):
        policy = GuardrailPolicy()
        text = "El SLA de respuesta es de 2 horas."
        result = policy.evaluate_response(text)
        assert result.pricing_sla_hallucination
        assert not result.passed

    def test_guardrail_policy_allows_pricing_decline(self):
        policy = GuardrailPolicy()
        text = "No tenemos información de precios. Consultá con nuestro equipo comercial."
        result = policy.evaluate_response(text)
        assert not result.pricing_sla_hallucination

    def test_guardrail_policy_limits_max_questions(self):
        policy = GuardrailPolicy()
        text = "¿Qué necesitas? ¿Automatizar? ¿Qué canal? ¿WhatsApp? ¿Email? ¿Web?"
        result = policy.evaluate_response(text)
        assert result.max_questions_exceeded

    def test_guardrail_policy_detects_empty_response(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response("")
        assert result.empty_response
        assert not result.passed

    def test_guardrail_build_fallback_response(self):
        policy = GuardrailPolicy()
        fallback = policy.build_fallback_response(reason="guardrail_violation")
        assert "No puedo proporcionar" in fallback

    def test_guardrail_build_generic_fallback_response(self):
        policy = GuardrailPolicy()
        fallback = policy.build_fallback_response()
        assert "error" in fallback.lower()


# ---------------------------------------------------------------------------
# 4. Prompt policy
# ---------------------------------------------------------------------------


class TestPromptPolicy:
    def test_prompt_policy_safe_ack_does_not_replace_llm(self):
        policy = PromptPolicy()
        ack = policy.build_safe_ack()
        assert ack == SAFE_ACK_TEXT
        assert "Recibí tu consulta" in ack

    def test_prompt_policy_commercial_ack(self):
        policy = PromptPolicy()
        ack = policy.build_safe_ack(domain="commercial")
        assert "automatización" in ack

    def test_prompt_policy_technical_ack(self):
        policy = PromptPolicy()
        ack = policy.build_safe_ack(domain="technical")
        assert "diagnóstico" in ack

    def test_prompt_policy_system_prompt_contains_rules(self):
        policy = PromptPolicy()
        prompt = policy.build_system_prompt()
        assert "Step-to-Action" in prompt
        assert "lead_capture" in prompt
        assert "una sola" in prompt.lower()

    def test_prompt_policy_turn_prompt_includes_user_message(self):
        policy = PromptPolicy()
        input = AssistantTurnInput(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
            user_message="Quiero automatizar ventas",
        )
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
        )
        prompt = policy.build_turn_prompt(input, state, [])
        assert "Quiero automatizar ventas" in prompt


# ---------------------------------------------------------------------------
# 5. Providers
# ---------------------------------------------------------------------------


class TestProviders:
    def test_null_retrieval_provider_returns_empty(self):
        provider = NullRetrievalProvider()
        input = AssistantTurnInput(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
            user_message="test",
        )
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
        )
        chunks = provider.retrieve(input, state)
        assert chunks == []

    def test_null_llm_provider_returns_safe_ack(self):
        provider = NullLLMProvider()
        input = AssistantTurnInput(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
            user_message="test",
        )
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
        )
        text = provider.generate(input, state, [])
        assert text == SAFE_ACK_TEXT

    def test_in_memory_state_repository_roundtrip(self):
        repo = InMemoryStateRepository()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="a1",
            package_code="p1",
            knowledge_scope_code="k1",
            turn_count=3,
        )
        repo.save(state)
        loaded = repo.load("s1")
        assert loaded is not None
        assert loaded.session_id == "s1"
        assert loaded.turn_count == 3

    def test_in_memory_state_repository_load_nonexistent(self):
        repo = InMemoryStateRepository()
        assert repo.load("nonexistent") is None


# ---------------------------------------------------------------------------
# 6. Constants and invariants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_planned_extensions_not_empty(self):
        assert len(PLANNED_EXTENSIONS) >= 4

    def test_forbidden_terms_not_empty(self):
        assert len(FORBIDDEN_TERMS) >= 5

    def test_safe_ack_text_defined(self):
        assert SAFE_ACK_TEXT
        assert "Recibí tu consulta" in SAFE_ACK_TEXT


# ---------------------------------------------------------------------------
# 7. Semantic memory and backward compatibility
# ---------------------------------------------------------------------------


class TestSemanticMemory:
    def test_new_state_initializes_semantic_memory(self):
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
        )
        assert state.semantic_memory == {}
        state.semantic_memory["diagnosis_status"] = "gathering"
        assert state.semantic_memory["diagnosis_status"] == "gathering"

    def test_old_state_without_semantic_memory_loads_safely(self):
        old_data = {
            "session_id": "s1",
            "assistant_instance_code": "team360_sales_diagnosis",
            "package_code": "pkg_sales_diagnosis",
            "knowledge_scope_code": "ks_test",
            "slots": {},
            "history_summary": None,
            "turn_count": 3,
            "risk_flags": [],
            "last_sources": [],
            "pending_questions": [],
        }
        state = ConversationState(**old_data)
        assert state.semantic_memory is not None
        assert "diagnosis_status" not in state.semantic_memory or state.semantic_memory.get("diagnosis_status") != "completed"

    def test_semantic_memory_accepts_all_fields(self):
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            semantic_memory={
                "business_context": "casa de repuestos",
                "channels": ["whatsapp"],
                "diagnosis_status": "gathering",
            },
        )
        assert state.semantic_memory["business_context"] == "casa de repuestos"
        assert "whatsapp" in state.semantic_memory["channels"]
        assert state.semantic_memory["diagnosis_status"] == "gathering"

    def test_asked_questions_starts_empty(self):
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
        )
        assert state.asked_questions == []

    def test_backward_compatible_serialization_roundtrip(self):
        from modules.sales_diagnosis_runtime.state_repository import ConversationStateSerializer
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=2,
            semantic_memory={"diagnosis_status": "gathering", "channels": ["whatsapp"]},
            asked_questions=[{"intent": "identify_volume", "question_text": "¿Cuántos mensajes?", "turn": 1}],
        )
        serialized = ConversationStateSerializer.to_dict(state)
        restored = ConversationStateSerializer.from_dict(serialized)
        assert restored.semantic_memory["diagnosis_status"] == "gathering"
        assert "whatsapp" in restored.semantic_memory.get("channels", [])
        assert len(restored.asked_questions) == 1
        assert restored.asked_questions[0]["intent"] == "identify_volume"


# ---------------------------------------------------------------------------
# 8. Question intent classification
# ---------------------------------------------------------------------------


class TestQuestionIntent:
    def test_classifies_channel_question(self):
        from modules.sales_diagnosis_runtime.runtime import _classify_question_intent
        assert _classify_question_intent("¿Por qué canal recibes los mensajes?") == "identify_channel"

    def test_classifies_volume_question(self):
        from modules.sales_diagnosis_runtime.runtime import _classify_question_intent
        assert _classify_question_intent("¿Cuántos mensajes recibes por día?") == "identify_volume"

    def test_classifies_process_question(self):
        from modules.sales_diagnosis_runtime.runtime import _classify_question_intent
        assert _classify_question_intent("¿Cómo gestionas actualmente estos mensajes?") == "clarify_current_process"

    def test_classifies_data_source_question(self):
        from modules.sales_diagnosis_runtime.runtime import _classify_question_intent
        assert _classify_question_intent("¿Dónde está la información de stock?") == "identify_data_source"

    def test_classifies_approval_question(self):
        from modules.sales_diagnosis_runtime.runtime import _classify_question_intent
        assert _classify_question_intent("¿Quién revisa los casos dudosos?") == "confirm_human_approval"

    def test_classifies_unknown_question_with_fallback(self):
        from modules.sales_diagnosis_runtime.runtime import _classify_question_intent
        result = _classify_question_intent("¿Qué opinas del clima?")
        assert result.startswith("other:")


# ---------------------------------------------------------------------------
# 9. Diagnosis request detection
# ---------------------------------------------------------------------------


class TestDiagnosisRequest:
    def test_detect_explicit_request(self):
        from modules.sales_diagnosis_runtime.runtime import DIAGNOSIS_REQUEST_PATTERNS
        assert DIAGNOSIS_REQUEST_PATTERNS.search("dame el diagnóstico")
        assert DIAGNOSIS_REQUEST_PATTERNS.search("qué me recomendás")
        assert DIAGNOSIS_REQUEST_PATTERNS.search("con esto alcanza")
        assert DIAGNOSIS_REQUEST_PATTERNS.search("decime qué hago")
        assert DIAGNOSIS_REQUEST_PATTERNS.search("dame el diagnostico")
        assert DIAGNOSIS_REQUEST_PATTERNS.search("qué me recomiendas")
        assert DIAGNOSIS_REQUEST_PATTERNS.search("ya está")

    def test_does_not_false_positive(self):
        from modules.sales_diagnosis_runtime.runtime import DIAGNOSIS_REQUEST_PATTERNS
        assert not DIAGNOSIS_REQUEST_PATTERNS.search("hola cómo estás")
        assert not DIAGNOSIS_REQUEST_PATTERNS.search("quiero saber si es viable")
