"""Tests for hardened PromptPolicy and GuardrailPolicy.

No network calls. No DB. No LLM.
"""

from __future__ import annotations

import pytest

from modules.sales_diagnosis_runtime import (
    AssistantTurnInput,
    ConversationState,
    GuardrailPolicy,
    PromptPolicy,
    RetrievedChunk,
)


SAMPLE_CHUNKS = [
    RetrievedChunk(
        chunk_id="c1",
        document_id="d1",
        knowledge_scope_id="ks_test",
        source_uri="/docs/automatizacion.md",
        title="Automatización de ventas",
        node_path="/automatizaciones/ventas",
        score=0.95,
        content_preview="Guía para automatizar procesos de ventas con Team360.",
        content="Contenido completo...",
    ),
]

SAMPLE_INPUT = AssistantTurnInput(
    session_id="s1",
    assistant_instance_code="team360_sales_diagnosis",
    package_code="pkg_sales_diagnosis",
    knowledge_scope_code="ks_test",
    user_message="Quiero automatizar ventas",
)

SAMPLE_STATE = ConversationState(
    session_id="s1",
    assistant_instance_code="team360_sales_diagnosis",
    package_code="pkg_sales_diagnosis",
    knowledge_scope_code="ks_test",
)


# ===================================================================
# PromptPolicy
# ===================================================================


