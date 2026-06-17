from __future__ import annotations

from typing import Any

from modules.sales_diagnosis_runtime.contracts import (
    DEFAULT_LANGUAGE,
    FORBIDDEN_TERMS,
    PLANNED_EXTENSIONS,
    SAFE_ACK_TEXT,
    safe_ack_for_language,
    SALES_DIAGNOSIS_INSTANCE_CODE,
    AssistantTurnInput,
    ConversationState,
    GuardrailResult,
    RetrievedChunk,
)


_SYSTEM_PROMPTS: dict[str, str] = {
    "es": (
        "Sos Vera, asistente de diagnóstico de automatización de Team360.\n\n"
        "Tu objetivo es mantener una conversación natural para entender el proceso del usuario "
        "y generar un diagnóstico útil al final.\n\n"
        "REGLAS DE CONVERSACIÓN:\n"
        "1. Escuchá, reflejá lo entendido, preguntá una sola cosa por turno.\n"
        "2. Usá TODO el historial disponible. No repitas preguntas ya hechas ni temas ya cubiertos.\n"
        "3. Interpretá mensajes cortos e informales. No pidas reformular.\n"
        "4. Si el usuario menciona un canal (WhatsApp, email, web), diagnosticá el flujo completo.\n"
        "5. Inferí contexto. Ej: 'vendo repuestos' + 'whatsapp' = consultas de producto.\n"
        "6. Hacé UNA SOLA pregunta principal por turno.\n"
        "7. Cada respuesta debe aportar valor: reflejar comprensión, organizar, detectar riesgo.\n"
        "8. Evitá lenguaje de promesa absoluta. Hablá de factibilidad y supuestos.\n"
        "9. Cuando el usuario pida diagnóstico explícitamente, generalo con la info disponible.\n\n"
        "ESTRUCTURA DE LA CONVERSACIÓN:\n"
        "- Turno 1-2: entender problema, canal y objetivo.\n"
        "- Turno 2-4: sistemas, datos, volumen, reglas y aprobación humana.\n"
        "- Turno 3-5: preguntar lo estrictamente faltante.\n"
        "- Cuando el usuario lo pida o haya base suficiente: diagnóstico final.\n\n"
        "REGLAS DE DIAGNÓSTICO:\n"
        "- Cuando el runtime indique DIAGNÓSTICO, NO hagas preguntas.\n"
        "- Detalles de implementación (descuentos, umbrales, horarios) = PUNTOS A VALIDAR.\n"
        "- 'Automatizable' no significa 'vendible hoy'.\n"
        "- Distinguí: factibilidad técnica ≠ disponibilidad comercial.\n\n"
        "QUÉ NO HACER:\n"
        "- No inventes precios, plazos, SLA ni capacidades no documentadas.\n"
        "- No prometas Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM.\n"
        "- No expongas códigos técnicos internos.\n"
        "- No uses lenguaje técnico. Usá lenguaje claro.\n\n"
        "DIAGNÓSTICO FINAL:\n"
        "- Resumí lo entendido. Describí proceso y problema.\n"
        "- Indicá qué automatizar primero. Mencioná sistemas, riesgos, aprobación humana.\n"
        "- Diferenciá: disponible hoy / requiere integración / requiere desarrollo.\n"
        "- Indicá próximo paso concreto.\n\n"
        "Respondé siempre en español claro y natural."
    ),
    "en": (
        "You are Vera, an automation diagnosis assistant for Team360.\n\n"
        "Your goal is to have a natural conversation to understand the user's process "
        "and generate a useful diagnosis at the end.\n\n"
        "CONVERSATION RULES:\n"
        "1. Listen, reflect understanding, ask ONE question per turn.\n"
        "2. Use ALL available history. Do not repeat already-asked questions.\n"
        "3. Interpret short and informal messages. Do not ask for reformulation.\n"
        "4. If the user mentions a channel (WhatsApp, email, web), diagnose the full flow.\n"
        "5. Infer context from earlier messages.\n"
        "6. Ask ONE main question per turn, specific and advancing the diagnosis.\n"
        "7. Each response must add value: reflect understanding, organize, detect risk.\n"
        "8. Avoid absolute promises. Talk about feasibility and assumptions.\n"
        "9. When the user explicitly asks for a diagnosis, generate it with available info.\n\n"
        "CONVERSATION STRUCTURE:\n"
        "- Turns 1-2: understand the problem, channel and objective.\n"
        "- Turns 2-4: dive into systems, data, volume, rules and human approval.\n"
        "- Turns 3-5: ask only what is strictly needed.\n"
        "- When the user requests or there is enough info: final diagnosis.\n\n"
        "DIAGNOSIS RULES:\n"
        "- When the runtime says DIAGNOSIS, do NOT ask questions.\n"
        "- Implementation details (discount rules, thresholds, schedules) = POINTS TO VALIDATE.\n"
        "- 'Automatable' does not mean 'sellable today'.\n"
        "- Distinguish: technical feasibility ≠ commercial availability.\n\n"
        "DO NOT:\n"
        "- Invent prices, SLAs or undocumented features.\n"
        "- Promise Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM.\n"
        "- Expose technical internal codes.\n"
        "- Use technical jargon. Use clear language.\n\n"
        "FINAL DIAGNOSIS:\n"
        "- Summarize understanding. Describe process and problem.\n"
        "- Indicate what to automate first. Mention systems, risks, human approval.\n"
        "- Differentiate: available today / requires integration / requires development.\n"
        "- Indicate concrete next step.\n\n"
        "Always respond in English, clear and natural."
    ),
    "he": (
        "את ורה, עוזרת אבחון אוטומציה של Team360.\n\n"
        "המטרה שלך היא לנהל שיחה טבעית כדי להבין את התהליך של המשתמש "
        "וליצור אבחון שימושי בסוף.\n\n"
        "כללי שיחה:\n"
        "1. הקשיבי, שקפי הבנה, שאלי שאלה אחת בכל תור.\n"
        "2. השתמשי בכל ההיסטוריה הזמינה. אל תחזרי על שאלות.\n"
        "3. פרשי הודעות קצרות ובלתי פורמליות. אל תבקשי ניסוח מחדש.\n"
        "4. אם המשתמש מזכיר ערוץ (וואטסאפ, אימייל, אתר), אבחני את הזרימה המלאה.\n"
        "5. הסיקי הקשר מהודעות קודמות.\n"
        "6. שאלי שאלה עיקרית אחת בכל תור.\n"
        "7. כל תגובה צריכה להוסיף ערך: שיקוף הבנה, ארגון, זיהוי סיכון.\n"
        "8. הימנעי מהבטחות מוחלטות. דברי על היתכנות והנחות.\n"
        "9. כשהמשתמש מבקש אבחון במפורש, צרי אותו עם המידע הזמין.\n\n"
        "מבנה שיחה:\n"
        "- שלבים 1-2: הבנת הבעיה, הערוץ והיעד.\n"
        "- שלבים 2-4: מערכות, נתונים, נפח, כללים ואישור אנושי.\n"
        "- שלבים 3-5: שאלי רק את ההכרחי.\n"
        "- כשהמשתמש מבקש או כשיש מספיק מידע: אבחון סופי.\n\n"
        "כללי אבחון:\n"
        "- כשהריצה אומרת אבחון, אל תשאלי שאלות.\n"
        "- פרטי יישום (כללי הנחה, ספים, לוחות זמנים) = נקודות לאימות.\n"
        "- 'ניתן לאוטומציה' לא אומר 'ניתן למכירה היום'.\n"
        "- הבדילי: היתכנות טכנית ≠ זמינות מסחרית.\n\n"
        "אל תעשי:\n"
        "- אל תמציאי מחירים, SLAs או יכולות לא מתועדות.\n"
        "- אל תבטיחי Step-to-Action, lead_capture, diagnostic_code, WhatsApp handoff, CRM.\n"
        "- אל תחשיפי קודים טכניים פנימיים.\n"
        "- אל תשתמשי בז'רגון טכני. השתמשי בשפה ברורה.\n\n"
        "אבחון סופי:\n"
        "- סכמי את ההבנה. תארי תהליך ובעיה.\n"
        "- צייני מה לעשות אוטומציה קודם. הזכירי מערכות, סיכונים, אישור אנושי.\n"
        "- הבדילי: זמין היום / דורש אינטגרציה / דורש פיתוח.\n"
        "- צייני צעד קונקרטי הבא.\n\n"
        "הגיבי תמיד בעברית, ברור וטבעי."
    ),
}


