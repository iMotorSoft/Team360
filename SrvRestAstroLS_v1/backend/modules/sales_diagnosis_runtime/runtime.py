from __future__ import annotations

import json
import re
from typing import Any

from modules.sales_diagnosis_runtime.contracts import (
    DEFAULT_LANGUAGE,
    LANGUAGE_UNDETERMINED,
    SAFE_ACK_TEXT,
    SAFE_ACK_TEXTS,
    SUPPORTED_LANGUAGES,
    _normalize_language,
    safe_ack_for_language,
    AssistantTurnInput,
    AssistantTurnOutput,
    ConversationState,
    ProgressiveEvent,
    RetrievedChunk,
    RuntimeMetrics,
)
from modules.sales_diagnosis_runtime.errors import (
    InvalidAssistantRuntimeInputError,
    SalesDiagnosisRuntimeError,
    UnsafeResponseError,
)
from modules.sales_diagnosis_runtime.canonical_patterns import (
    GENERAL_OUTCOME_PATTERNS,
    GENERAL_PROBLEM_PATTERNS,
    extract_approval,
    extract_current_channels,
    extract_current_systems,
    extract_entities,
    extract_entity_sources,
    extract_volume,
    is_business_context,
    is_correction,
)
from modules.sales_diagnosis_runtime.intent_classifier import (
    CLASSIFIER_CONFIDENCE_MODERATE,
    CLASSIFIER_CONFIDENCE_STRONG,
    HIGH_CONFIDENCE_RULES,
    IntentClassification,
    IntentClassifier,
    IntentScope,
    IntentSource,
    IntentStateSummary,
    IntentType,
    match_high_confidence,
)
from modules.sales_diagnosis_runtime.policies import GuardrailPolicy, PromptPolicy
from modules.sales_diagnosis_runtime.structured_diagnosis import build_structured_diagnosis
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