class TestPromptPolicyHardened:
    def test_safe_ack_is_not_intelligent_answer(self):
        policy = PromptPolicy()
        ack = policy.build_safe_ack()
        assert ack is not None
        assert "Recibí" in ack or "Gracias" in ack or "recibí" in ack
        assert len(ack.split()) <= 30

    def test_safe_ack_does_not_claim_future_capabilities(self):
        policy = PromptPolicy()
        ack = policy.build_safe_ack().lower()
        for cap in ["step-to-action", "lead capture", "diagnostic code", "whatsapp"]:
            assert cap not in ack

    def test_system_prompt_contains_required_guardrails(self):
        policy = PromptPolicy()
        prompt = policy.build_system_prompt()
        prompt_lower = prompt.lower()
        assert "step-to-action" in prompt_lower
        assert "lead_capture" in prompt_lower
        assert "diagnostic_code" in prompt_lower
        assert "whatsapp handoff" in prompt_lower
        assert "automatizable" in prompt_lower
        assert "vendible" in prompt_lower

    def test_system_prompt_encourages_conversation(self):
        policy = PromptPolicy()
        prompt = policy.build_system_prompt().lower()
        assert "una sola pregunta" in prompt
        assert "no repitas preguntas" in prompt
        assert "historial" in prompt
        assert "informales" in prompt

    def test_system_prompt_distinguishes_feasibility_from_availability(self):
        policy = PromptPolicy()
        prompt = policy.build_system_prompt().lower()
        assert "factibilidad técnica" in prompt
        assert "disponibilidad comercial" in prompt
        assert "automatizable" in prompt
        assert "vendible" in prompt

    def test_system_prompt_does_not_reject_channels(self):
        policy = PromptPolicy()
        prompt = policy.build_system_prompt().lower()
        assert "canal no está disponible" not in prompt or "diagnosticá el flujo completo" in prompt
        assert "diagnosticá el flujo completo" in prompt

    def test_system_prompt_handles_explicit_diagnosis_request(self):
        policy = PromptPolicy()
        prompt = policy.build_system_prompt().lower()
        assert "diagnóstico explícitamente" in prompt or "dame el diagnóstico" in prompt or "dame el diagnostico" in prompt
        assert "pida diagnóstico" in prompt or "con esto alcanza" in prompt or "decime qué hago" in prompt

    def test_turn_prompt_includes_retrieved_chunks(self):
        policy = PromptPolicy()
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, SAMPLE_STATE, SAMPLE_CHUNKS)
        assert SAMPLE_INPUT.user_message in prompt
        assert SAMPLE_CHUNKS[0].title in prompt
        assert SAMPLE_CHUNKS[0].source_uri in prompt
        assert SAMPLE_CHUNKS[0].content_preview in prompt

    def test_turn_prompt_limits_to_one_question(self):
        policy = PromptPolicy()
        for context_arg in [[], SAMPLE_CHUNKS]:
            prompt = policy.build_turn_prompt(
                SAMPLE_INPUT, SAMPLE_STATE, context_arg
            )
            assert "una sola pregunta" in prompt or "UNA SOLA pregunta" in prompt

    def test_turn_prompt_without_context_is_valid(self):
        policy = PromptPolicy()
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, SAMPLE_STATE, [])
        assert SAMPLE_INPUT.user_message in prompt

    def test_turn_prompt_requests_followup_when_only_requested_without_base(self):
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            semantic_memory={"diagnosis_status": "requested"},
        )
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, state, [])
        assert "ACCIÓN: DIAGNÓSTICO" in prompt

    def test_turn_prompt_switches_to_diagnosis_when_sufficient_and_mentions_validation(self):
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            semantic_memory={
                "diagnosis_status": "sufficient",
                "contradictions": ["User corrected discount approval"],
            },
        )
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, state, [])
        assert "ACCIÓN: DIAGNÓSTICO" in prompt
        assert "PUNTO A VALIDAR" in prompt
        assert "Correcciones registradas" in prompt

    def test_turn_prompt_includes_history(self):
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            history_summary="Usuario: vendo repuestos\nVera: contame mas",
        )
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, state, [])
        assert "Historial" in prompt or "historial" in prompt
        assert "vendo repuestos" in prompt

    def test_turn_prompt_instructions_prevent_repeat_questions(self):
        policy = PromptPolicy()
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, SAMPLE_STATE, [])
        prompt_lower = prompt.lower()
        assert "no repetir preguntas" in prompt_lower or "no repitas" in prompt_lower

    # ------------------------------------------------------------------
    # Proactive pause (offer_pause) tests
    # ------------------------------------------------------------------

    def test_offer_pause_when_turn_4_with_process_and_channel(self):
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=4,
            semantic_memory={
                "diagnosis_status": "gathering",
                "current_process": "ventas con Kommo y Meta",
                "channels": ["whatsapp"],
            },
        )
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, state, [])
        assert "PAUSA Y OFRECER OPCIÓN" in prompt
        assert "NO hagas una nueva pregunta" in prompt
        assert "conclusión preliminar" in prompt

    def test_offer_pause_suppressed_when_user_asks_to_continue(self):
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=4,
            semantic_memory={
                "diagnosis_status": "gathering",
                "current_process": "ventas con Kommo y Meta",
                "channels": ["whatsapp"],
            },
        )
        continue_input = AssistantTurnInput(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="seguí preguntando",
        )
        prompt = policy.build_turn_prompt(continue_input, state, [])
        assert "PAUSA Y OFRECER OPCIÓN" not in prompt
        assert "SEGUIR PREGUNTANDO" in prompt

    def test_no_offer_pause_when_turn_below_4(self):
        policy = PromptPolicy()
        for turn in range(1, 4):
            state = ConversationState(
                session_id="s1",
                assistant_instance_code="team360_sales_diagnosis",
                package_code="pkg_sales_diagnosis",
                knowledge_scope_code="ks_test",
                turn_count=turn,
                semantic_memory={
                    "diagnosis_status": "gathering",
                    "current_process": "ventas",
                    "channels": ["web"],
                },
            )
            prompt = policy.build_turn_prompt(SAMPLE_INPUT, state, [])
            assert "PAUSA Y OFRECER OPCIÓN" not in prompt, f"Unexpected pause at turn {turn}"

    def test_no_offer_pause_without_process(self):
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=5,
            semantic_memory={
                "diagnosis_status": "gathering",
                "channels": ["web"],
            },
        )
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, state, [])
        assert "PAUSA Y OFRECER OPCIÓN" not in prompt

    def test_no_offer_pause_without_channel(self):
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=5,
            semantic_memory={
                "diagnosis_status": "gathering",
                "current_process": "ventas con Kommo y Meta",
            },
        )
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, state, [])
        assert "PAUSA Y OFRECER OPCIÓN" not in prompt

    def test_offer_pause_not_triggered_in_diagnosis_mode(self):
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=5,
            semantic_memory={
                "diagnosis_status": "requested",
                "current_process": "ventas con Kommo y Meta",
                "channels": ["whatsapp"],
            },
        )
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, state, [])
        assert "ACCIÓN: DIAGNÓSTICO" in prompt
        assert "PAUSA Y OFRECER OPCIÓN" not in prompt

    def test_offer_pause_continue_variants_are_all_detected(self):
        policy = PromptPolicy()
        base_state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=4,
            semantic_memory={
                "diagnosis_status": "gathering",
                "current_process": "ventas con Kommo y Meta",
                "channels": ["whatsapp"],
            },
        )
        variants = [
            "seguí preguntando",
            "seguí",
            "más detalle",
            "afinemos",
            "preguntame más",
            "continuá",
            "quiero seguir respondiendo",
            "contame más",
            "dale seguí",
            "ok seguí",
            "tell me more",
            "keep going",
            "ask me more",
            "wants more details",
        ]
        for msg in variants:
            inp = AssistantTurnInput(
                session_id="s1",
                assistant_instance_code="team360_sales_diagnosis",
                package_code="pkg_sales_diagnosis",
                knowledge_scope_code="ks_test",
                user_message=msg,
            )
            prompt = policy.build_turn_prompt(inp, base_state, [])
            assert "PAUSA Y OFRECER OPCIÓN" not in prompt, f"Failed for: {msg}"
            assert "SEGUIR PREGUNTANDO" in prompt, f"Expected ask variant for: {msg}"

    def test_offer_pause_kommo_meta_full_scenario(self):
        """Simulate Kommo + Meta + ROAS + Excel conversation."""
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=5,
            semantic_memory={
                "diagnosis_status": "gathering",
                "current_process": "ventas con Kommo y Meta, ROAS, ventas/pedidos cargados manualmente en Excel",
                "channels": ["kommo", "meta", "whatsapp"],
                "systems_and_data_sources": ["excel"],
                "entities": ["roas", "sales", "kpi"],
                "human_approval": "required",
            },
        )
        prompt = policy.build_turn_prompt(SAMPLE_INPUT, state, [])
        assert "PAUSA Y OFRECER OPCIÓN" in prompt
        assert "NO hagas una nueva pregunta" in prompt
        assert "conclusión preliminar" in prompt

    def test_offer_pause_continue_in_english(self):
        policy = PromptPolicy()
        state = ConversationState(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            turn_count=4,
            semantic_memory={
                "diagnosis_status": "gathering",
                "current_process": "automating sales",
                "channels": ["email"],
            },
        )
        continue_input = AssistantTurnInput(
            session_id="s1",
            assistant_instance_code="team360_sales_diagnosis",
            package_code="pkg_sales_diagnosis",
            knowledge_scope_code="ks_test",
            user_message="ask me more",
        )
        prompt = policy.build_turn_prompt(continue_input, state, [])
        assert "PAUSA Y OFRECER OPCIÓN" not in prompt
        assert "SEGUIR PREGUNTANDO" in prompt