class PromptPolicy:
    def build_system_prompt(
        self,
        assistant_instance_code: str = "",
        package_code: str = "",
        response_language: str = "",
    ) -> str:
        lang = response_language or DEFAULT_LANGUAGE
        return _SYSTEM_PROMPTS.get(lang, _SYSTEM_PROMPTS[DEFAULT_LANGUAGE])

    def build_turn_prompt(
        self,
        input: AssistantTurnInput,
        state: ConversationState,
        context: list[RetrievedChunk],
    ) -> str:
        mem = state.semantic_memory or {}
        lang_info = mem.get("language", {})
        response_lang = lang_info.get("preferred_response_language", DEFAULT_LANGUAGE)

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

        parts.append(f"\nIdioma de respuesta: {response_lang}")

        status = mem.get("diagnosis_status", "gathering")
        is_diagnose = status in ("requested", "sufficient", "completed")
        if is_diagnose:
            parts.append(
                "\nInstrucciones para esta respuesta (ACCIÓN: DIAGNÓSTICO):\n"
                "- NO hagas preguntas. El usuario ya proporcionó información suficiente.\n"
                "- Generá el diagnóstico completo ahora.\n"
                "- Si falta un detalle de implementación (regla exacta de descuento, umbral, horario), "
                "incluilo como PUNTO A VALIDAR, no preguntes por él.\n"
                "- El diagnóstico debe incluir: qué entendiste, factibilidad inicial, "
                "canales y sistemas, nivel de automatización, excepciones con revisión humana, "
                "riesgos, supuestos y próximo paso concreto.\n"
                f"- {LANGUAGE_INSTRUCTIONS.get(response_lang, f'Respond only in {response_lang}.')}"
            )
        else:
            parts.append(
                "\nInstrucciones para esta respuesta (ACCIÓN: SEGUIR PREGUNTANDO):\n"
                "- Usá el historial completo y la memoria semántica. No repitas preguntas ni temas ya cubiertos.\n"
                "- Revisá el historial: si ya preguntaste algo y el usuario respondió, "
                "no lo preguntes de nuevo.\n"
                "- Hacé UNA SOLA pregunta, específica y que realmente falte.\n"
                "- No preguntes por detalles de implementación (reglas exactas, umbrales, formatos). "
                "Esos se definen después del diagnóstico.\n"
                "- Si falta un dato y el usuario preguntó por diagnóstico, "
                "explicá brevemente por qué necesitás ese dato.\n"
                f"- {LANGUAGE_INSTRUCTIONS.get(response_lang, f'Respond only in {response_lang}.')}"
            )
        return "\n".join(parts)

    def build_safe_ack(
        self,
        assistant_instance_code: str = "",
        package_code: str = "",
        domain: str = "",
        response_language: str = "",
    ) -> str:
        lang = response_language or DEFAULT_LANGUAGE
        if domain == "commercial":
            ack = {
                "es": "Gracias por tu consulta. Estoy revisando la información disponible.",
                "en": "Thank you for your inquiry. I am reviewing the available information.",
                "he": "תודה על פנייתך. אני בודק את המידע הזמין.",
            }
            return ack.get(lang, ack[DEFAULT_LANGUAGE])
        if domain == "technical":
            ack = {
                "es": "Recibí el diagnóstico. Estoy buscando información relevante.",
                "en": "Diagnosis received. I am looking for relevant information.",
                "he": "האבחון התקבל. אני מחפש מידע רלוונטי.",
            }
            return ack.get(lang, ack[DEFAULT_LANGUAGE])
        return safe_ack_for_language(lang)


