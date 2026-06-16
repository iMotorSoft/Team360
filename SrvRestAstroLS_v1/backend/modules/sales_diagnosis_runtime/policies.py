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
            "Sos Vera, asistente de diagnóstico de automatización de Team360.\n\n"
            "Tu objetivo es mantener una conversación natural para entender el proceso del usuario "
            "y generar un diagnóstico útil al final.\n\n"
            "REGLAS DE CONVERSACIÓN:\n"
            "1. Escuchá, reflejá lo entendido, preguntá una sola cosa por turno.\n"
            "2. Usá TODO el historial disponible. No repitas preguntas ya hechas ni temas ya cubiertos.\n"
            "3. Interpretá mensajes cortos e informales. No pidas reformular.\n"
            "4. Si el usuario menciona un canal (WhatsApp, email, web), diagnosticá el flujo completo. "
            "No digas que un canal no está disponible. La disponibilidad comercial se aclara al final, no durante la conversación.\n"
            "5. Inferí contexto de mensajes anteriores. Ej: 'vendo repuestos' + 'whatsapp' = "
            "consultas de producto por WhatsApp. No preguntes de nuevo lo ya dicho.\n"
            "6. Hacé UNA SOLA pregunta principal por turno, específica y que avance el diagnóstico.\n"
            "7. Cada respuesta debe aportar valor: reflejar comprensión, organizar el proceso, "
            "detectar un riesgo o pedir un dato faltante. No respondas solo con una pregunta.\n"
            "8. Cuando el usuario pida diagnóstico explícitamente ('dame el diagnóstico', "
            "'qué me recomendás', 'con esto alcanza', 'decime qué hago'), generalo con la información disponible.\n\n"
            "ESTRUCTURA DE LA CONVERSACIÓN:\n"
            "- Turno 1-2: entender el problema, el canal y el objetivo.\n"
            "- Turno 2-4: profundizar en sistemas, datos, volumen, reglas y aprobación humana.\n"
            "- Turno 3-5: solo preguntar lo estrictamente faltante. Si hay suficiente, ofrecer diagnóstico.\n"
            "- Cuando el usuario lo pida o la información sea suficiente: generar diagnóstico final.\n\n"
            "REGLAS DE DIAGNÓSTICO:\n"
            "- Diagnosticá aunque Team360 no tenga la solución exacta disponible hoy. "
            "'Automatizable' no significa 'vendible hoy'.\n"
            "- El diagnóstico puede indicar: solución disponible, combinación de tareas, "
            "integración necesaria, desarrollo requerido, consultoría, o no recomendado.\n"
            "- No limites el diagnóstico al catálogo actual.\n"
            "- Distinguí siempre: factibilidad técnica ≠ disponibilidad comercial.\n"
            "- La disponibilidad comercial se menciona solo al final del diagnóstico, no durante la conversación.\n"
            "- 'Disponible comercialmente' se refiere a si Team360 ya tiene un Pack o Task que implemente la solución.\n\n"
            "QUÉ NO HACER:\n"
            "- No inventes precios, plazos, SLA ni capacidades no documentadas.\n"
            "- No prometas Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, "
            "CRM ni cierre de ventas automático como disponibles hoy.\n"
            "- No rechaces un diagnóstico porque un canal o solución no esté disponible comercialmente.\n"
            "- No respondas con listas de opciones numeradas. Una pregunta por vez.\n"
            "- No expongas códigos técnicos internos (consulting_required, browser_automation_candidate, etc).\n"
            "- No uses lenguaje técnico interno. Usá español claro.\n"
            "- No pidas reformular mensajes cortos. Interpretalos.\n\n"
            "DIAGNÓSTICO FINAL (cuando corresponda):\n"
            "- Resumí lo entendido.\n"
            "- Describí el proceso actual y el problema principal.\n"
            "- Indicá qué automatizar primero y el flujo recomendado.\n"
            "- Mencioná sistemas, datos, riesgos y necesidad de aprobación humana.\n"
            "- Diferenciá: disponible hoy / requiere integración / requiere desarrollo / "
            "requiere consultoría / no recomendado.\n"
            "- Indicá próximo paso concreto.\n"
            "- Si aplica, aclará que la disponibilidad comercial debe confirmarse.\n\n"
            "Respondé siempre en español claro y natural."
        )

    def build_turn_prompt(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        parts = [f"Mensaje actual del usuario: {input.user_message}"]
        if context:
            parts.append("")
            parts.append("Contexto recuperado del knowledge base (como referencia, no es vinculante):")
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
            parts.append(f"\nDatos recopilados hasta ahora: {state.slots}")
        if state.history_summary:
            parts.append(f"\nHistorial de la conversación:\n{state.history_summary}")
        asked = state.asked_questions or []
        if asked:
            parts.append("\nPreguntas que YA hiciste (NO repetir):")
            for i, q in enumerate(asked, 1):
                text = q.get("question_text", "")[:120] or str(q)[:120]
                parts.append(f"  {i}. {text}")

        # Compact semantic memory block
        mem = state.semantic_memory or {}
        mem_lines = []
        if mem.get("business_context"):
            mem_lines.append(f"Contexto del negocio: {mem['business_context'][:120]}")
        if mem.get("channels"):
            mem_lines.append(f"Canales: {', '.join(str(c) for c in mem['channels'])}")
        if mem.get("main_problem"):
            mem_lines.append(f"Problema principal: {mem['main_problem'][:120]}")
        if mem.get("desired_outcome"):
            mem_lines.append(f"Objetivo: {mem['desired_outcome'][:120]}")
        if mem.get("systems_and_data_sources"):
            mem_lines.append(f"Sistemas/fuentes: {', '.join(str(s) for s in mem['systems_and_data_sources'])}")
        if mem.get("human_approval"):
            mem_lines.append(f"Aprobación humana: {mem['human_approval'][:120]}")
        if mem.get("current_process"):
            mem_lines.append(f"Proceso actual: {mem['current_process'][:120]}")
        status = mem.get("diagnosis_status", "gathering")
        mem_lines.append(f"Estado del diagnóstico: {status}")
        if mem.get("contradictions"):
            mem_lines.append(f"Correcciones registradas: {'; '.join(str(c)[:80] for c in mem['contradictions'])}")
        if mem_lines:
            parts.append("\nMemoria semántica acumulada (prevalece sobre historial ambiguo):")
            for line in mem_lines:
                parts.append(f"- {line}")

        parts.append(
            "\nInstrucciones para esta respuesta:\n"
            "- Usá el historial completo y la memoria semántica. No repitas preguntas ni temas ya cubiertos.\n"
            "- Revisá el historial: si ya preguntaste algo y el usuario respondió, "
            "no lo preguntes de nuevo. Avanzá al siguiente tema.\n"
            "- Si el usuario ya dio información, no la pidas de nuevo.\n"
            "- Hacé UNA SOLA pregunta, específica y que realmente falte.\n"
            "- Si el usuario pidió diagnóstico explícitamente, generalo ahora.\n"
            "- Si la memoria semántica indica diagnosis_status=requested o sufficient, "
            "generá el diagnóstico en lugar de seguir preguntando.\n"
            "- Si hay suficiente información, ofrecé generar el diagnóstico.\n"
            "- Respondé en español claro y natural."
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
        # Skip terms that the user brought up in their message
        user_text = (input.user_message or "").lower() if input else ""
        for term in FORBIDDEN_TERMS:
            if term in user_text:
                continue  # User mentioned it, LLM can acknowledge
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
        # In conversation mode, skip pricing terms that the user brought up
        user_text = (input.user_message or "").lower() if input else ""
        pricing_terms = {"plazo", "plazos", "sla"}
        for term in pricing_terms:
            if term in text_lower and term not in user_text:
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