# ===================================================================
# GuardrailPolicy — individual capability checks
# ===================================================================


class TestGuardrailPolicyStepToAction:
    def test_flags_step_to_action_ready_claim(self):
        assert GuardrailPolicy.is_step_to_action_ready(
            "Podemos activar Step-to-Action para vos."
        )
        assert not GuardrailPolicy.is_step_to_action_ready(
            "Step-to-Action no está disponible actualmente."
        )
        assert not GuardrailPolicy.is_step_to_action_ready(
            "Step-to-Action aparece como extensión futura."
        )


class TestGuardrailPolicyLeadCapture:
    def test_flags_lead_capture_ready_claim(self):
        assert GuardrailPolicy.is_lead_capture_ready(
            "Lead capture está disponible para tu caso."
        )
        assert not GuardrailPolicy.is_lead_capture_ready(
            "Lead capture no está disponible todavía."
        )
        assert not GuardrailPolicy.is_lead_capture_ready(
            "Lead capture es una capacidad futura."
        )


class TestGuardrailPolicyDiagnosticCode:
    def test_flags_diagnostic_code_ready_claim(self):
        assert GuardrailPolicy.is_diagnostic_code_ready(
            "Podemos generar un diagnostic code."
        )
        assert not GuardrailPolicy.is_diagnostic_code_ready(
            "Diagnostic code no está listo aún."
        )


