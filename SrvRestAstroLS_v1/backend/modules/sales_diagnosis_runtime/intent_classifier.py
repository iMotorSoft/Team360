from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from modules.automation_diagnosis.litellm_client import LiteLLMClient


class IntentType(str, Enum):
    PROVIDE_INFORMATION = "provide_information"
    REQUEST_DIAGNOSIS = "request_diagnosis"
    ASK_POINT_QUESTION = "ask_point_question"
    CORRECT_PREVIOUS_INFORMATION = "correct_previous_information"
    STOP_INTERVIEW = "stop_interview"
    UNCLEAR = "unclear"


class IntentScope(str, Enum):
    GLOBAL = "global"
    POINT_QUESTION = "point_question"
    NOT_APPLICABLE = "not_applicable"


class IntentSource(str, Enum):
    HIGH_CONFIDENCE_RULE = "high_confidence_rule"
    AI_CLASSIFIER = "ai_classifier"
    RUNTIME_FALLBACK = "runtime_fallback"


CLASSIFIER_CONFIDENCE_STRONG = 0.85
CLASSIFIER_CONFIDENCE_MODERATE = 0.60


@dataclass
class IntentClassification:
    intent: IntentType = IntentType.UNCLEAR
    scope: IntentScope = IntentScope.NOT_APPLICABLE
    confidence: float = 0.0
    source: IntentSource = IntentSource.RUNTIME_FALLBACK
    matched_rule: str | None = None
    language: str = "es"


@dataclass
class IntentStateSummary:
    diagnosis_status: str = "gathering"
    has_process: bool = False
    has_channels: bool = False
    has_systems: bool = False
    has_human_approval: bool = False
    has_volume: bool = False
    turn_count: int = 0
    last_question_intent: str = ""
    current_language: str = "es"


# ---------------------------------------------------------------------------
# High-confidence rules
# ---------------------------------------------------------------------------

