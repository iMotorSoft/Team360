from __future__ import annotations

from typing import Any

from modules.sales_diagnosis_runtime.contracts import (
    FORBIDDEN_TERMS,
    PLANNED_EXTENSIONS,
    SAFE_ACK_TEXT,
    AssistantTurnInput,
    ConversationState,
    GuardrailResult,
    RetrievedChunk,
)


# ---------------------------------------------------------------------------
# PromptPolicy
# ---------------------------------------------------------------------------


class PromptPolicy:
    """Defines system prompts, turn prompts and safe ack templates.

    All prompts are configurable by assistant_instance / package.
    This skeleton provides defaults. Full policy registry in PostgreSQL is
    future (Fase 1.8c).
    """

    def build_system_prompt(
        self,
        assistant_instance_code: str = "",
        package_code: str = "",
    ) -> str:
        return (
            "Sos un asistente de ventas y diagnóstico de automatización de Team360. "
            "Tu objetivo es entender qué necesita el usuario, "
            "recuperar contexto del knowledge base y orientar sin prometer "
            "capacidades no disponibles. "
            "No inventes precios, plazos, SLA ni integraciones no documentadas. "
            "No vendas Step-to-Action, lead_capture, diagnostic_code ni "
            "WhatsApp handoff como disponibles. "
            "Hacé máximo 3 preguntas por turno."
        )

    def build_turn_prompt(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        parts = [f"Usuario: {input.user_message}"]
        if context:
            parts.append("\nContexto recuperado:")
            for i, c in enumerate(context, 1):
                parts.append(f"{i}. [{c.title}] {c.content_preview}")
        if state.slots:
            parts.append(f"\nSlots actuales: {state.slots}")
        if state.history_summary:
            parts.append(f"\nHistorial: {state.history_summary}")
        parts.append(
            "\nRespondé de forma útil, concreta y sin prometer "
            "capacidades no disponibles."
        )
        return "\n".join(parts)

    def build_safe_ack(
        self,
        assistant_instance_code: str = "",
        package_code: str = "",
        domain: str = "",
    ) -> str:
        if domain == "commercial":
            return (
                "Gracias por tu consulta. Estoy revisando la información "
                "disponible sobre automatización para tu caso."
            )
        if domain == "technical":
            return (
                "Recibí el diagnóstico. Estoy buscando información relevante "
                "para orientarte."
            )
        return SAFE_ACK_TEXT


# ---------------------------------------------------------------------------
# GuardrailPolicy
# ---------------------------------------------------------------------------


class GuardrailPolicy:
    """Evaluates assistant responses against commercial safety rules.

    After Fase 1.7c validation:
    - 0 real forbidden claims
    - 0 planned_extension misrepresented
    - 0 pricing/SLA hallucination

    This skeleton implements the same heuristic layers from the lab evaluator.
    Full policy registry is future (Fase 1.8c).
    """

    def evaluate_response(
        self,
        response_text: str,
        input: AssistantTurnInput | None = None,
        state: ConversationState | None = None,
    ) -> GuardrailResult:
        result = GuardrailResult(passed=True)
        text_lower = response_text.lower()

        # Empty response check
        if not response_text.strip():
            result.empty_response = True
            result.passed = False
            result.notes.append("response_empty")
            return result

        # Forbidden claims check
        for term in FORBIDDEN_TERMS:
            if term in text_lower:
                has_negation = self._has_near_negation(text_lower, term)
                if not has_negation:
                    result.forbidden_claims.append(term)
                    result.notes.append(f"forbidden_term_found:{term}")

        # Planned extension check
        for cap in PLANNED_EXTENSIONS:
            cap_label = cap.replace("_", " ")
            if cap_label in text_lower:
                decline_patterns = [
                    "no está disponible",
                    "no está listo",
                    "todavía no",
                    "capacidad futura",
                    "no ofrecemos",
                    "no incluimos",
                ]
                has_decline = any(p in text_lower for p in decline_patterns)
                if not has_decline:
                    result.planned_extension_misrepresented = True
                    result.notes.append(f"planned_extension_misrepresented:{cap}")

        # Pricing/SLA hallucination check
        pricing_terms = {"precio", "precios", "plazo", "plazos", "sla"}
        for term in pricing_terms:
            if term in text_lower:
                decline_patterns = [
                    "no contamos",
                    "no tenemos información",
                    "no documentado",
                    "consultá con nuestro equipo",
                    "no está disponible",
                ]
                has_decline = any(p in text_lower for p in decline_patterns)
                if not has_decline:
                    result.pricing_sla_hallucination = True
                    result.notes.append(f"unsupported_{term}_claim")

        # Max questions check
        question_count = text_lower.count("?")
        if question_count > 3:
            result.max_questions_exceeded = True
            result.notes.append(f"max_questions_exceeded:{question_count}")

        if result.forbidden_claims or result.planned_extension_misrepresented:
            result.passed = False
        if result.pricing_sla_hallucination:
            result.passed = False

        return result

    def build_fallback_response(
        self,
        reason: str = "",
    ) -> str:
        if "guardrail" in reason or "unsafe" in reason:
            return (
                "No puedo proporcionar esa información porque excede "
                "los límites de lo que puedo confirmar. "
                "Consultá con nuestro equipo comercial."
            )
        return (
            "Ocurrió un error al procesar tu consulta. "
            "Por favor intentá de nuevo o escribinos directamente."
        )

    @staticmethod
    def _has_near_negation(text: str, term: str, window: int = 60) -> bool:
        """Check if a negation token appears within window chars of term."""
        negation_tokens = {
            "no", "no tenemos", "no contamos", "no está",
            "todavía no", "falta", "no documentado",
            "sin prometer", "evita prometer",
        }
        idx = text.find(term)
        if idx == -1:
            return False
        start = max(0, idx - window)
        end = min(len(text), idx + len(term) + window)
        context = text[start:end]
        return any(tok in context for tok in negation_tokens)

    @staticmethod
    def is_step_to_action_ready(response_text: str) -> bool:
        """Detect if a response falsely claims Step-to-Action is available."""
        text_lower = response_text.lower()
        if "step-to-action" not in text_lower and "steptoaction" not in text_lower:
            return False
        decline_patterns = [
            "no está disponible",
            "no está listo",
            "todavía no",
            "capacidad futura",
            "no ofrecemos",
        ]
        return not any(p in text_lower for p in decline_patterns)