class TestGuardrailPolicyWhatsAppHandoff:
    def test_flags_whatsapp_handoff_ready_claim(self):
        assert GuardrailPolicy.is_whatsapp_handoff_ready(
            "WhatsApp handoff está operativo."
        )
        assert not GuardrailPolicy.is_whatsapp_handoff_ready(
            "WhatsApp handoff no está disponible."
        )


class TestGuardrailPolicyCRM:
    def test_flags_crm_ready_claim(self):
        assert GuardrailPolicy.is_crm_ready(
            "La integración con CRM está lista."
        )
        assert not GuardrailPolicy.is_crm_ready(
            "CRM no está disponible todavía."
        )


class TestGuardrailPolicyAutoBilling:
    def test_flags_auto_billing_ready_claim(self):
        assert GuardrailPolicy.is_auto_billing_ready(
            "La facturación automática está lista."
        )
        assert not GuardrailPolicy.is_auto_billing_ready(
            "La facturación automática no está disponible."
        )


# ===================================================================
# GuardrailPolicy — evaluate_response integration
# ===================================================================


class TestGuardrailPolicyEvaluate:
    def test_plausible_safe_response_passes(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "Podemos automatizar ventas con nuestras herramientas documentadas."
        )
        assert result.passed

    def test_step_to_action_evaluate_rejects_ready_claim(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "Step-to-Action está listo para implementar."
        )
        assert not result.passed
        assert result.planned_extension_misrepresented

    def test_step_to_action_evaluate_allows_declined(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "Step-to-Action no está disponible actualmente."
        )
        assert result.passed

    def test_lead_capture_evaluate_rejects_ready_claim(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "Lead capture está disponible para tu negocio."
        )
        assert not result.passed
        assert result.planned_extension_misrepresented

    def test_lead_capture_evaluate_allows_declined(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "Lead capture no está disponible todavía."
        )
        assert result.passed

    def test_diagnostic_code_evaluate_rejects_ready_claim(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "Podemos generar un código de diagnóstico automático."
        )
        assert not result.passed
        assert result.planned_extension_misrepresented

    def test_whatsapp_handoff_evaluate_rejects_ready_claim(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "WhatsApp handoff está operativo para tu caso."
        )
        assert not result.passed
        assert result.planned_extension_misrepresented

    def test_whatsapp_channel_without_handoff_claim_passes(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "Podemos evaluar consultas que llegan por WhatsApp, "
            "sin vender WhatsApp handoff como listo."
        )
        assert result.passed

    def test_crm_evaluate_rejects_ready_claim(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "La integración con CRM está lista."
        )
        assert not result.passed
        assert result.planned_extension_misrepresented

    def test_crm_comparison_without_ready_claim_passes(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "El diagnóstico diferencia Team360 hoy de una alternativa con otro "
            "partner o CRM externo; no promete capacidades futuras."
        )
        assert result.passed

    def test_auto_billing_evaluate_rejects_ready_claim(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "El cierre de ventas automático está disponible."
        )
        assert not result.passed
        assert result.planned_extension_misrepresented

    def test_multiple_planned_extensions_all_declined_passes(self):
        policy = GuardrailPolicy()
        text = (
            "Step-to-Action no está disponible actualmente. "
            "Lead capture no está lista. "
            "Diagnostic code aparece como extensión futura. "
            "WhatsApp handoff no está disponible."
        )
        result = policy.evaluate_response(text)
        assert result.passed

    def test_pricing_claim_with_decline_passes(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "No contamos con información de precios en el knowledge actual."
        )
        assert result.passed

    def test_sla_claim_without_decline_fails(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "El SLA de respuesta es de 2 horas."
        )
        assert not result.passed
        assert result.pricing_sla_hallucination

    def test_sla_claim_with_decline_passes(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "No tenemos información de SLA. Consultá con nuestro equipo comercial."
        )
        assert not result.pricing_sla_hallucination

    def test_diagnostic_response_time_without_implementation_claim_passes(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "El diagnóstico responde en pocos minutos, normalmente en menos "
            "de 10 minutos; no promete implementación inmediata."
        )
        assert result.passed

    def test_implementation_timeline_claim_without_decline_fails(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "El plazo de implementación garantizado es de 2 días."
        )
        assert not result.passed

    def test_scope_dependent_cost_or_timeline_passes(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "El diagnóstico es preliminar: el costo y los plazos dependen "
            "del alcance y deben pactarse antes de implementar."
        )
        assert result.passed

    def test_commercially_acidic_answers_pass_when_honest(self):
        policy = GuardrailPolicy()
        safe_answers = [
            (
                "No es lead generation disfrazada: el diagnóstico debe ser "
                "honesto y puede decir que no conviene automatizar."
            ),
            (
                "El diagnóstico es preliminar, puede requerir validación "
                "adicional y no promete asumir el costo de la falla."
            ),
            (
                "No siempre es automatizable; se evalúa caso por caso y "
                "a veces conviene no automatizar."
            ),
            (
                "Si depende de MFA o permisos cerrados, puede quedar bloqueado "
                "y requiere aprobación humana; no se bypassa MFA."
            ),
        ]
        for answer in safe_answers:
            result = policy.evaluate_response(answer)
            assert result.passed, result.notes

    def test_too_many_questions_fails(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "¿Qué necesitas? ¿Automatizar? ¿Qué canal? ¿WhatsApp? ¿Email?"
        )
        assert result.max_questions_exceeded

    def test_empty_response_fails(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response("")
        assert result.empty_response
        assert not result.passed

    def test_whitespace_only_response_fails(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response("   \n  ")
        assert result.empty_response
        assert not result.passed

    def test_happy_path_response_passes(self):
        policy = GuardrailPolicy()
        result = policy.evaluate_response(
            "Podemos ayudarte con la automatización de ventas. "
            "Tenemos documentación disponible. "
            "¿Qué canal te interesa?"
        )
        assert result.passed


# ===================================================================
# GuardrailPolicy — fallback responses
# ===================================================================


class TestGuardrailPolicyFallback:
    def test_fallback_response_is_safe(self):
        policy = GuardrailPolicy()
        fallback = policy.build_fallback_response(reason="guardrail_violation")
        assert fallback is not None
        assert len(fallback.split()) <= 40

    def test_fallback_pricing_contextual(self):
        policy = GuardrailPolicy()
        fallback = policy.build_fallback_response(
            reason="unsupported_precio_claim",
            input=SAMPLE_INPUT,
        )
        assert "precios" in fallback.lower() or "costos" in fallback.lower()

    def test_fallback_planned_extension_contextual(self):
        policy = GuardrailPolicy()
        fallback = policy.build_fallback_response(
            reason="planned_extension_misrepresented:whatsapp_handoff",
            input=SAMPLE_INPUT,
        )
        assert "whatsapp" in fallback.lower() or "WhatsApp" in fallback

    def test_fallback_generic_without_input(self):
        policy = GuardrailPolicy()
        fallback = policy.build_fallback_response()
        assert "error" in fallback.lower() or "intentá" in fallback

    def test_fallback_guardrail_without_input(self):
        policy = GuardrailPolicy()
        fallback = policy.build_fallback_response(reason="guardrail_violation")
        assert "No puedo proporcionar" in fallback


# ===================================================================
# GuardrailPolicy — has_near_negation
# ===================================================================


class TestGuardrailPolicyNegation:
    def test_negation_detected_before_term(self):
        text = "no contamos con información de precios en este momento."
        assert GuardrailPolicy._has_near_negation(text, "precios")

    def test_negation_not_detected_when_missing(self):
        text = "El precio del servicio es accesible."
        assert not GuardrailPolicy._has_near_negation(text, "precio")

    def test_negation_detected_with_todavia_no(self):
        text = "Esa funcionalidad todavía no está disponible."
        assert GuardrailPolicy._has_near_negation(text, "funcionalidad")
