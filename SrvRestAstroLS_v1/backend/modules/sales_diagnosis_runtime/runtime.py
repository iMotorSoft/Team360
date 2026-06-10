from __future__ import annotations

from typing import Any

from modules.sales_diagnosis_runtime.contracts import (
    SAFE_ACK_TEXT,
    AssistantTurnInput,
    AssistantTurnOutput,
    ConversationState,
    ProgressiveEvent,
    RuntimeMetrics,
)
from modules.sales_diagnosis_runtime.errors import (
    GuardrailViolationError,
    InvalidAssistantRuntimeInputError,
    LLMUnavailableError,
    RetrievalUnavailableError,
    UnsafeResponseError,
)
from modules.sales_diagnosis_runtime.policies import GuardrailPolicy, PromptPolicy
from modules.sales_diagnosis_runtime.providers import (
    AuditTrail,
    LLMProvider,
    MetricsRecorder,
    NullAuditTrail,
    NullLLMProvider,
    NullMetricsRecorder,
    NullRetrievalProvider,
    RetrievalProvider,
    StateRepository,
)


class AssistantConversationRuntime:
    """Skeleton orchestrator for the sales diagnosis assistant.

    This is an internal runtime skeleton. It does not expose HTTP endpoints,
    does not call real LLM or Milvus, and does not implement SSE.

    Architecture invariants (from Fase 1.7e):
    - PostgreSQL 18 is source of truth
    - Milvus 2.6 is derived vector runtime for conversation
    - gpt-5-nano low is first intelligent response
    - Template safe ack does not replace LLM
    - Guardrails are mandatory before exposing responses
    - Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff
      are NOT available
    """

    def __init__(
        self,
        retrieval_provider: RetrievalProvider | None = None,
        llm_provider: LLMProvider | None = None,
        state_repository: StateRepository | None = None,
        prompt_policy: PromptPolicy | None = None,
        guardrail_policy: GuardrailPolicy | None = None,
        metrics_recorder: MetricsRecorder | None = None,
        audit_trail: AuditTrail | None = None,
    ) -> None:
        self._retrieval = retrieval_provider or NullRetrievalProvider()
        self._llm = llm_provider or NullLLMProvider()
        self._state_repo = state_repository
        self._prompt_policy = prompt_policy or PromptPolicy()
        self._guardrail_policy = guardrail_policy or GuardrailPolicy()
        self._metrics = metrics_recorder or NullMetricsRecorder()
        self._audit = audit_trail or NullAuditTrail()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_turn(self, input: AssistantTurnInput) -> AssistantTurnOutput:
        self._validate_input(input)

        events: list[ProgressiveEvent] = []
        metrics = RuntimeMetrics()

        # Emit received event
        events.append(ProgressiveEvent(
            event_type="team360.status.received",
            safe_to_show=True,
        ))

        # Load or create conversation state
        state = self._load_or_create_state(input)

        # Emit safe ack (quick progress signal, no LLM)
        ack_text = self._prompt_policy.build_safe_ack(
            assistant_instance_code=input.assistant_instance_code,
            package_code=input.package_code,
        )
        events.append(ProgressiveEvent(
            event_type="team360.answer.quick_ack",
            payload={"text": ack_text},
            safe_to_show=True,
        ))

        # Retrieve context (NullRetrievalProvider returns empty)
        events.append(ProgressiveEvent(
            event_type="team360.status.retrieval_started",
            safe_to_show=True,
        ))
        chunks = self._retrieval.retrieve(input, state)

        # Evaluate if we have real providers or only null
        has_real_retrieval = not isinstance(self._retrieval, NullRetrievalProvider)
        has_real_llm = not isinstance(self._llm, NullLLMProvider)

        if not has_real_retrieval:
            events.append(ProgressiveEvent(
                event_type="team360.status.retrieval_skipped",
                payload={"reason": "no_provider_configured"},
                safe_to_show=True,
            ))

        if not has_real_llm:
            # Skeleton mode: return safe ack as response
            metrics.time_to_first_ack_ms = 0
            output = AssistantTurnOutput(
                response_text=ack_text,
                response_type="skeleton_ack",
                asked_questions=[],
                slots_updated={},
                retrieved_sources=[],
                guardrail_result=self._guardrail_policy.evaluate_response(ack_text),
                events=events,
                metrics=metrics,
                next_state=state,
            )
            events.append(ProgressiveEvent(
                event_type="team360.done",
                payload={"mode": "skeleton_no_llm"},
                safe_to_show=True,
            ))
            self._save_state(state)
            self._metrics.record_turn(input, output)
            self._audit.record(input, output)
            return output

        # --- Real provider path (future, not implemented yet) ---
        # This path is reached only when real LLM/retrieval providers are wired.
        events.append(ProgressiveEvent(
            event_type="team360.sources.ready",
            payload={"chunk_count": len(chunks)},
            safe_to_show=True,
        ))

        context_text = self._prompt_policy.build_turn_prompt(input, state, chunks)
        raw_response = self._llm.generate(input, state, chunks)

        guardrail_result = self._guardrail_policy.evaluate_response(
            raw_response, input, state
        )

        if not guardrail_result.passed:
            if guardrail_result.forbidden_claims or guardrail_result.planned_extension_misrepresented:
                raise UnsafeResponseError(
                    f"Response blocked by guardrails: {guardrail_result.notes}"
                )
            raw_response = self._guardrail_policy.build_fallback_response(
                reason="guardrail_violation"
            )

        events.append(ProgressiveEvent(
            event_type="team360.answer.final_ready",
            payload={"text": raw_response},
            safe_to_show=True,
        ))
        events.append(ProgressiveEvent(
            event_type="team360.guardrails.applied",
            payload={"passed": guardrail_result.passed},
            safe_to_show=True,
        ))
        events.append(ProgressiveEvent(
            event_type="team360.done",
            safe_to_show=True,
        ))

        output = AssistantTurnOutput(
            response_text=raw_response,
            response_type="final",
            asked_questions=[],
            slots_updated={},
            retrieved_sources=chunks,
            guardrail_result=guardrail_result,
            events=events,
            metrics=metrics,
            next_state=state,
        )

        self._save_state(state)
        self._metrics.record_turn(input, output)
        self._audit.record(input, output)

        return output

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_input(self, input: AssistantTurnInput) -> None:
        if not input.session_id:
            raise InvalidAssistantRuntimeInputError("session_id is required")
        if not input.assistant_instance_code:
            raise InvalidAssistantRuntimeInputError(
                "assistant_instance_code is required"
            )
        if not input.user_message or not input.user_message.strip():
            raise InvalidAssistantRuntimeInputError("user_message is required")

    def _load_or_create_state(self, input: AssistantTurnInput) -> ConversationState:
        if self._state_repo:
            existing = self._state_repo.load(input.session_id)
            if existing is not None:
                return existing
        return ConversationState(
            session_id=input.session_id,
            assistant_instance_code=input.assistant_instance_code,
            package_code=input.package_code,
            knowledge_scope_code=input.knowledge_scope_code,
        )

    def _save_state(self, state: ConversationState) -> None:
        if self._state_repo:
            self._state_repo.save(state)