DIAGNOSIS_REQUEST_PATTERNS = re.compile(
    r"\b(dame\s*(el\s*|un\s*)?diagn[oó]stico"
    r"|dame\s*(el\s*)?informe"
    r"|dame\s*((la|una)\s*)?conclusi[oó]n"
    r"|qu[eé]\s*conclusi[oó]n\s*(ten[eé]s|sac[aá]s)"
    r"|qu[eé]\s*me\s*d[aá]s\s*como\s*conclusi[oó]n"
    r"|res[uú]m[íi]me|resum[íi]"
    r"|mostrame\s*(el\s*)?resultado"
    r"|ya\s*(con\s*esto|con\s*lo\s*que\s*hay)\s*qu[eé]\s*(me\s*)?dec[íi]s"
    r"|qu[eé]\s*(me\s*)?(recomiend[aeá]s?|recomiend[aeá]n|recomend[áa]s)"
    r"|con\s*esto\s*(alcanza|dame|quiero|empecemos)"
    r"|decime\s*qu[eé]\s*(hago|har[ií]as)"
    r"|qu[eé]\s*automatizar[ií]as|ya\s*est[áa]"
    r"|dame\s*una\s*orientaci[oó]n(\s*inicial)?"
    r"|dame\s*una\s*evaluaci[oó]n"
    r"|orient[aeá]me"
    r"|no\s*quiero\s*seguir\s*respondiendo"
    r"|ya\s*pod[eé]s\s*decirme\s*qu[eé]\s*conviene\s*hacer\s*primero"
    r"|evaluaci[oó]n\s*inicial"
    r"|orientaci[oó]n\s*inicial)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Canonical multilingual extraction is now in canonical_patterns.py
# ---------------------------------------------------------------------------


MANAGEMENT_SYSTEM_OPTIONS: dict[str, str] = {
    "whatsapp_business": "WhatsApp Business",
    "crm": "CRM / Sistema de gestión",
    "spreadsheet": "Planilla / Excel",
    "custom_system": "Sistema propio",
    "none": "No se gestiona centralizadamente",
}

MANAGEMENT_SYSTEM_OPTIONS_EMAIL: dict[str, str] = {
    "email_inbox": "Solo en la bandeja de email",
    "email_folders": "Carpetas o etiquetas del correo",
    "spreadsheet": "Planilla / Excel",
    "crm": "CRM o mesa de ayuda",
    "custom_system": "Sistema propio",
    "none": "No hay un seguimiento definido",
}

MANAGEMENT_SYSTEM_OPTIONS_WHATSAPP: dict[str, str] = {
    "whatsapp_business": "Solo en WhatsApp Business",
    "crm": "CRM o sistema de gestión",
    "spreadsheet": "Planilla / Excel",
    "custom_system": "Sistema propio",
    "none": "No hay un seguimiento definido",
}

# Combined reverse map: canonical key -> display label (for dedup)
_MANAGEMENT_KEY_TO_LABEL: dict[str, str] = {}
for _d in [MANAGEMENT_SYSTEM_OPTIONS, MANAGEMENT_SYSTEM_OPTIONS_EMAIL, MANAGEMENT_SYSTEM_OPTIONS_WHATSAPP]:
    _MANAGEMENT_KEY_TO_LABEL.update(_d)

AUTOMATION_GOALS: dict[str, str] = {
    "answer_faq": "Responder consultas frecuentes",
    "classify": "Clasificar consultas",
    "schedule": "Agendar turnos",
    "remind": "Enviar recordatorios",
    "escalate": "Derivar casos a una persona",
}

PRODUCT_CATALOG: list[dict[str, Any]] = [
    {
        "code": "pack_flow_whatsapp",
        "name": "T360 Pack Flow — Gestión de WhatsApp",
        "required_channels": ["whatsapp"],
        "match_goals": [],
        "status": "feasible",
        "summary": "Ordená la recepción, clasificación y respuesta de consultas de WhatsApp.",
        "reasons": ["Automatiza la recepción de mensajes", "Centraliza las consultas en un solo flujo"],
        "limitations": ["WhatsApp Business API requiere configuración previa"],
        "next_step": "Revisar acceso a WhatsApp Business API y definir reglas de derivación.",
    },
    {
        "code": "pack_faq_automation",
        "name": "T360 Pack — Automatización de consultas frecuentes",
        "required_channels": [],
        "match_goals": ["answer_faq"],
        "status": "feasible",
        "summary": "Respondé automáticamente preguntas recurrentes sin intervención manual.",
        "reasons": ["Reduce el tiempo de respuesta en consultas repetitivas"],
        "limitations": ["Requiere base de conocimiento actualizada"],
        "next_step": "Identificar las preguntas más frecuentes y preparar las respuestas base.",
    },
]


class AssistantConversationRuntime:
    def __init__(
        self,
        retrieval_provider: RetrievalProvider | None = None,
        llm_provider: LLMProvider | None = None,
        state_repository: StateRepository | None = None,
        prompt_policy: PromptPolicy | None = None,
        guardrail_policy: GuardrailPolicy | None = None,
        metrics_recorder: MetricsRecorder | None = None,
        audit_trail: AuditTrail | None = None,
        intent_classifier: IntentClassifier | None = None,
    ) -> None:
        self._retrieval = retrieval_provider or NullRetrievalProvider()
        self._llm = llm_provider or NullLLMProvider()
        self._state_repo = state_repository
        self._prompt_policy = prompt_policy or PromptPolicy()
        self._guardrail_policy = guardrail_policy or GuardrailPolicy()
        self._metrics = metrics_recorder or NullMetricsRecorder()
        self._audit = audit_trail or NullAuditTrail()
        self._intent_classifier = intent_classifier

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_turn(self, input: AssistantTurnInput) -> AssistantTurnOutput:
        self._validate_input(input)

        events: list[ProgressiveEvent] = []
        metrics = RuntimeMetrics()

        events.append(ProgressiveEvent(event_type="team360.status.received", safe_to_show=True))

        # 1. Load or create conversation state
        state = self._load_or_create_state(input)

        events.append(ProgressiveEvent(
            event_type="team360.answer.quick_ack",
            payload={"text": self._prompt_policy.build_safe_ack()},
            safe_to_show=True,
        ))

        has_real_llm = not isinstance(self._llm, NullLLMProvider)

        # 2. Mark answered questions from user's current message
        self._mark_answered_questions(state, input)

        # 3. Update semantic memory BEFORE RAG (current message is incorporated now)
        self._update_semantic_memory(state, input)

        # 3.2 Auto-answer management system slot from extracted systems
        self._auto_answer_management_system(state)

        # 3.5 Handle interaction response (structured answer from frontend blocks)
        self._apply_interaction_response(state, input)

        # 3.6 Resolve active blocks from free-text user message
        self._resolve_block_from_text(state, input)

        # 4. Resolve contradictions
        self._resolve_contradictions(state, input)

        # 4.5 Resolve language
        lang_state = self._resolve_response_language(state, input)

        # 4.6 Classify intent
        intent = self._classify_intent(state, input)

        # 5. Decide action based on intent + coverage + safety
        should_diagnose = self._decide_turn(intent, state)

        # 5.2 Decide if proactive pause should be offered (independent of diagnosis)
        should_pause = self._should_offer_pause(state, input)
        if should_pause:
            state.semantic_memory["_runtime_pause"] = True

        # Clear runtime pause flag if not actively pausing (prevent stale signal in prompt)
        if not should_pause:
            state.semantic_memory.pop("_runtime_pause", None)

        # If user chose continue from pause, mark it
        if self._is_user_continuing(input.user_message) and state.slots.get("pause_offered"):
            state.slots["pause_consumed"] = True
            state.slots["pause_semantic_snapshot"] = {
                "channels": list(state.semantic_memory.get("channels", [])),
                "systems_and_data_sources": list(state.semantic_memory.get("systems_and_data_sources", [])),
                "entities": list(state.semantic_memory.get("entities", [])),
                "human_approval": state.semantic_memory.get("human_approval", ""),
                "volume": state.semantic_memory.get("volume", ""),
                "current_process": state.semantic_memory.get("current_process", ""),
                "main_problem": state.semantic_memory.get("main_problem", ""),
            }

        # 5.5 Build structured diagnosis (deterministic, no LLM)
        if should_diagnose:
            structured_diagnosis = build_structured_diagnosis(state.semantic_memory)
            state.semantic_memory["last_structured_diagnosis"] = structured_diagnosis
            diagnosis_built = True
        else:
            # Preserve last_structured_diagnosis so post-diagnosis turns can use it.
            structured_diagnosis = state.semantic_memory.get("last_structured_diagnosis", None)
            diagnosis_built = False

        # 6. Build retrieval query from UPDATED semantic memory
        retrieval_query = self._build_retrieval_query(input, state)
        has_real_retrieval = not isinstance(self._retrieval, NullRetrievalProvider)

        # 7. Run RAG with synthesized query
        chunks: list[RetrievedChunk] = []
        if has_real_retrieval and retrieval_query:
            events.append(ProgressiveEvent(event_type="team360.status.retrieval_started", safe_to_show=True))
            retrieval_input = self._make_retrieval_input(input, retrieval_query)
            try:
                chunks = self._retrieval.retrieve(retrieval_input, state)
            except SalesDiagnosisRuntimeError as exc:
                events.append(ProgressiveEvent(
                    event_type="team360.status.retrieval_failed",
                    payload={"error": str(exc)},
                    safe_to_show=True,
                ))

        events.append(ProgressiveEvent(
            event_type="team360.sources.ready",
            payload={"chunk_count": len(chunks)},
            safe_to_show=True,
        ))

        if not has_real_llm:
            return self._skeleton_response(input, state, events, metrics)

        # 8. Generate response
        raw_response = self._llm.generate(input, state, chunks)

        is_fallback = raw_response in set(SAFE_ACK_TEXTS.values())
        events.append(ProgressiveEvent(
            event_type="team360.llm.provider_result",
            payload={"response_is_fallback": is_fallback},
            safe_to_show=True,
        ))

        # 9. Guardrail evaluation
        guardrail_result = self._guardrail_policy.evaluate_response(raw_response, input, state)

        if not guardrail_result.passed:
            if guardrail_result.forbidden_claims or guardrail_result.planned_extension_misrepresented:
                raise UnsafeResponseError(f"Response blocked by guardrails: {guardrail_result.notes}")
            raw_response = self._guardrail_policy.build_fallback_response(reason="guardrail_violation")

        events.append(ProgressiveEvent(
            event_type="team360.answer.final_ready", payload={"text": raw_response}, safe_to_show=True,
        ))
        events.append(ProgressiveEvent(
            event_type="team360.guardrails.applied", payload={"passed": guardrail_result.passed}, safe_to_show=True,
        ))

        # 10. Track questions Vera asks
        self._track_asked_questions(state, raw_response)

        events.append(ProgressiveEvent(event_type="team360.done", safe_to_show=True))

        if should_diagnose and state.semantic_memory.get("diagnosis_status") != "completed":
            state.semantic_memory["diagnosis_status"] = "completed"
            # Activate continuation when diagnosis completes: user can explore next steps.
            mem = state.semantic_memory
            if not mem.get("_continuation_active"):
                mem["_continuation_active"] = True
                sd = mem.get("last_structured_diagnosis", {}) or {}
                mem["_continuation_topic"] = "next_steps"
                lang = (mem.get("language") or {}).get("preferred_response_language", "es")
                mem["_continuation_options"] = self._build_continuation_options(lang)

        # Resolve post-diagnosis continuation choices (e.g., "1" or "Tipo de diferencias")
        self._resolve_post_diagnosis_continuation(state, input)

        # Build interaction_block: single_choice > multi_choice > pause/choice > missing_requirements > cards
        interaction_block = self._build_single_choice_block(state)
        if interaction_block is None:
            interaction_block = self._build_multi_choice_block(state)
        if interaction_block is None:
            if should_pause:
                interaction_block = self._build_pause_block(should_pause, state)
        if interaction_block is None:
            interaction_block = self._build_next_step_choice_if_ready(should_diagnose, state)
        if interaction_block is None:
            interaction_block = self._build_missing_requirements_block(state, should_diagnose)
        if interaction_block is None:
            interaction_block = self._build_diagnosis_action_card(
                state, should_diagnose, structured_diagnosis, intent,
            )
        if interaction_block is None:
            interaction_block = self._build_product_fit_card(state, should_diagnose)

        decision_reason = intent.source.value if intent.source != IntentSource.RUNTIME_FALLBACK else self._readiness_reason(state)
        if intent.intent in (IntentType.REQUEST_DIAGNOSIS, IntentType.STOP_INTERVIEW) and should_diagnose:
            decision_reason = f"{intent.intent.value}_with_coverage"
        elif intent.intent == IntentType.REQUEST_DIAGNOSIS and not should_diagnose:
            decision_reason = f"{intent.intent.value}_missing_critical"

        model_name = getattr(self._llm, "model_name", None) or ""
        output = AssistantTurnOutput(
            response_text=raw_response,
            response_type="diagnosis" if should_diagnose else "final",
            retrieved_sources=chunks,
            guardrail_result=guardrail_result,
            events=events,
            metrics=metrics,
            next_state=state,
            turn_decision={
                "action": "diagnose" if should_diagnose else "reflect_and_ask",
                "retrieval_query": retrieval_query,
                "diagnosis_status": state.semantic_memory.get("diagnosis_status", "gathering"),
                "readiness_reason": decision_reason,
                "intent": intent.intent.value,
                "intent_scope": intent.scope.value,
                "intent_confidence": intent.confidence,
                "intent_source": intent.source.value,
                "matched_rule": intent.matched_rule,
                "classifier_called": intent.source
                    not in (IntentSource.HIGH_CONFIDENCE_RULE, IntentSource.RUNTIME_FALLBACK),
                "generation": {
                    "status": "fallback" if is_fallback else "success",
                    "model": model_name,
                    "fallback_used": is_fallback,
                    "fallback_reason": "transient_error" if is_fallback else None,
                },
                "diagnosis_built": diagnosis_built,
            },
            language={
                "initial_language": lang_state.get("initial_language", input.locale),
                "current_language": lang_state.get("current_language", input.locale),
                "preferred_response_language": lang_state.get("preferred_response_language", input.locale),
                "response_language": lang_state.get("preferred_response_language", input.locale),
                "language_confidence": lang_state.get("language_confidence", 1.0),
                "language_source": lang_state.get("language_source", "default"),
                "explicit_language_preference": lang_state.get("explicit_language_preference", False),
            },
            diagnosis=structured_diagnosis if should_diagnose else None,
            interaction_block=interaction_block,
        )

        self._save_state(state)
        self._metrics.record_turn(input, output)
        self._audit.record(input, output)

        return output

    # ------------------------------------------------------------------
    # Semantic memory (updated BEFORE RAG)
    # ------------------------------------------------------------------

    def _update_semantic_memory(self, state: ConversationState, input: AssistantTurnInput) -> None:
        mem = dict(state.semantic_memory or {})
        if not mem.get("diagnosis_status"):
            mem["diagnosis_status"] = "gathering"

        msg = input.user_message

        # Store raw messages for later pattern scanning
        messages = mem.get("_messages", [])
        messages.append(msg)
        mem["_messages"] = messages

        # Business context — first mention of business type
        if not mem.get("business_context"):
            ctx = is_business_context(msg)
            if ctx:
                mem["business_context"] = ctx

        # Channels — extracted only from current-assertion clauses
        channels = extract_current_channels(msg)
        if channels:
            existing = mem.get("channels", [])
            for c in channels:
                if c not in existing:
                    existing.append(c)
            mem["channels"] = existing

        # Systems and data sources — extracted only from current-assertion clauses
        systems = extract_current_systems(msg)
        if systems:
            existing = mem.get("systems_and_data_sources", [])
            for s in systems:
                if s not in existing:
                    existing.append(s)
            mem["systems_and_data_sources"] = existing

        # Business entities (inventory, prices, etc.)
        entities = extract_entities(msg)
        if entities:
            existing = mem.get("entities", [])
            for e in entities:
                if e not in existing:
                    existing.append(e)
            mem["entities"] = existing

        # Entity-source relationships (e.g., inventory → erp, prices → spreadsheet)
        entity_sources = extract_entity_sources(msg)
        if entity_sources:
            existing = mem.get("entity_sources", {})
            existing.update(entity_sources)
            mem["entity_sources"] = existing

        # Approval / human review — canonical
        approval = extract_approval(msg)
        if approval:
            existing = mem.get("human_approval", "")
            # Only upgrade from '' or 'not_required' to stronger
            if not existing or existing == "not_required":
                mem["human_approval"] = approval
            elif existing == "required" and approval == "conditional":
                pass  # keep required
            elif approval == "required":
                mem["human_approval"] = "required"
            elif approval == "conditional" and not existing:
                mem["human_approval"] = "conditional"

        # Volume — canonical
        volume = extract_volume(msg)
        if volume:
            mem["volume"] = volume

        # Problem and outcome — broad heuristic match (keep backward compat)
        if not mem.get("main_problem"):
            if GENERAL_PROBLEM_PATTERNS.search(msg):
                mem["main_problem"] = msg

        if not mem.get("desired_outcome"):
            if GENERAL_OUTCOME_PATTERNS.search(msg):
                mem["desired_outcome"] = msg

        process = self._update_current_process(mem.get("current_process", ""), msg)
        if process:
            mem["current_process"] = process

        # Normalize systems_and_data_sources: deduplicate canonical keys and labels
        mem["systems_and_data_sources"] = self._normalize_systems(mem.get("systems_and_data_sources", []))

        state.semantic_memory = mem

    @staticmethod
    def _normalize_systems(systems: list[str]) -> list[str]:
        """Deduplicate systems list: if a canonical key has a known display
        label, emit the label instead. If both key and label exist, keep only
        the label. Preserves order of first occurrence."""
        seen_labels: set[str] = set()
        result: list[str] = []
        for item in systems:
            label = _MANAGEMENT_KEY_TO_LABEL.get(item, item)
            if label not in seen_labels:
                seen_labels.add(label)
                result.append(label)
        return result

    @staticmethod
    def _auto_answer_management_system(state: ConversationState) -> None:
        status = state.slots.get("management_system_choice_status", "")
        if status == "answered":
            return
        mem = state.semantic_memory or {}
        systems = mem.get("systems_and_data_sources", [])
        if not systems:
            return
        SYSTEM_TO_MGMT_OPTION = {
            "crm": "crm",
            "kommo": "crm",
            "salesforce": "crm",
            "spreadsheet": "spreadsheet",
            "custom_system": "custom_system",
            "erp": "crm",
            "database": "custom_system",
        }
        for sys_name in systems:
            option = SYSTEM_TO_MGMT_OPTION.get(sys_name)
            if option:
                state.slots["management_system"] = option
                state.slots["management_system_choice_status"] = "answered"
                return

    @staticmethod
    def _resolve_block_from_text(state: ConversationState, input: AssistantTurnInput) -> None:
        msg = input.user_message.strip().lower()
        if not msg:
            return

        # Single choice resolution
        sc_status = state.slots.get("management_system_choice_status", "")
        if sc_status not in ("answered",):
            TEXT_TO_SINGLE_CHOICE = {
                "en excel": "spreadsheet",
                "planilla": "spreadsheet",
                "excel": "spreadsheet",
                "en una planilla": "spreadsheet",
                "crm": "crm",
                "en crm": "crm",
                "en salesforce": "crm",
                "salesforce": "crm",
                "en kommo": "crm",
                "kommo": "crm",
                "sistema propio": "custom_system",
                "propio": "custom_system",
                "whatsapp business": "whatsapp_business",
                "en whatsapp": "whatsapp_business",
                "no gestionamos": "none",
                "no hay seguimiento": "none",
                "ninguno": "none",
            }
            for text_pattern, option_value in TEXT_TO_SINGLE_CHOICE.items():
                if text_pattern in msg:
                    all_options = {}
                    for d in [MANAGEMENT_SYSTEM_OPTIONS, MANAGEMENT_SYSTEM_OPTIONS_EMAIL, MANAGEMENT_SYSTEM_OPTIONS_WHATSAPP]:
                        all_options.update(d)
                    label = all_options.get(option_value, option_value)
                    state.slots["management_system"] = option_value
                    state.slots["management_system_label"] = label
                    state.slots["management_system_choice_status"] = "answered"
                    mem = state.semantic_memory or {}
                    systems = mem.get("systems_and_data_sources", [])
                    if label not in systems and option_value not in systems:
                        systems.append(label)
                        mem["systems_and_data_sources"] = systems
                        state.semantic_memory = mem
                    return

            # If text doesn't match and single_choice is active, don't guess
            return

        # Multi choice resolution
        mc_status = state.slots.get("automation_goals_choice_status", "")
        if mc_status not in ("answered",):
            TEXT_TO_MULTI_CHOICE = {
                "responder": "answer_faq",
                "respuesta": "answer_faq",
                "consultar stock": "answer_faq",
                "clasificar": "classify",
                "turno": "schedule",
                "recordatorio": "remind",
                "derivar": "escalate",
                "excepción": "escalate",
                "excepciones": "escalate",
                "revisión humana": "escalate",
                "humana": "escalate",
                "todo": "*",
            }
            matched_values = []
            for text_pattern, opt_val in TEXT_TO_MULTI_CHOICE.items():
                if text_pattern in msg:
                    if opt_val == "*":
                        matched_values = list(AUTOMATION_GOALS.keys())
                        break
                    if opt_val not in matched_values:
                        matched_values.append(opt_val)
            if matched_values:
                labels = [AUTOMATION_GOALS.get(v, v) for v in matched_values]
                state.slots["automation_goals"] = matched_values
                state.slots["automation_goals_labels"] = labels
                state.slots["automation_goals_choice_status"] = "answered"
                return

    @staticmethod
    def _build_continuation_options(lang: str) -> list[dict[str, str]]:
        lang_map = {
            "es": [
                {"id": "difference_types", "topic": "difference_types",
                 "label": "Tipos de diferencias"},
                {"id": "operational_flow", "topic": "operational_flow",
                 "label": "Flujo operativo"},
            ],
            "en": [
                {"id": "difference_types", "topic": "difference_types",
                 "label": "Types of discrepancies"},
                {"id": "operational_flow", "topic": "operational_flow",
                 "label": "Operational workflow"},
            ],
            "he": [
                {"id": "difference_types", "topic": "difference_types",
                 "label": "סוגי פערים"},
                {"id": "operational_flow", "topic": "operational_flow",
                 "label": "תהליך תפעולי"},
            ],
        }
        return lang_map.get(lang, lang_map["es"])

    @staticmethod
    def _resolve_post_diagnosis_continuation(state: ConversationState, input: AssistantTurnInput) -> None:
        mem = state.semantic_memory or {}
        if not mem.get("_continuation_active"):
            return
        chosen_topic = mem.get("_continuation_topic", "")
        if chosen_topic not in ("next_steps", ""):
            return
        options = mem.get("_continuation_options", [])
        if not options:
            return
        msg = input.user_message.strip().lower()
        if not msg:
            return
        msg_clean = msg.rstrip(".,;!?").strip()
        # Multilingual prefix stripping
        for prefix in ["opción ", "opcion ", "option ", "אפשרות "]:
            if msg_clean.startswith(prefix):
                msg_clean = msg_clean[len(prefix):].strip()
                break
        # Multilingual "first option" matching
        first_keywords = {"1", "primera", "la primera", "primera opción", "primera opcion",
                          "first", "the first", "first option",
                          "ראשונה", "הראשונה", "אפשרות ראשונה"}
        second_keywords = {"2", "segunda", "la segunda", "segunda opción", "segunda opcion",
                           "second", "the second", "second option",
                           "שנייה", "השנייה", "אפשרות שנייה"}
        if msg_clean in first_keywords:
            chosen = options[0]
            mem["_continuation_topic"] = chosen["topic"]
            mem["_continuation_chosen_label"] = chosen["label"]
            del mem["_continuation_options"]
            state.semantic_memory = mem
            return
        if len(options) > 1 and msg_clean in second_keywords:
            chosen = options[1]
            mem["_continuation_topic"] = chosen["topic"]
            mem["_continuation_chosen_label"] = chosen["label"]
            del mem["_continuation_options"]
            state.semantic_memory = mem
            return
        # Match by text content against option labels
        for opt in options:
            opt_lower = opt["label"].lower()
            opt_id = opt["id"].lower()
            if opt_id in msg or any(word in msg for word in opt_lower.split() if len(word) > 3):
                mem["_continuation_topic"] = opt["topic"]
                mem["_continuation_chosen_label"] = opt["label"]
                del mem["_continuation_options"]
                state.semantic_memory = mem
                return

    @staticmethod
    def _apply_interaction_response(state: ConversationState, input: AssistantTurnInput) -> None:
        resp = (input.metadata or {}).get("interaction_response")
        if not isinstance(resp, dict):
            return
        block_type = resp.get("block_type")
        if block_type == "single_choice":
            value = resp.get("value", "")
            valid_options = set(MANAGEMENT_SYSTEM_OPTIONS) | set(MANAGEMENT_SYSTEM_OPTIONS_EMAIL) | set(MANAGEMENT_SYSTEM_OPTIONS_WHATSAPP)
            if value not in valid_options:
                return
            option_id = resp.get("option_id")
            if option_id is not None and option_id != value:
                return
            all_options = {**MANAGEMENT_SYSTEM_OPTIONS, **MANAGEMENT_SYSTEM_OPTIONS_EMAIL, **MANAGEMENT_SYSTEM_OPTIONS_WHATSAPP}
            label = all_options.get(value, value)
            state.slots["management_system"] = value
            state.slots["management_system_label"] = label
            state.slots["management_system_choice_status"] = "answered"
            mem = state.semantic_memory or {}
            systems = mem.get("systems_and_data_sources", [])
            if label not in systems and value not in systems:
                systems.append(label)
                mem["systems_and_data_sources"] = systems
                state.semantic_memory = mem
        elif block_type == "multi_choice":
            values = resp.get("values", [])
            if not isinstance(values, list) or not values:
                return
            valid = {k for k in AUTOMATION_GOALS}
            filtered = [v for v in values if v in valid]
            if not filtered:
                return
            labels = resp.get("labels", [])
            official_labels = [AUTOMATION_GOALS[v] for v in filtered]
            state.slots["automation_goals"] = filtered
            state.slots["automation_goals_labels"] = official_labels
            state.slots["automation_goals_choice_status"] = "answered"

    @staticmethod
    def _update_current_process(existing: str, msg: str) -> str:
        words = msg.split()
        if len(words) < 3:
            return ""
        # If no existing process, set from this message
        if not existing:
            return msg
        # If existing contains key process words and msg adds new steps,
        # merge them into a coherent description.
        existing_lower = existing.lower()
        msg_lower = msg.lower()
        process_keywords = {"reporte", "reportes", "excel", "erp", "cruce", "cruza",
                            "manual", "descarga", "archivo", "sistema", "planilla",
                            "datos", "carga", "valida", "armado", "formato",
                            "tiktok", "venta", "ventas", "estado", "responsable",
                            "producto", "fecha", "nombre", "columna", "kanban"}
        # Msg is about a specific process step — append if not already covered
        if any(k in msg_lower for k in process_keywords):
            # Check if this is substantially new info
            overlap = sum(1 for w in words if w.lower() in existing_lower)
            if overlap <= len(words) * 0.5:
                return f"{existing} Luego se {msg_lower.rstrip('.')}."
        return existing

    # ------------------------------------------------------------------
    # Contradiction resolution
    # ------------------------------------------------------------------

    def _resolve_contradictions(self, state: ConversationState, input: AssistantTurnInput) -> None:
        mem = state.semantic_memory or {}
        msg = input.user_message
        corrected = False

        if not is_correction(msg):
            return

        # --- Entity-source corrections (partial replacement) ---
        new_entity_sources = extract_entity_sources(msg)
        existing_sources = mem.get("entity_sources", {})
        if new_entity_sources:
            # Only update entity-source pairs found in the correction message
            for entity, new_source in new_entity_sources.items():
                existing_sources[entity] = new_source
            mem["entity_sources"] = existing_sources
            corrected = True

            # Also rebuild systems_and_data_sources from updated entity_sources
            # to keep both in sync
            rebuilt_systems = list(dict.fromkeys(existing_sources.values()))
            if rebuilt_systems:
                mem["systems_and_data_sources"] = rebuilt_systems

        # Extract systems mentioned (for systems not tied to entities)
        new_systems = extract_current_systems(msg)
        if new_systems and not new_entity_sources:
            # Only replace if no entity-source mapping was found
            # (entity_sources is more precise)
            mem["systems_and_data_sources"] = new_systems
            corrected = True
        elif new_systems and new_entity_sources:
            # Add new systems not already covered by entity_sources
            existing_sys = set(mem.get("systems_and_data_sources", []))
            covered = set(existing_sources.values())
            for sys in new_systems:
                if sys not in covered and sys not in existing_sys:
                    existing_sys.add(sys)
            if existing_sys:
                mem["systems_and_data_sources"] = list(existing_sys)

        # Volume correction — extract new volume
        new_volume = extract_volume(msg)
        if new_volume:
            mem["volume"] = new_volume
            corrected = True

        # Log the correction
        contradictions = mem.get("contradictions", [])
        contradictions.append(f"User corrected in turn {state.turn_count}: {input.user_message[:120]}")
        mem["contradictions"] = contradictions
        corrected = True

        if corrected:
            state.semantic_memory = mem

    # ------------------------------------------------------------------
    # Language detection and resolution
    # ------------------------------------------------------------------

    def _detect_message_language(self, text: str) -> dict:
        hebrew_ratio = _hebrew_char_ratio(text)
        latin_ratio = _latin_char_ratio(text)

        if hebrew_ratio > 0.4:
            code = "he"
            confidence = min(0.99, 0.7 + hebrew_ratio)
        elif latin_ratio > 0.4 and hebrew_ratio < 0.15:
            confidence = 0.3
            code = "und"
            english_words = re.findall(r"\b(the|and|for|are|but|not|you|all|can|had|her|was|one|our|out|has|have|from|this|that|with|will|your|they|them|what|when|make|like|just|over|take|know|need|want)\b", text, re.IGNORECASE)
            spanish_words = re.findall(r"\b(el|la|los|las|que|por|del|una|las|con|para|como|está|más|pero|sus|le|o|ya|ese|son|era|vez|todo|hay|tan|tipo|vez|dar|muy|voy|ir|tener|hacer|estoy|quiero|necesito|tengo|vendo|recibo|usan|automático|automatizar|manual|reviso|hago|hacés|hacen|entonces|porque)\b", text, re.IGNORECASE)
            if len(spanish_words) > len(english_words) * 2:
                code = "es"
                confidence = 0.8
            elif len(english_words) > len(spanish_words) * 2:
                code = "en"
                confidence = 0.8
            elif len(spanish_words) > 0 or len(english_words) > 0:
                code = "mixed"
                confidence = 0.5
        else:
            code = "und"
            confidence = 0.3
        return {"code": code, "confidence": round(confidence, 2)}

    def _is_significant_message(self, text: str, current_language: str) -> bool:
        words = text.strip().split()
        if len(words) < 3:
            return False
        common_greetings = frozenset({
            "hola", "hi", "shalom", "שלום", "ok", "sí", "si", "no",
            "yes", "thanks", "gracias", "תודה", "bye", "adiós", "adios",
        })
        lower = text.lower().strip()
        return lower not in common_greetings and len(lower) > 10

    def _detect_explicit_language_switch(self, text: str) -> str | None:
        patterns = [
            (r"\b(respond[eé]me|habl[aá]me|contest[aá]me|respond[eé]|resp[oó]ndeme|segu[ií]|seguimos|sigamos|continu[aá]|continuamos)\s+(en\s+)?(espa[ñn]ol|ingl[eé]s|hebreo|english|spanish|hebrew|עברית)\b", None),
            (r"\b(can\s+we\s+continue\s+in\s+)(english|spanish|hebrew)\b", None),
            (r"\b(please\s+answer\s+in\s+)(english|spanish|hebrew)\b", None),
            (r"\b([תצ]ענה\s+לי\s+ב)(אנגלית|עברית|ספרדית)\b", None),
            (r"\b(אפשר\s+להמשיך\s+ב)(עברית|אנגלית|ספרדית)\b", None),
        ]
        lower = text.lower()
        for pattern, _ in patterns:
            m = re.search(pattern, lower)
            if m:
                last = m.group(m.lastindex or 2)
                lang_map = {
                    "español": "es", "espanol": "es", "spanish": "es", "español": "es",
                    "english": "en", "inglés": "en", "ingles": "en",
                    "hebreo": "he", "hebrew": "he", "עברית": "he",
                    "אנגלית": "en", "ספרדית": "es",
                }
                return lang_map.get(last.lower() if last else "")
        return None

    def _resolve_response_language(self, state: ConversationState, input: AssistantTurnInput) -> dict:
        mem = state.semantic_memory or {}
        lang_state = mem.get("language", {})
        msg_lang = self._detect_message_language(input.user_message)
        detected_code = msg_lang["code"]

        explicit_switch = self._detect_explicit_language_switch(input.user_message)
        if explicit_switch:
            preferred = explicit_switch
            source = "explicit_user_request"
            explicit_pref = True
            current = preferred
        else:
            explicit_pref = lang_state.get("explicit_language_preference", False)
            preferred = lang_state.get("preferred_response_language", "")
            current = lang_state.get("current_language", "")
            source = lang_state.get("language_source", "detected")

            if explicit_pref and preferred:
                current = preferred
                source = "explicit_preference"
            elif detected_code not in ("und", "mixed") and self._is_significant_message(input.user_message, current or ""):
                if not lang_state.get("initial_language") or lang_state["initial_language"] == LANGUAGE_UNDETERMINED:
                    lang_state["initial_language"] = detected_code
                current = detected_code
                if not explicit_pref:
                    preferred = detected_code
                source = "detected"

            if not current:
                current = _normalize_language(input.locale or DEFAULT_LANGUAGE)
            if not preferred:
                preferred = current
            if not lang_state.get("initial_language"):
                lang_state["initial_language"] = current

        if source == "explicit_user_request":
            lang_state["explicit_language_preference"] = True
            lang_state["language_source"] = "explicit_user_request"
        elif source == "explicit_preference":
            pass
        else:
            lang_state["explicit_language_preference"] = explicit_pref
            lang_state["language_source"] = source

        lang_state["current_language"] = current
        lang_state["preferred_response_language"] = preferred
        lang_state["last_message_language"] = msg_lang["code"]
        lang_state["language_confidence"] = msg_lang["confidence"]

        mem["language"] = lang_state
        state.semantic_memory = mem

        return lang_state

    # ------------------------------------------------------------------
    # Intent classification and TurnDecision
    # ------------------------------------------------------------------

    def _build_intent_state(self, state: ConversationState) -> IntentStateSummary:
        mem = state.semantic_memory or {}
        lang = mem.get("language", {})
        return IntentStateSummary(
            diagnosis_status=mem.get("diagnosis_status", "gathering"),
            has_process=bool(mem.get("current_process") or mem.get("main_problem")),
            has_channels=bool(mem.get("channels")),
            has_systems=bool(mem.get("systems_and_data_sources")),
            has_human_approval=bool(mem.get("human_approval")),
            has_volume=bool(mem.get("volume")),
            turn_count=state.turn_count,
            last_question_intent=_last_question_intent(state),
            current_language=lang.get("current_language", "es"),
        )

    def _classify_intent(self, state: ConversationState, input: AssistantTurnInput) -> IntentClassification:
        fast = match_high_confidence(input.user_message)
        if fast is not None:
            return fast
        if self._intent_classifier is not None:
            summary = self._build_intent_state(state)
            return self._intent_classifier.classify(input.user_message, summary)
        return IntentClassification(source=IntentSource.RUNTIME_FALLBACK)

    def _decide_turn(self, intent: IntentClassification, state: ConversationState) -> bool:
        mem = state.semantic_memory or {}
        status = mem.get("diagnosis_status", "gathering")
        if status in ("completed",):
            return False
        coverage = self._build_intent_state(state)
        has_critical = coverage.has_process and coverage.has_channels and coverage.has_systems
        is_strong = intent.confidence >= CLASSIFIER_CONFIDENCE_STRONG
        is_moderate = intent.confidence >= CLASSIFIER_CONFIDENCE_MODERATE

        if intent.intent == IntentType.REQUEST_DIAGNOSIS:
            if intent.scope == IntentScope.GLOBAL:
                if has_critical or is_strong:
                    mem["diagnosis_status"] = "sufficient"
                    state.semantic_memory = mem
                    return True
            return False

        if intent.intent == IntentType.STOP_INTERVIEW:
            if has_critical or is_strong:
                mem["diagnosis_status"] = "sufficient"
                state.semantic_memory = mem
                return True
            if is_moderate and coverage.has_process:
                mem["diagnosis_status"] = "sufficient"
                state.semantic_memory = mem
                return True
            return False

        if intent.intent == IntentType.ASK_POINT_QUESTION:
            return False

        if intent.intent == IntentType.PROVIDE_INFORMATION:
            if status == "requested" and has_critical:
                mem["diagnosis_status"] = "sufficient"
                state.semantic_memory = mem
                return True
            return False

        if intent.intent == IntentType.CORRECT_PREVIOUS_INFORMATION:
            return False

        return False

    # ------------------------------------------------------------------
    # Diagnosis readiness
    # ------------------------------------------------------------------

    def _is_ready_to_diagnose(self, state: ConversationState) -> bool:
        mem = state.semantic_memory or {}
        status = mem.get("diagnosis_status", "gathering")

        if status in ("completed", "sufficient"):
            return True

        has_process = bool(mem.get("current_process") or mem.get("main_problem"))
        has_channel = bool(mem.get("channels"))
        has_system = bool(mem.get("systems_and_data_sources"))

        if has_process and has_channel and has_system:
            mem["diagnosis_status"] = "sufficient"
            state.semantic_memory = mem
            return True

        return False

    def _should_offer_pause(self, state: ConversationState, input: AssistantTurnInput) -> bool:
        """Deterministic: should we offer a pause with next_step_choice block?

        Unlike _is_ready_to_diagnose which requires strict process+channel+system,
        this method uses a broader heuristic to decide when to proactively pause
        and offer the user a choice between preliminary diagnosis or continuing.

        Conditions:
        - turn_count >= 3
        - Has at least process or channel or system context
        - At least 2 memory dimensions are populated
        - Pause not already offered, or if offered then new info appeared
        - User didn't explicitly say continue
        - Not in diagnose mode already
        """
        mem = state.semantic_memory or {}
        status = mem.get("diagnosis_status", "gathering")

        # Already diagnosing — no need to pause
        if status in ("completed", "sufficient", "requested"):
            return False

        # Need at least a few turns
        if state.turn_count < 3:
            return False

        has_process = bool(mem.get("current_process") or mem.get("main_problem"))
        has_channel = bool(mem.get("channels"))
        has_system = bool(mem.get("systems_and_data_sources"))
        has_entity = bool(mem.get("entities"))
        has_approval = bool(mem.get("human_approval"))
        has_volume = bool(mem.get("volume"))

        # Need at least some factual context
        if not (has_process or has_channel or has_system):
            return False

        # Count populated memory dimensions (broad heuristic)
        dims = sum(1 for d in [has_process, has_channel, has_system,
                               has_entity, has_approval, has_volume])
        if dims < 2:
            return False

        # User chose to continue — allow re-offer only if substantial new info
        if state.slots.get("pause_consumed"):
            if not self._has_new_info_since_pause(state):
                return False

        # User explicitly asked to continue in this message
        if self._is_user_continuing(input.user_message):
            return False

        # Check anti-loop: if pause was already offered, don't re-offer
        # unless new info has appeared since last offer
        if state.slots.get("pause_offered") and not state.slots.get("pause_consumed"):
            return False

        # ── Exclusión mutua con multi_choice ────────────────────────────
        # Si multi_choice está pendiente (offered pero no answered),
        # no ofrecer pausa por texto — competirían bloque y texto.
        if state.slots.get("automation_goals_choice_status") == "offered":
            return False

        # Si single_choice fue respondido y multi_choice no fue ofrecido
        # ni respondido, multi_choice se emitirá como bloque esta ronda
        # (a menos que ya haya datos para diagnosticar).
        # No ofrecer pausa por texto para evitar duplicación.
        mc_status = state.slots.get("automation_goals_choice_status", "")
        if state.slots.get("management_system_choice_status") == "answered" and mc_status not in ("answered", "offered"):
            if not self._is_ready_to_diagnose(state) and mem.get("channels", []):
                return False

        return True

    @staticmethod
    def _is_user_continuing(message: str) -> bool:
        return bool(re.search(
            r"\b(segu[ií]\s*preguntando"
            r"|segu[ií]"
            r"|seguir(\s*conversando|\s*respondiendo|)"
            r"|m[aá]s\s*detalle"
            r"|afinemos|afin[eé]mos"
            r"|pregunt[aá]me\s*m[aá]s"
            r"|continu[aá]|continuemos"
            r"|dale\s*(segu[ií]|pregunt[aá]|seguir)"
            r"|ok\s*(segu[ií]|pregunt[aá]|seguir)"
            r"|s[ií]\s*(segu[ií]|pregunt[aá]|seguir)"
            r"|quiero\s*(seguir\s*respondiendo|contestar\s*m[aá]s)"
            r"|h[aá]blame\s*m[aá]s"
            r"|contame\s*m[aá]s"
            r"|decime\s*m[aá]s"
            r"|\d+\s*[,;.\-]?\s*\d*\s*preguntas?\s*m[aá]s"
            r"|unas?\s*preguntas?\s*m[aá]s"
            r"|un\s*par\s*de\s*preguntas?\s*m[aá]s"
            r"|wants?\s*(more\s*)?(details?|questions?|to\s*continue)"
            r"|keep\s*(going|asking|talking)"
            r"|ask\s*me\s*more"
            r"|continue|let\s*\'?s\s*(continue|go\s*deeper)"
            r"|tell\s*me\s*more)\b",
            message,
            re.IGNORECASE,
        ))

    @staticmethod
    def _has_new_info_since_pause(state: ConversationState) -> bool:
        """Check if new semantic info has appeared since the pause was consumed."""
        mem = state.semantic_memory or {}
        pause_snapshot = state.slots.get("pause_semantic_snapshot", {})
        if not pause_snapshot:
            return False
        for key in ("channels", "systems_and_data_sources", "entities",
                    "human_approval", "volume", "current_process", "main_problem"):
            old = pause_snapshot.get(key)
            new = mem.get(key)
            if old != new:
                return True
        return False

    @staticmethod
    def _build_next_step_choice_if_ready(
        should_diagnose: bool,
        state: ConversationState,
    ) -> dict[str, object] | None:
        if not should_diagnose:
            return None
        min_turns = 2
        if state.turn_count < min_turns:
            return None
        return {
            "type": "next_step_choice",
            "title": "¿Cómo querés seguir?",
            "description": "Ya tengo suficiente información para darte una orientación inicial.",
            "actions": [
                {
                    "id": "continue",
                    "label": "Seguir conversando",
                    "intent": "continue_conversation",
                    "style": "secondary",
                },
                {
                    "id": "show_diagnosis",
                    "label": "Ver diagnóstico",
                    "intent": "show_current_diagnosis",
                    "style": "primary",
                },
            ],
        }

    @staticmethod
    def _build_pause_block(
        should_pause: bool,
        state: ConversationState,
    ) -> dict[str, object] | None:
        if not should_pause:
            return None
        if state.turn_count < 3:
            return None
        state.slots["pause_offered"] = True
        return {
            "type": "next_step_choice",
            "title": "¿Cómo querés seguir?",
            "description": "Ya tengo suficiente información para darte una orientación inicial.",
            "actions": [
                {
                    "id": "continue",
                    "label": "Seguir conversando",
                    "intent": "continue_conversation",
                    "style": "secondary",
                },
                {
                    "id": "show_diagnosis",
                    "label": "Ver diagnóstico",
                    "intent": "show_current_diagnosis",
                    "style": "primary",
                },
            ],
        }

    @staticmethod
    def _get_management_options(channels: list[str]) -> dict[str, str]:
        if "email" in channels and "whatsapp" not in channels:
            return MANAGEMENT_SYSTEM_OPTIONS_EMAIL
        if "whatsapp" in channels and "email" not in channels:
            return MANAGEMENT_SYSTEM_OPTIONS_WHATSAPP
        return MANAGEMENT_SYSTEM_OPTIONS

    @staticmethod
    def _build_single_choice_block(
        state: ConversationState,
    ) -> dict[str, object] | None:
        status = state.slots.get("management_system_choice_status", "")
        if status == "answered":
            return None
        mem = state.semantic_memory or {}
        if state.turn_count < 2:
            return None
        channels = mem.get("channels", [])
        if not channels:
            return None
        has_systems = bool(mem.get("systems_and_data_sources"))
        if has_systems:
            return None
        if not status:
            state.slots["management_system_choice_status"] = "offered"
        options = AssistantConversationRuntime._get_management_options(channels)
        channel_label = "emails" if "email" in channels else "consultas"
        article = "los " if "email" in channels else "las "
        return {
            "type": "single_choice",
            "question": f"¿Dónde se registran y siguen hoy {article}{channel_label}?",
            "helper_text": "Elegí la opción que mejor describa tu situación actual.",
            "required": True,
            "options": [
                {"id": k, "label": v, "value": k}
                for k, v in options.items()
            ],
            "submit_action": {
                "id": "submit_management_system",
                "label": "Continuar",
                "intent": "answer_choice",
                "style": "primary",
            },
        }

    def _readiness_reason(self, state: ConversationState) -> str:
        mem = state.semantic_memory or {}
        parts = []
        if mem.get("business_context"):
            parts.append("context")
        if mem.get("channels"):
            parts.append("channel")
        if mem.get("current_process") or mem.get("main_problem"):
            parts.append("process")
        if mem.get("systems_and_data_sources"):
            parts.append("systems")
        if mem.get("human_approval"):
            parts.append("approval")
        return "+".join(parts) if parts else "gathering"

    @staticmethod
    def _build_multi_choice_block(
        state: ConversationState,
    ) -> dict[str, object] | None:
        status = state.slots.get("automation_goals_choice_status", "")
        if status == "answered":
            return None
        if state.slots.get("management_system_choice_status") not in ("answered",):
            return None
        mem = state.semantic_memory or {}
        if state.turn_count < 3:
            return None
        channels = mem.get("channels", [])
        if not channels:
            return None
        if not status:
            state.slots["automation_goals_choice_status"] = "offered"
        elif state.slots.get("multi_choice_shown"):
            return None
        state.slots["multi_choice_shown"] = True
        return {
            "type": "multi_choice",
            "question": "¿Qué querés automatizar primero?",
            "helper_text": "Podés elegir más de una opción.",
            "min_selected": 1,
            "max_selected": 3,
            "options": [
                {"id": k, "label": v, "value": k}
                for k, v in AUTOMATION_GOALS.items()
            ],
            "submit_action": {
                "id": "submit_automation_goals",
                "label": "Continuar",
                "intent": "submit_choices",
                "style": "primary",
            },
        }

    @staticmethod
    def _build_missing_requirements_block(
        state: ConversationState,
        should_diagnose: bool,
    ) -> dict[str, object] | None:
        mem = state.semantic_memory or {}
        status = mem.get("diagnosis_status", "gathering")
        if status in ("completed",):
            return None
        if should_diagnose:
            return None
        if state.slots.get("management_system_choice_status") not in ("answered",):
            return None

        reqs: list[dict[str, str]] = []

        channels = mem.get("channels", [])
        if channels:
            reqs.append({
                "id": "channel",
                "label": "Canal principal",
                "status": "confirmed",
                "required_for": "preliminary_diagnosis",
            })
        else:
            reqs.append({
                "id": "channel",
                "label": "Canal principal",
                "status": "missing",
                "required_for": "preliminary_diagnosis",
            })

        if state.slots.get("management_system"):
            reqs.append({
                "id": "management_system",
                "label": "Sistema de gestión actual",
                "status": "confirmed",
                "required_for": "full_diagnosis",
            })
        else:
            reqs.append({
                "id": "management_system",
                "label": "Sistema de gestión actual",
                "status": "missing",
                "required_for": "full_diagnosis",
            })

        has_process = bool(mem.get("current_process") or mem.get("main_problem"))
        if has_process:
            reqs.append({
                "id": "current_process",
                "label": "Proceso actual descripto",
                "status": "confirmed",
                "required_for": "preliminary_diagnosis",
            })
        else:
            reqs.append({
                "id": "current_process",
                "label": "Proceso actual",
                "status": "missing",
                "required_for": "preliminary_diagnosis",
            })

        approval = mem.get("human_approval", "")
        if approval:
            reqs.append({
                "id": "approval_rules",
                "label": "Qué acciones necesitan aprobación humana",
                "status": "confirmed" if approval in ("required", "conditional") else "partial",
                "required_for": "implementation",
            })
        else:
            reqs.append({
                "id": "approval_rules",
                "label": "Qué acciones necesitan aprobación humana",
                "status": "missing",
                "required_for": "implementation",
            })

        volume = mem.get("volume", "")
        if volume:
            reqs.append({
                "id": "volume",
                "label": "Volumen aproximado de consultas",
                "status": "confirmed",
                "required_for": "full_diagnosis",
            })
        else:
            reqs.append({
                "id": "volume",
                "label": "Volumen aproximado de consultas",
                "status": "missing",
                "required_for": "full_diagnosis",
            })

        has_any_confirmed = any(r["status"] == "confirmed" for r in reqs)
        has_any_missing = any(r["status"] != "confirmed" for r in reqs)
        if not has_any_confirmed or not has_any_missing:
            return None

        req_signature = tuple(
            (r["id"], r["status"]) for r in reqs
        )
        last_sig = state.slots.get("missing_requirements_last_signature")
        if last_sig is not None:
            last_sig_normalized = tuple(tuple(p) for p in last_sig)
            if last_sig_normalized == req_signature:
                return None
        state.slots["missing_requirements_last_signature"] = [[p[0], p[1]] for p in req_signature]

        return {
            "type": "missing_requirements",
            "title": "Qué falta para afinar el diagnóstico",
            "description": "Ya hay una orientación inicial. Estos datos ayudarían a hacerla más precisa.",
            "requirements": reqs[:5],
            "actions": [
                {
                    "id": "continue",
                    "label": "Completar datos",
                    "intent": "continue_conversation",
                    "style": "secondary",
                },
                {
                    "id": "show_diagnosis",
                    "label": "Ver diagnóstico actual",
                    "intent": "show_current_diagnosis",
                    "style": "primary",
                },
            ],
        }

    @staticmethod
    def _build_diagnosis_action_card(
        state: ConversationState,
        should_diagnose: bool,
        diagnosis: dict[str, Any] | None,
        intent: Any,
    ) -> dict[str, object] | None:
        if not should_diagnose or not diagnosis:
            return None
        if intent.intent not in (IntentType.REQUEST_DIAGNOSIS, IntentType.STOP_INTERVIEW):
            return None

        sig = (diagnosis.get("confidence", ""), diagnosis.get("availability", ""))
        last_sig = state.slots.get("diagnosis_card_last_signature")
        if last_sig is not None:
            last_sig_normalized = tuple(last_sig)
            if last_sig_normalized == sig:
                return None
        state.slots["diagnosis_card_last_signature"] = list(sig)

        status_map: dict[str, str] = {
            "available_now": "available_today",
            "requires_validation": "requires_integration",
            "custom_solution": "requires_integration",
            "not_in_immediate_catalog": "planned_extension",
            "not_recommended": "not_recommended",
        }
        status = status_map.get(diagnosis.get("availability", ""), "feasible")

        next_step = (diagnosis.get("next_step") or "").strip()
        summary_raw = diagnosis.get("summary") or ""
        if isinstance(summary_raw, str) and summary_raw.strip() and len(summary_raw) > 10 and summary_raw.strip()[0].isupper():
            summary = summary_raw.strip()
        elif next_step and (
            not next_step.startswith("validate")
            and not next_step.startswith("design")
            and not next_step.startswith("evaluate")
            and not next_step.startswith("define")
        ):
            summary = next_step
        else:
            summary = "Se puede avanzar con la información recopilada."

        return {
            "type": "diagnosis_action_card",
            "title": "Diagnóstico preliminar disponible",
            "summary": summary,
            "status": status,
            "confidence": diagnosis.get("confidence", "low"),
            "primary_action": {
                "id": "continue_refining",
                "label": "Afinar diagnóstico",
                "intent": "continue_conversation",
                "style": "secondary",
            },
            "secondary_actions": [
                {
                    "id": "show_current",
                    "label": "Ver diagnóstico actual",
                    "intent": "show_current_diagnosis",
                    "style": "primary",
                },
            ],
        }

    @staticmethod
    def _build_product_fit_card(
        state: ConversationState,
        should_diagnose: bool,
    ) -> dict[str, object] | None:
        if not should_diagnose and state.semantic_memory.get("diagnosis_status") != "completed":
            return None
        mem = state.semantic_memory or {}
        channels = mem.get("channels", [])
        goals = state.slots.get("automation_goals", [])

        matched: list[dict[str, Any]] = []
        channels_set = set(channels)
        for product in PRODUCT_CATALOG:
            req = product.get("required_channels", [])
            if req and not channels_set.intersection(req):
                continue
            goal_match = not product["match_goals"] or any(g in goals for g in product["match_goals"])
            if goal_match:
                matched.append(product)

        if not matched:
            return None
        product = matched[0]

        sig = product["code"]
        last_sig = state.slots.get("product_fit_card_last_signature")
        if last_sig == sig:
            return None
        state.slots["product_fit_card_last_signature"] = sig

        return {
            "type": "product_fit_card",
            "product_code": product["code"],
            "product_name": product["name"],
            "fit_score": 75,
            "status": product["status"],
            "summary": product["summary"],
            "good_fit_reasons": product["reasons"],
            "limitations": product["limitations"],
            "recommended_next_step": product["next_step"],
            "actions": [
                {
                    "id": "show_diagnosis",
                    "label": "Ver diagnóstico",
                    "intent": "show_current_diagnosis",
                    "style": "primary",
                },
            ],
        }

    def _is_diagnosis_request(self, message: str, state: ConversationState) -> bool:
        if DIAGNOSIS_REQUEST_PATTERNS.search(message):
            state.semantic_memory["diagnosis_status"] = "requested"
            return True
        if state.semantic_memory.get("diagnosis_status") in ("completed", "sufficient"):
            return True
        return False

    # ------------------------------------------------------------------
    # Retrieval query synthesis
    # ------------------------------------------------------------------

    def _build_retrieval_query(self, input: AssistantTurnInput, state: ConversationState) -> str:
        mem = state.semantic_memory or {}
        parts = [input.user_message]
        if mem.get("current_process"):
            parts.append(str(mem["current_process"]))
        if mem.get("main_problem"):
            parts.append(str(mem["main_problem"]))
        query = " ".join(parts)
        return query[:500]

    @staticmethod
    def _make_retrieval_input(original: AssistantTurnInput, query: str) -> AssistantTurnInput:
        from dataclasses import replace
        return replace(original, user_message=query)

    # ------------------------------------------------------------------
    # Answered questions tracking
    # ------------------------------------------------------------------

    def _mark_answered_questions(self, state: ConversationState, input: AssistantTurnInput) -> None:
        questions = state.asked_questions or []
        if not questions:
            return
        msg_lower = input.user_message.lower()
        updated = False
        for q in questions:
            if q.get("answered"):
                continue
            intent = q.get("intent", "")
            question_text = (q.get("question_text", "") or "").lower()
            # Primary: keyword-based intent matching
            if self._message_answers_intent(msg_lower, intent):
                q["answered"] = True
                q["answer_evidence"] = input.user_message[:200]
                q["answered_turn"] = state.turn_count
                updated = True
                continue
            # Fallback: if message contains key terms from the question,
            # treat it as a direct answer to that question.
            if question_text and not intent.startswith("identify_"):
                q_words = {w for w in question_text.split() if len(w) > 3}
                msg_words = {w for w in msg_lower.split() if len(w) > 3}
                overlap = q_words & msg_words
                if len(overlap) >= 2:
                    q["answered"] = True
                    q["answer_evidence"] = input.user_message[:200]
                    q["answered_turn"] = state.turn_count
                    updated = True
        if updated:
            state.asked_questions = questions

    @staticmethod
    def _message_answers_intent(msg_lower: str, intent: str) -> bool:
        mapping = {
            "identify_channel": ["whatsapp", "email", "correo", "web", "sitio", "teléfono", "telefono", "chat", "presencial", "app", "gmail", "instagram", "facebook", "portal"],
            "identify_volume": ["diario", "diaria", "por día", "por dia", "mensual", "semanal", "consulta", "mensaje", "llamada", "50", "60", "80", "100", "120", "150", "200", "300", "500"],
            "clarify_current_process": ["manual", "excel", "planilla", "sistema", "responde", "copia", "escribe", "busca", "persona", "gestiona", "cruce", "cruza", "descarga", "arma", "armado", "reporte", "reportes", "paso", "proceso", "flujo"],
            "identify_data_source": ["planilla", "excel", "sheet", "sistema", "base", "programa", "software", "app", "archivo", "erp", "crm", "base de datos", "sql", "api", "web"],
            "confirm_human_approval": ["supervisor", "jefe", "revisa", "aprobación", "aprobacion", "persona", "humano", "dueño", "dueña", "gerente", "coordinador", "socio", "director"],
            "clarify_desired_outcome": ["quiero", "necesito", "buscamos", "objetivo", "meta", "automatizar", "ordenar", "mejorar", "acelerar", "optimizar", "digitalizar"],
            "identify_rules": ["regla", "criterio", "política", "politica", "depende", "decide", "según", "segun", "caso", "si", "cuando", "condición"],
        }
        keywords = mapping.get(intent, [])
        if keywords and any(k in msg_lower for k in keywords):
            return True
        # Fallback: for unknown intents (other:...), any response moves the
        # conversation forward rather than re-asking.
        if intent.startswith("other:"):
            return True
        return False

    def _track_asked_questions(self, state: ConversationState, response: str) -> None:
        if "?" not in response:
            return
        questions = state.asked_questions or []
        answered_intents = {q.get("intent", "") for q in questions if q.get("answered")}
        for line in response.split("\n"):
            if "?" in line:
                intent = _classify_question_intent(line)
                if intent and intent not in answered_intents:
                    existing = {q.get("intent", "") for q in questions}
                    if intent not in existing:
                        questions.append({
                            "intent": intent,
                            "question_text": line.strip(),
                            "turn": state.turn_count,
                            "answered": False,
                            "answer_evidence": "",
                        })
        state.asked_questions = questions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _skeleton_response(self, input, state, events, metrics) -> AssistantTurnOutput:
        ack = self._prompt_policy.build_safe_ack()
        output = AssistantTurnOutput(
            response_text=ack,
            response_type="skeleton_ack",
            retrieved_sources=[],
            guardrail_result=self._guardrail_policy.evaluate_response(ack),
            events=events,
            metrics=metrics,
            next_state=state,
            turn_decision={
                "action": "reflect_and_ask",
                "retrieval_query": "",
                "diagnosis_status": "gathering",
                "readiness_reason": "no_llm",
                "intent": "",
                "intent_scope": "",
                "intent_confidence": 0.0,
                "intent_source": "unavailable",
                "matched_rule": None,
                "classifier_called": False,
                "generation": {
                    "status": "unavailable",
                    "model": "",
                    "fallback_used": False,
                    "fallback_reason": "no_llm_provider",
                },
                "diagnosis_built": False,
            },
            diagnosis=None,
            interaction_block=None,
        )
        events.append(ProgressiveEvent(event_type="team360.done", payload={"mode": "skeleton_no_llm"}, safe_to_show=True))
        self._save_state(state)
        self._metrics.record_turn(input, output)
        self._audit.record(input, output)
        return output

    def _validate_input(self, input: AssistantTurnInput) -> None:
        if not input.session_id or not input.session_id.strip():
            raise InvalidAssistantRuntimeInputError("session_id is required")
        if not input.assistant_instance_code:
            raise InvalidAssistantRuntimeInputError("assistant_instance_code is required")
        if not input.user_message or not input.user_message.strip():
            raise InvalidAssistantRuntimeInputError("user_message is required")

    def _load_or_create_state(self, input: AssistantTurnInput) -> ConversationState:
        state: ConversationState | None = None
        if self._state_repo:
            try:
                state = self._state_repo.load(input.session_id)
            except SalesDiagnosisRuntimeError:
                pass
        if state is None:
            state = ConversationState(
                session_id=input.session_id,
                assistant_instance_code=input.assistant_instance_code,
                package_code=input.package_code,
                knowledge_scope_code=input.knowledge_scope_code,
            )
        if not state.semantic_memory:
            state.semantic_memory = {"diagnosis_status": "gathering"}
        state.turn_count += 1
        return state

    def _save_state(self, state: ConversationState) -> None:
        if self._state_repo:
            try:
                self._state_repo.save(state)
            except SalesDiagnosisRuntimeError:
                pass


QUESTION_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("identify_channel", ["canal", "whatsapp", "email", "web", "por dónde", "por donde", "por qué medio"]),
    ("identify_volume", ["cuántos", "cuantas", "volumen", "diariamente", "por día", "por dia", "frecuencia", "cantidad", "cada cuánto"]),
    ("clarify_current_process", ["cómo gestiona", "como gestiona", "cómo maneja", "como maneja", "cómo hace", "como hace", "proceso actual", "hoy", "actualmente", "cómo lo hacen", "cómo es el proceso"]),
    ("identify_data_source", ["planilla", "excel", "sistema", "base de datos", "dónde", "donde", "fuente", "dónde está", "donde esta"]),
    ("confirm_human_approval", ["aprobación", "aprobacion", "supervisor", "revisa", "persona", "humano", "quién", "quien", "quién revisa", "quien revisa"]),
    ("identify_exception", ["excepción", "excepcion", "caso especial", "particular", "dudoso", "excepcional"]),
    ("clarify_desired_outcome", ["resultado", "objetivo", "meta", "qué querés", "que queres", "qué esperás", "que esperas"]),
    ("identify_rules", ["regla", "criterio", "política", "politica", "decide", "cómo sabés", "como sabes", "qué criterio"]),
]


def _classify_question_intent(question: str) -> str:
    q_lower = question.lower()
    for intent, keywords in QUESTION_INTENT_PATTERNS:
        if any(k in q_lower for k in keywords):
            return intent
    return f"other:{question[:60]}"


def _last_question_intent(state: ConversationState) -> str:
    questions = state.asked_questions or []
    if not questions:
        return ""
    last = questions[-1]
    return last.get("intent", "")


def _hebrew_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    hebrew = sum(1 for c in text if "\u0590" <= c <= "\u05FF")
    return hebrew / len(text)


def _latin_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return latin / len(text)