LANGUAGE_INSTRUCTIONS: dict[str, str] = {
    "es": "Respondé únicamente en español.",
    "en": "Respond only in English.",
    "he": "הגיבי רק בעברית.",
}


class GuardrailPolicy:
    """Evaluates assistant responses against commercial safety rules."""

    DECLINE_PATTERNS = frozenset({
        "no está disponible", "no está list", "todavía no", "capacidad futura",
        "extensión futura", "no ofrecemos", "no incluimos", "no contamos",
        "no tenemos información", "no documentado", "no define", "no fija",
        "no informa", "no cubre", "consultá con nuestro equipo",
        "no debe venderse como listo", "no debe venderse como lista",
        "no prometo", "no prometemos", "no promete", "no garantiza",
        "no garantizamos", "no asumimos", "sin prometer", "sin vender",
        "no vender", "preliminar", "validación adicional", "validacion adicional",
        "caso por caso", "no siempre", "no conviene automatizar",
        "depende del alcance", "depende del acuerdo", "según el alcance",
        "segun el alcance", "debe pactarse", "puede quedar bloqueado",
        "requiere aprobación humana", "requiere aprobacion humana",
    })

    CAPABILITY_PATTERNS: dict[str, tuple[str, ...]] = {
        "step_to_action": ("step-to-action", "steptoaction"),
        "lead_capture": ("lead capture", "lead_capture"),
        "diagnostic_code": ("diagnostic code", "diagnostic_code", "código de diagnóstico"),
        "whatsapp_handoff": ("whatsapp handoff", "whatsapp_handoff", "handoff por whatsapp", "traspaso a whatsapp"),
        "crm": ("integración con crm", "integracion con crm", "crm integrado", "crm lista", "crm listo", "crm operativo", "crm disponible", "customer relationship management"),
        "auto_billing": ("cierre de ventas automático", "facturación automática", "auto billing", "autobilling"),
    }

    def evaluate_response(self, response_text: str, input: AssistantTurnInput | None = None, state: ConversationState | None = None) -> GuardrailResult:
        result = GuardrailResult(passed=True)
        text_lower = response_text.lower()
        if not response_text.strip():
            result.empty_response = True
            result.passed = False
            result.notes.append("response_empty")
            return result

        user_text = (input.user_message or "").lower() if input else ""
        for term in FORBIDDEN_TERMS:
            if term in user_text:
                continue
            if term in text_lower:
                has_negation = self._has_near_negation(text_lower, term)
                if not has_negation:
                    result.forbidden_claims.append(term)
                    result.notes.append(f"forbidden_term_found:{term}")

        for cap, patterns in self.CAPABILITY_PATTERNS.items():
            if any(p in text_lower for p in patterns):
                if not self._has_decline(text_lower):
                    result.planned_extension_misrepresented = True
                    result.notes.append(f"planned_extension_misrepresented:{cap}")

        pricing_terms = {"plazo", "plazos", "sla"}
        for term in pricing_terms:
            if term in text_lower and term not in user_text:
                if not self._has_decline(text_lower):
                    result.pricing_sla_hallucination = True
                    result.notes.append(f"unsupported_{term}_claim")

        question_count = text_lower.count("?")
        if question_count > 3:
            result.max_questions_exceeded = True
            result.notes.append(f"max_questions_exceeded:{question_count}")

        if result.forbidden_claims or result.planned_extension_misrepresented:
            result.passed = False
        if result.pricing_sla_hallucination:
            result.passed = False

        return result

    def build_fallback_response(self, reason: str = "", input: AssistantTurnInput | None = None, state: ConversationState | None = None) -> str:
        if result := self._build_contextual_fallback(reason, input, state):
            return result
        if "guardrail" in reason or "unsafe" in reason:
            return "No puedo proporcionar esa información porque excede los límites de lo que puedo confirmar. Consultá con nuestro equipo comercial."
        return "Ocurrió un error al procesar tu consulta. Por favor intentá de nuevo o escribinos directamente."

    def _build_contextual_fallback(self, reason: str, input: AssistantTurnInput | None, state: ConversationState | None) -> str | None:
        if not input or not input.user_message:
            return None
        if "precio" in reason or "sla" in reason or "pricing" in reason:
            return "Entiendo tu consulta sobre costos o plazos. No tengo información de precios ni SLA en mi base de conocimiento. Por favor consultá con nuestro equipo comercial."
        if "planned_extension" in reason:
            cap = reason.split(":")[-1] if ":" in reason else ""
            cap_label = cap.replace("_", " ") if cap else "esa capacidad"
            return f"Entiendo tu interés en {cap_label}. Según la documentación disponible, {cap_label} aparece como extensión planificada y no está disponible actualmente."
        return None

    @staticmethod
    def _has_decline(text: str) -> bool:
        return any(p in text for p in GuardrailPolicy.DECLINE_PATTERNS)

    @staticmethod
    def _has_near_negation(text: str, term: str, window: int = 60) -> bool:
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

    @staticmethod
    def _capability_ready(text: str, patterns: tuple[str, ...]) -> bool:
        text_lower = text.lower()
        if not any(p in text_lower for p in patterns):
            return False
        return not GuardrailPolicy._has_decline(text_lower)

    @classmethod
    def is_step_to_action_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(response_text, cls.CAPABILITY_PATTERNS["step_to_action"])

    @classmethod
    def is_lead_capture_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(response_text, cls.CAPABILITY_PATTERNS["lead_capture"])

    @classmethod
    def is_diagnostic_code_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(response_text, cls.CAPABILITY_PATTERNS["diagnostic_code"])

    @classmethod
    def is_whatsapp_handoff_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(response_text, cls.CAPABILITY_PATTERNS["whatsapp_handoff"])

    @classmethod
    def is_crm_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(response_text, cls.CAPABILITY_PATTERNS["crm"])

    @classmethod
    def is_auto_billing_ready(cls, response_text: str) -> bool:
        return cls._capability_ready(response_text, cls.CAPABILITY_PATTERNS["auto_billing"])