HIGH_CONFIDENCE_RULES: list[dict[str, Any]] = [
    # --- Spanish: provide_information (expressions of automation intent) ---
    {"id": "provide_info_es_a01", "intent": IntentType.PROVIDE_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"^(quiero|necesito|buscamos|necesitamos)\s+(automatizar|mejorar|optimizar|agilizar|digitalizar|ordenar|simplificar)", re.IGNORECASE)},
    {"id": "provide_info_es_a02", "intent": IntentType.PROVIDE_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"^(queremos|debemos|vamos\s+a)\s+(automatizar|mejorar|optimizar|agilizar|digitalizar|ordenar|simplificar)", re.IGNORECASE)},
    # "No quiero responder ese mensaje" = provide_information (policy opinion), NOT stop_interview
    {"id": "provide_info_es_nr01", "intent": IntentType.PROVIDE_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"\bno\s+quier[oó]\s+responder\s+ese\s+mensaje\b", re.IGNORECASE)},
    # --- English: provide_information ---
    {"id": "provide_info_en_a01", "intent": IntentType.PROVIDE_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"^(i\s+)?(want\s+to|need\s+to|we\s+want\s+to|we\s+need\s+to|we\'re\s+looking\s+to)\s+(automate|improve|optimize|digitize|organize|simplify)", re.IGNORECASE)},
    {"id": "provide_info_en_nr01", "intent": IntentType.PROVIDE_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"\b(i\s+)?don\s*\'*t\s+want\s+to\s+respond\s+that\s+message\b", re.IGNORECASE)},
    # --- Hebrew: provide_information ---
    {"id": "provide_info_he_a01", "intent": IntentType.PROVIDE_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"^(אני\s+)?(רוצה|צריך|צריכה|מחפש|מחפשת)\s+(לבצע\s+)?(אוטומציה|לייעל|לשפר|לארגן|לפשט)", re.IGNORECASE)},
    # --- Spanish: request_diagnosis global ---
    {"id": "request_diagnosis_es_01", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bdame\s*((el|un)\s*)?diagn[oó]stico\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_01b", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bdame\s*(el\s*)?informe\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_01c", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bdame\s*((la|una)\s*)?conclusi[oó]n\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_01d", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\b(res[uú]m[íi]me|resum[íi])\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_01e", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bmostrame\s*(el\s*)?resultado\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_01f", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bqu[eé]\s*conclusi[oó]n\s*(ten[eé]s|sac[aá]s)\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_01g", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bya\s*(con\s*esto|con\s*lo\s*que\s*hay)\s*qu[eé]\s*(me\s*)?dec[íi]s\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_02", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bdame\s*una\s*orientaci[oó]n\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_03", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bcerr[aá]\s*(con\s*(una\s*)?)?recomendaci[oó]n\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_04", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bqu[eé]\s*(har[ií]as|conviene)\s*(primero|con\s*todo\s*esto)\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_04b", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bqu[eé]\s*(me\s+)?recomiend[aeá]s?\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_04c", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bqu[eé]\s*(me\s+)?recomend[áa]s\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_04d", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\borient[aeá]me\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_05", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\b(con\s*esto|con\s*lo\s*que\s*te\s*dije)\s*(ya\s*)?(est[aá]|alcanza|dame|quiero|empecemos)\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_06", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bpod[ée]s\s*decirme\s*si\s*se\s*puede\b", re.IGNORECASE)},
    {"id": "request_diagnosis_es_07", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bpod[ée]s\s*decirme\s*qu[eé]\s*har[ií]as\b", re.IGNORECASE)},
    # --- Spanish: stop_interview ---
    {"id": "stop_interview_es_01", "intent": IntentType.STOP_INTERVIEW, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bno\s*quier[oó]\s*(seguir\s*respondiendo|continuar|contestar\s*m[aá]s)\b", re.IGNORECASE)},
    # --- Spanish: correction ---
    {"id": "correct_es_01", "intent": IntentType.CORRECT_PREVIOUS_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"\b(mejor\s*dicho|rectifico|rectificamos)\b", re.IGNORECASE)},
    # --- English: request_diagnosis global ---
    {"id": "request_diagnosis_en_01", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bgive\s+me\s+(a|an)\s+(diagnosis|assessment|recommendation|report|summary)\b", re.IGNORECASE)},
    {"id": "request_diagnosis_en_01b", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bwhat\s+would\s+you\s+do\b", re.IGNORECASE)},
    {"id": "request_diagnosis_en_02", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\btell\s+me\s+(if|whether)\s+(this\s+)?(can\s+be\s+automated|i\s+should\s+automate)\b", re.IGNORECASE)},
    {"id": "request_diagnosis_en_03", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bis\s+this\s+(enough|sufficient)\b", re.IGNORECASE)},
    {"id": "request_diagnosis_en_04", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\btell\s+me\s+what\s+(you\s+)?would\s+do\b", re.IGNORECASE)},
    {"id": "request_diagnosis_en_05", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\btell\s+me\s+what\s+to\s+do\s+first\b", re.IGNORECASE)},
    {"id": "request_diagnosis_en_06", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bcan\s+you\s+(assess|tell\s+me|evaluate|summarize|give\s+me\s+a\s+conclusion)\b", re.IGNORECASE)},
    # --- English: stop_interview ---
    {"id": "stop_interview_en_01", "intent": IntentType.STOP_INTERVIEW, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\b(i\s*don\s*'?t\s*want\s*to\s*(continue|answer\s*(more|anymore)))\b", re.IGNORECASE)},
    # --- English: correction ---
    {"id": "correct_en_01", "intent": IntentType.CORRECT_PREVIOUS_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"\b(actually\s+i\s+meant|i\s+mean\s+actually|let\s+me\s+correct)\b", re.IGNORECASE)},
    {"id": "correct_en_02", "intent": IntentType.CORRECT_PREVIOUS_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"\bcorrection\b", re.IGNORECASE)},
    # --- Hebrew: request_diagnosis ---
    {"id": "request_diagnosis_he_01", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\b(תן\s*לי|תני\s*לי)\s*(אבחון|הערכה|המלצה)\b", re.IGNORECASE)},
    {"id": "request_diagnosis_he_02", "intent": IntentType.REQUEST_DIAGNOSIS, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\bמה\s*אתה\s*ממליץ\b", re.IGNORECASE)},
    # --- Hebrew: stop_interview ---
    {"id": "stop_interview_he_01", "intent": IntentType.STOP_INTERVIEW, "scope": IntentScope.GLOBAL,
     "pattern": re.compile(r"\b(אני\s*לא\s*רוצה\s*להמשיך|אני\s*לא\s*רוצה\s*לענות\s*יותר)\b", re.IGNORECASE)},
    # --- Hebrew: correction ---
    {"id": "correct_he_01", "intent": IntentType.CORRECT_PREVIOUS_INFORMATION, "scope": IntentScope.NOT_APPLICABLE,
     "pattern": re.compile(r"\b(בעצם|סליחה\s*,?\s*אני\s*מתקן|אני\s*מתקן)\b", re.IGNORECASE)},
]


def match_high_confidence(message: str) -> IntentClassification | None:
    for rule in HIGH_CONFIDENCE_RULES:
        if rule["pattern"].search(message):
            return IntentClassification(
                intent=rule["intent"],
                scope=rule["scope"],
                confidence=1.0,
                source=IntentSource.HIGH_CONFIDENCE_RULE,
                matched_rule=rule["id"],
            )
    return None


# ---------------------------------------------------------------------------
# Factual answer detection (short factual responses that don't need AI)
# ---------------------------------------------------------------------------

FACTUAL_NUMBERS = re.compile(r"^\s*(\d+[\.\d]*(\s*-\s*\d+)?\s*(por\s*(d[ií]a|semana|mes|hora|d[íi]a))?\s*)[\.!¡¿?;]*\s*$", re.IGNORECASE)
FACTUAL_AFFIRMATIVE_SHORT = re.compile(r"^\s*(s[ií]|no|yes|ok|dale|sale|bueno|claro|listo|hecho|de\s*acuerdo|okey|okay|d[\'´]acord)[\.!\?]*\s*$", re.IGNORECASE)
FACTUAL_CHANNEL_SINGLE = re.compile(r"^\s*(whatsapp|gmail|email|correo|web|chat|tel[eé]fono|telefono|app|portal|presencial|local|instagram|facebook|redes)[\.!\?]*\s*$", re.IGNORECASE)
FACTUAL_SYSTEM_SINGLE = re.compile(r"^\s*(sistema|planilla|excel|sheet|programa|software|erp|crm|app|aplicaci[oó]n|base\s+de\s+datos|bd)[\.!\?]*\s*$", re.IGNORECASE)


def is_clear_factual_answer(message: str) -> bool:
    msg = message.strip()
    if not msg:
        return False
    if FACTUAL_NUMBERS.match(msg):
        return True
    if FACTUAL_AFFIRMATIVE_SHORT.match(msg):
        return True
    if FACTUAL_CHANNEL_SINGLE.match(msg):
        return True
    if FACTUAL_SYSTEM_SINGLE.match(msg):
        return True
    return False


# ---------------------------------------------------------------------------
# LiteLLM Intent Classifier
# ---------------------------------------------------------------------------

CLASSIFIER_SYSTEM_PROMPT = (
    "You classify user messages in a business automation conversation. "
    "Respond only with valid JSON. No explanation.\n\n"
    "Intents:\n"
    "- provide_information: user gives facts (channels, volume, systems, approvals, expresses an "
    "automation objective or describes their process). This is the default for statements about what they do.\n"
    "- request_diagnosis: user explicitly asks for a global assessment, recommendation, next steps, "
    "or evaluation of their situation. The user is asking YOU to evaluate or decide.\n"
    "- ask_point_question: user asks a specific question about one feature, tool, or capability. "
    "A yes/no question about a single integration or feature.\n"
    "- correct_previous_information: user contradicts a specific fact they stated earlier with new data. "
    "Requires a concrete correction (e.g. 'not 80, it is 120', 'we use Outlook not Gmail'). "
    "NOT for vague mentions of 'incomplete' or 'wrong'. NOT for providing new information.\n"
    "- stop_interview: user wants to end the conversation entirely and get a final answer.\n"
    "- unclear: ambiguous, greeting, or cannot determine.\n\n"
    "CRITICAL DISTINCTIONS:\n"
    "- 'I want to automate...' / 'We need to improve...' = provide_information (expressing an objective)\n"
    "- 'Can you tell me if I should automate...?' / 'What would you do?' = request_diagnosis (asking for evaluation)\n"
    "- 'No, I don't want to handle that message automatically' = provide_information (policy opinion)\n"
    "- 'I don't want to continue answering questions' = stop_interview (stop the conversation)\n\n"
    "Scopes:\n"
    "- global: refers to the entire process\n"
    "- point_question: refers to a single concept, integration, or feature\n"
    "- not_applicable: for corrections, information provision, or unclear\n\n"
    "Output format:\n"
    '{"intent": "...", "scope": "...", "confidence": 0.0-1.0}'
)


def _build_classifier_user(message: str, summary: IntentStateSummary) -> str:
    return (
        f"Message: {message}\n"
        f"Language: {summary.current_language}\n"
        f"Diagnosis status: {summary.diagnosis_status}\n"
        f"Coverage: process={summary.has_process} channels={summary.has_channels} "
        f"systems={summary.has_systems} approval={summary.has_human_approval} volume={summary.has_volume}\n"
        f"Turn: {summary.turn_count}\n"
        f"Last question intent: {summary.last_question_intent or 'none'}"
    )


def parse_classifier_response(raw: str) -> IntentClassification:
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return IntentClassification(source=IntentSource.RUNTIME_FALLBACK)

    intent_str = (data.get("intent") or "").strip()
    scope_str = (data.get("scope") or "").strip()
    confidence = float(data.get("confidence", 0.0))

    try:
        intent = IntentType(intent_str)
    except (ValueError, TypeError):
        intent = IntentType.UNCLEAR

    try:
        scope = IntentScope(scope_str)
    except (ValueError, TypeError):
        scope = IntentScope.NOT_APPLICABLE

    return IntentClassification(
        intent=intent,
        scope=scope,
        confidence=min(max(confidence, 0.0), 1.0),
        source=IntentSource.AI_CLASSIFIER,
    )


# ---------------------------------------------------------------------------
# Provider protocol + LiteLLM implementation
# ---------------------------------------------------------------------------


class IntentClassifier(Protocol):
    def classify(
        self,
        message: str,
        state_summary: IntentStateSummary,
    ) -> IntentClassification:
        ...


class LiteLLMIntentClassifier:
    def __init__(self, base_url: str | None = None, model: str = "openai_gpt-5-nano") -> None:
        self._client = LiteLLMClient(base_url=base_url)
        self._model = model

    def classify(
        self,
        message: str,
        state_summary: IntentStateSummary,
    ) -> IntentClassification:
        fast = match_high_confidence(message)
        if fast is not None:
            return fast

        if is_clear_factual_answer(message):
            return IntentClassification(
                intent=IntentType.PROVIDE_INFORMATION,
                scope=IntentScope.NOT_APPLICABLE,
                confidence=0.95,
                source=IntentSource.HIGH_CONFIDENCE_RULE,
                matched_rule="factual_answer",
            )

        user = _build_classifier_user(message, state_summary)
        try:
            resp = self._client.chat_completion(
                self._model,
                [
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
                max_tokens=60,
            )
            return parse_classifier_response(resp.content)
        except Exception:
            return IntentClassification(source=IntentSource.RUNTIME_FALLBACK)


class NullIntentClassifier:
    def classify(
        self,
        message: str,
        state_summary: IntentStateSummary,
    ) -> IntentClassification:
        return IntentClassification(source=IntentSource.RUNTIME_FALLBACK)
