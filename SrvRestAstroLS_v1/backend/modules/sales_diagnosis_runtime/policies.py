from __future__ import annotations

from typing import Any

from modules.sales_diagnosis_runtime.contracts import (
    FORBIDDEN_TERMS,
    PLANNED_EXTENSIONS,
    SAFE_ACK_TEXT,
    SALES_DIAGNOSIS_INSTANCE_CODE,
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
            "Respondé primero con una respuesta directa a la pregunta del usuario "
            "en 1 o 2 frases; "
            "después explicá el límite o el próximo paso si hace falta. "
            "No inventes precios, plazos, SLA ni integraciones no documentadas. "
            "No vendas Step-to-Action, lead_capture, diagnostic_code, "
            "WhatsApp handoff, CRM ni cierre de ventas automático como disponibles. "
            "No afirmes integración CRM vía API REST como lista; si aparece CRM "
            "en el contexto, tratalo como referencia externa o no documentada "
            "salvo que la fuente diga explícitamente que está disponible hoy. "
            "Diferenciá claramente entre:\n"
            "- **automatizable**: existe documentación y se puede vender hoy.\n"
            "- **vendible hoy**: hay pricing o caso de uso documentado.\n"
            "- **planned_extension**: aparece como capacidad futura, "
            "no debe venderse como lista.\n"
            "- **no documentado**: no hay información en el knowledge base.\n"
            "Reglas de respuesta para el diagnóstico headless:\n"
            "- Para tiempo de diagnóstico, podés decir que responde en pocos minutos "
            "o normalmente en menos de 10 minutos; no prometas implementación inmediata.\n"
            "- Para instalación inicial, si no hay una fuente que diga lo contrario, "
            "indicá que no hace falta instalar software para empezar y que se usa "
            "desde el navegador.\n"
            "- Para estado actual del proceso, distinguí manual, parcialmente "
            "automatizado y ya automatizado; no asumas que todo es manual.\n"
            "- Para MFA, permisos cerrados o sistemas restringidos, explicá que "
            "puede quedar bloqueado, requiere aprobación humana y no se deben "
            "bypassear controles.\n"
            "- Para comparación con partners, diferenciá Team360 hoy de alternativas "
            "externas y no prometas capacidades futuras.\n"
            "- Para preguntas sobre lead generation, aclarar que el diagnóstico no "
            "debe ser un formulario de leads disfrazado: debe ser honesto y puede "
            "decir que no conviene automatizar.\n"
            "- Para alucinación, responsabilidad o costo de error, aclarar que el "
            "diagnóstico es preliminar, no garantiza viabilidad, no afirma sin datos "
            "y puede requerir validación adicional.\n"
            "- Para trampas o respuestas falsas, explicá que la calidad de la "
            "información cambia el resultado y que no conviene mentir.\n"
            "- Para incentivos comerciales, respondé que no siempre es automatizable, "
            "la evaluación es caso por caso y a veces conviene no automatizar.\n"
            "Frases canónicas útiles cuando aplican: no necesitas instalar nada; "
            "detecta si ya está automatizado; distingue manual de automatizado; "
            "puede quedar bloqueado por permisos cerrados; diferencia entre "
            "Team360 hoy y otro partner; diagnóstico honesto; si no hay datos "
            "no afirma; respuestas falsas cambian el resultado.\n"
            "Hacé máximo 3 preguntas por turno. "
            "Respondé en español claro, sin HTML, sin formato AG-UI."
        )

    def build_turn_prompt(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        parts = [f"Usuario: {input.user_message}"]
        if context:
            parts.append("")
            parts.append("Contexto recuperado del knowledge base:")
            for i, c in enumerate(context, 1):
                src = c.source_uri or ""
                title = c.title or ""
                path = c.node_path or ""
                meta = f"[{title}]({src})" if title and src else title or src
                if path:
                    meta = f"{meta} — {path}"
                parts.append(f"{i}. {meta}")
                parts.append(f"   {c.content_preview or '(sin preview)'}")
        if state.slots:
            parts.append(f"\nSlots actuales: {state.slots}")
        if state.history_summary:
            parts.append(f"\nHistorial: {state.history_summary}")
        parts.append(
            "\nRespondé de forma útil, concreta y sin prometer "
            "capacidades no disponibles. "
            "Formato recomendado: respuesta directa, límite honesto y próximo "
            "paso concreto si aplica. Evitá responder con un bloqueo genérico "
            "cuando la pregunta sea comercialmente válida. "
            "Máximo 3 preguntas. Usá español claro. Sin HTML ni AG-UI."
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

    Hardened in Fase 1.8c:
    - Individual detection methods for each future capability
    - CRM and auto billing/sales closing detection
    - Context-aware fallback builder
    - Better word-boundary-aware regex patterns
    """

    DECLINE_PATTERNS = frozenset({
        "no está disponible",
        "no está list",
        "todavía no",
        "capacidad futura",
        "extensión futura",
        "no ofrecemos",
        "no incluimos",
        "no contamos",
        "no tenemos información",
        "no documentado",
        "no define",
        "no fija",
        "no informa",
        "no cubre",
        "consultá con nuestro equipo",
        "no debe venderse como listo",
        "no debe venderse como lista",
        "no prometo",
        "no prometemos",
        "no promete",
        "no garantiza",
        "no garantizamos",
        "no asumimos",
        "sin prometer",
        "sin vender",
        "no vender",
        "preliminar",
        "validación adicional",
        "validacion adicional",
        "caso por caso",
        "no siempre",
        "no conviene automatizar",
        "depende del alcance",
        "depende del acuerdo",
        "según el alcance",
        "segun el alcance",
        "debe pactarse",
        "puede quedar bloqueado",
        "requiere aprobación humana",
        "requiere aprobacion humana",
    })

    CAPABILITY_PATTERNS: dict[str, tuple[str, ...]] = {
        "step_to_action": ("step-to-action", "steptoaction"),
        "lead_capture": ("lead capture", "lead_capture"),
        "diagnostic_code": ("diagnostic code", "diagnostic_code", "código de diagnóstico"),
        "whatsapp_handoff": (
            "whatsapp handoff",
            "whatsapp_handoff",
            "handoff por whatsapp",
            "traspaso a whatsapp",
        ),
        "crm": (
            "integración con crm",
            "integracion con crm",
            "crm integrado",
            "crm lista",
            "crm listo",
            "crm operativo",
            "crm disponible",
            "customer relationship management",
        ),
        "auto_billing": (
            "cierre de ventas automático",
            "facturación automática",
            "auto billing", "autobilling",
        ),
    }

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

        # Planned extension checks — any future capability claimed as ready
        for cap, patterns in self.CAPABILITY_PATTERNS.items():
            if any(p in text_lower for p in patterns):
                if not self._has_decline(text_lower):
                    result.planned_extension_misrepresented = True
                    result.notes.append(f"planned_extension_misrepresented:{cap}")

        # Pricing/SLA hallucination check
        pricing_terms = {"precio", "precios", "plazo", "plazos", "sla"}
        for term in pricing_terms:
            if term in text_lower:
                if not self._has_decline(text_lower):
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
        input: AssistantTurnInput | None = None,
        state: ConversationState | None = None,
    ) -> str:
        if result := self._build_contextual_fallback(reason, input, state):
            return result
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

    def _build_contextual_fallback(
        self,
        reason: str,
        input: AssistantTurnInput | None,
        state: ConversationState | None,
    ) -> str | None:
        if not input or not input.user_message:
            return None
        if "precio" in reason or "sla" in reason or "pricing" in reason:
            return (
                "Entiendo tu consulta sobre costos o plazos. "
                "No tengo información de precios ni SLA en mi base de conocimiento. "
                "Por favor consultá con nuestro equipo comercial "
                "para obtener una cotización personalizada."
            )
        if "planned_extension" in reason:
            cap = reason.split(":")[-1] if ":" in reason else ""
            cap_label = cap.replace("_", " ") if cap else "esa capacidad"
            return (
                f"Entiendo tu interés en {cap_label}. "
                f"Según la documentación disponible, {cap_label} "
                f"aparece como extensión planificada y no está disponible "
                f"actualmente. ¿Querés que te informe sobre "
                f"otras capacidades que sí están documentadas?"
            )
        return None

    @staticmethod
    def _has_decline(text: str) -> bool:
        return any(p in text for p in GuardrailPolicy.DECLINE_PATTERNS)

    @staticmethod
    def _has_near_negation(text: str, term: str, window: int = 60) -> bool:
        """Check if a negation token appears within window chars of term."""
        negation_tokens = {
            "no", "no tenemos", "no contamos", "no está",
            "todavía no", "falta", "no documentado",
            "sin prometer", "evita prometer",
            "depende", "según el alcance", "segun el alcance",
        }
        idx = text.find(term)
        if idx == -1:
            return False
        start = max(0, idx - window)
        end = min(len(text), idx + len(term) + window)
        context = text[start:end]
        return any(tok in context for tok in negation_tokens)

    # ------------------------------------------------------------------
    # Individual capability checks
    # ------------------------------------------------------------------

    @staticmethod
    def _capability_ready(text: str, patterns: tuple[str, ...]) -> bool:
        text_lower = text.lower()
        if not any(p in text_lower for p in patterns):
            return False
        return not GuardrailPolicy._has_decline(text_lower)

    @classmethod
    def is_step_to_action_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(
            response_text, cls.CAPABILITY_PATTERNS["step_to_action"]
        )

    @classmethod
    def is_lead_capture_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(
            response_text, cls.CAPABILITY_PATTERNS["lead_capture"]
        )

    @classmethod
    def is_diagnostic_code_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(
            response_text, cls.CAPABILITY_PATTERNS["diagnostic_code"]
        )

    @classmethod
    def is_whatsapp_handoff_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(
            response_text, cls.CAPABILITY_PATTERNS["whatsapp_handoff"]
        )

    @classmethod
    def is_crm_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(
            response_text, cls.CAPABILITY_PATTERNS["crm"]
        )

    @classmethod
    def is_auto_billing_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(
            response_text, cls.CAPABILITY_PATTERNS["auto_billing"]
        )
