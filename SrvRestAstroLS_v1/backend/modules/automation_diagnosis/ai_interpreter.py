"""AI interpretation adapters.

LiteLLM is the real Phase 1 path. Mock/Noop exist only for tests and fallback.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from .answer_collector import answers_as_text
from .litellm_client import LiteLLMClient
from .retrieval import retrieved_context_as_prompt
from .schemas import AIInterpretation, DiagnosisSession, RetrievedContext


DEFAULT_TEXT_MODEL = "automation_diagnosis_text"


class AIInterpreterPort(Protocol):
    def interpret(self, session: DiagnosisSession, context: RetrievedContext) -> AIInterpretation:
        ...


# @lat: [[ai-litellm#AI LiteLLM#Decision Boundary]]
SYSTEM_PROMPT = """
Sos el interprete tecnico-comercial de Team360 para diagnosticar automatizaciones.
Devolve SOLO JSON valido, sin markdown.

Reglas:
- No clasifiques como decision final. Team360 decide con scoring deterministico.
- No prometas bypass de MFA, anti-bot, hardware keys, biometria o firma fuerte.
- Identifica sistemas, riesgos, necesidad de aprobacion humana, credenciales y workers probables.
- Usa el contexto RAG solo como apoyo, no inventes datos.

Formato:
{
  "summary": "string",
  "signals": {
    "process": "string",
    "business_pain": "string",
    "systems": ["string"],
    "mfa_or_security": ["string"],
    "data_sensitivity": ["string"],
    "rules_clarity": "clear|partially_clear|mostly_manual|unknown",
    "human_dependency": "low|medium|high|expert_judgement",
    "economic_impact": "low|medium|high|critical",
    "possible_workers": ["string"],
    "knowledge_need": "none|rag|graphrag|hybrid"
  },
  "risks": ["string"],
  "visible_summary_draft": "string",
  "internal_notes": "string"
}
"""


def _extract_first_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:])
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("AI response did not contain JSON")
    decoder = json.JSONDecoder()
    obj, _end = decoder.raw_decode(cleaned[start:])
    return obj


def _fallback_systems_from_text(text: str) -> list[str]:
    known = ["sap", "sap b1", "erp", "excel", "whatsapp", "email", "portal", "browser", "desktop", "api"]
    lowered = text.lower()
    return [item for item in known if re.search(rf"\b{re.escape(item)}\b", lowered)]


class LiteLLMAIInterpreter:
    # @lat: [[ai-litellm#AI LiteLLM#Adapter Rule]]
    def __init__(self, client: LiteLLMClient | None = None, model: str | None = None) -> None:
        self.client = client
        self.model = model or os.environ.get("TEAM360_AUTOMATION_DIAGNOSIS_TEXT_MODEL", DEFAULT_TEXT_MODEL)

    def interpret(self, session: DiagnosisSession, context: RetrievedContext) -> AIInterpretation:
        client = self.client or LiteLLMClient()
        answers_text = answers_as_text(session.answers)
        context_text = retrieved_context_as_prompt(context)
        user_prompt = f"""
Contexto RAG:
{context_text or "(sin contexto recuperado)"}

Respuestas del diagnostico:
{answers_text}

Genera interpretacion estructurada para Team360.
"""
        response = client.chat_completion(
            self.model,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            correlation_id=session.correlation_id,
        )
        parsed = _extract_first_json_object(response.content)
        return AIInterpretation(
            provider="litellm",
            model=response.model,
            summary=str(parsed.get("summary") or ""),
            signals=dict(parsed.get("signals") or {}),
            risks=[str(item) for item in parsed.get("risks") or []],
            usage=response.usage,
            latency_ms=response.latency_ms,
            raw={"parsed": parsed},
        )


class MockAIInterpreter:
    def interpret(self, session: DiagnosisSession, context: RetrievedContext) -> AIInterpretation:
        text = answers_as_text(session.answers)
        return AIInterpretation(
            provider="mock",
            model="mock_automation_diagnosis",
            summary="Interpretacion mock: proceso candidato a automatizacion con validacion operativa.",
            signals={
                "systems": _fallback_systems_from_text(text),
                "rules_clarity": "partially_clear" if "partially_clear" in text else "unknown",
                "human_dependency": "medium",
                "possible_workers": ["diagnosis_ai_interpreter", "workflow_classifier"],
                "knowledge_need": "rag" if context.chunks else "none",
            },
            risks=[],
            raw={"retrieved_chunk_count": len(context.chunks)},
        )


class NoopAIInterpreter:
    def interpret(self, session: DiagnosisSession, context: RetrievedContext) -> AIInterpretation:
        return AIInterpretation(
            provider="none",
            model="none",
            summary="AI disabled. Deterministic scoring only.",
            signals={},
            risks=[],
        )


def build_ai_interpreter(provider: str | None = None) -> AIInterpreterPort:
    selected = (provider or os.environ.get("TEAM360_AI_PROVIDER", "litellm")).strip().lower()
    if selected == "litellm":
        return LiteLLMAIInterpreter()
    if selected == "mock":
        return MockAIInterpreter()
    if selected == "none":
        return NoopAIInterpreter()
    raise ValueError(f"Unsupported TEAM360_AI_PROVIDER: {selected}")
