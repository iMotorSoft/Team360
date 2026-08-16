"""Structured AI interpretation for the email intake boundary."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from jsonschema import ValidationError, validate

from modules.automation_diagnosis.litellm_client import LiteLLMClient
from modules.messaging.domain import InboundMessage

from ..domain.models import CandidateRequest, InitialInterpretation, ReplyInterpretation
from ..domain.routing import CANONICAL_CATEGORIES


DEFAULT_FLOW_MODEL = "openai_gpt-5.4-nano"


class FlowIntakeAIError(RuntimeError):
    """Raised when AI output cannot cross the validated Flow boundary."""


class FlowIntakeInterpreterPort(Protocol):
    def interpret_initial(self, message: InboundMessage) -> InitialInterpretation: ...

    def interpret_reply(
        self,
        message: InboundMessage,
        current_requests: tuple[CandidateRequest, ...],
    ) -> ReplyInterpretation: ...


_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "description",
        "tentative_category",
        "location_text",
        "missing_data",
        "context_notes",
        "confidence",
    ],
    "properties": {
        "description": {"type": "string", "minLength": 1},
        "tentative_category": {"type": ["string", "null"]},
        "location_text": {"type": ["string", "null"]},
        "missing_data": {"type": "array", "items": {"type": "string"}},
        "context_notes": {"type": ["string", "null"]},
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
    },
}

_INITIAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["requests", "clarification_question"],
    "properties": {
        "requests": {"type": "array", "items": _CANDIDATE_SCHEMA},
        "clarification_question": {"type": ["string", "null"]},
    },
}

_REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "requests", "clarification_question"],
    "properties": {
        "action": {
            "enum": ["confirm_all", "correction", "reinterpret", "ambiguous"]
        },
        "requests": {"type": "array", "items": _CANDIDATE_SCHEMA},
        "clarification_question": {"type": ["string", "null"]},
    },
}

_SYSTEM_PROMPT = """
Sos el intérprete de intake municipal de Team360 Flow. Respondé SOLO JSON válido.
No inventes direcciones, hechos, categorías ni confirmaciones. Separá solicitudes
independientes aunque estén en el mismo mensaje. Conservá expresiones contextuales
como "en la misma cuadra" en location_text o context_notes.

Cada solicitud usa exactamente:
{"description": string, "tentative_category": string|null,
 "location_text": string|null, "missing_data": [string],
 "context_notes": string|null, "confidence": number|null}

tentative_category es vocabulario cerrado: debe ser exactamente uno de
__CANONICAL_CATEGORIES__ o null. No escribas categorías
compuestas ni descriptivas (por ejemplo "Alumbrado público - luminaria
apagada"); usá la categoría canónica y poné el detalle en description o
context_notes. Si la solicitud no corresponde a una categoría del catálogo,
usá null.
""".replace("__CANONICAL_CATEGORIES__", json.dumps(list(CANONICAL_CATEGORIES))).strip()


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:])
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    if start < 0:
        raise FlowIntakeAIError("Flow intake AI response did not contain JSON.")
    try:
        value, _end = json.JSONDecoder().raw_decode(cleaned[start:])
    except (json.JSONDecodeError, TypeError) as exc:
        raise FlowIntakeAIError("Flow intake AI returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise FlowIntakeAIError("Flow intake AI JSON must be an object.")
    return value


def _candidate(value: dict[str, Any]) -> CandidateRequest:
    return CandidateRequest(
        description=value["description"].strip(),
        tentative_category=value["tentative_category"],
        location_text=value["location_text"],
        missing_data=tuple(value["missing_data"]),
        context_notes=value["context_notes"],
        confidence=value["confidence"],
    )


class LiteLLMFlowIntakeInterpreter:
    """LiteLLM adapter; Flow depends on this port, never on OpenAI directly."""

    def __init__(self, client: LiteLLMClient | None = None, model: str | None = None) -> None:
        self._client = client
        self.model = (
            model
            or os.environ.get("TEAM360_LITELLM_MODEL_ALIAS")
            or DEFAULT_FLOW_MODEL
        )

    def _complete(self, user_prompt: str, correlation_id: str) -> Any:
        try:
            client = self._client or LiteLLMClient()
            return client.text_completion(
                self.model,
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=1800,
                correlation_id=correlation_id,
                metadata={
                    "feature": "flow_email_intake",
                    "phase": "structured_interpretation",
                    "model_alias": self.model,
                },
            )
        except FlowIntakeAIError:
            raise
        except Exception as exc:
            raise FlowIntakeAIError("LiteLLM Flow intake request failed.") from exc

    def interpret_initial(self, message: InboundMessage) -> InitialInterpretation:
        response = self._complete(
            "Interpretá el primer correo. Devolvé exactamente "
            '{"requests": [...], "clarification_question": string|null}. '
            "Si no hay una solicitud identificable, requests debe quedar vacío y "
            "clarification_question debe pedir el dato mínimo.\n\n"
            f"ASUNTO: {message.subject}\nMENSAJE:\n{message.text_body}",
            message.external_message_id,
        )
        parsed = _extract_json(response.content)
        try:
            validate(instance=parsed, schema=_INITIAL_SCHEMA)
            requests = tuple(_candidate(item) for item in parsed["requests"])
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise FlowIntakeAIError("Flow intake AI initial schema validation failed.") from exc
        return InitialInterpretation(
            requests=requests,
            clarification_question=parsed["clarification_question"],
            provider="litellm",
            model=response.model,
            usage=response.usage,
            latency_ms=response.latency_ms,
        )

    def interpret_reply(
        self,
        message: InboundMessage,
        current_requests: tuple[CandidateRequest, ...],
    ) -> ReplyInterpretation:
        current = json.dumps(
            [request.as_dict() for request in current_requests], ensure_ascii=False
        )
        response = self._complete(
            "Interpretá la respuesta ciudadana usando las solicitudes pendientes. "
            "action debe ser confirm_all solo ante confirmación inequívoca de todas; "
            "correction si corrige datos; reinterpret si agrega información o una nueva "
            "solicitud; ambiguous si no alcanza para decidir. Para correction/reinterpret, "
            "requests debe contener la lista COMPLETA revisada; para las otras acciones, []. "
            "Ejemplos obligatorios: 'Sí', 'Sí, correcto' y 'Los dos' (cuando hay dos) "
            "son confirm_all. 'El primero sí, el árbol está en la cuadra siguiente' es "
            "correction con la lista completa revisada. 'No, es Ciudad de la Paz y Maure' "
            "es correction. No marques ambiguous una afirmación breve e inequívoca. "
            "Devolvé exactamente "
            '{"action":"confirm_all|correction|reinterpret|ambiguous",'
            '"requests":[],"clarification_question":string|null}.\n\n'
            f"SOLICITUDES PENDIENTES:\n{current}\n\nRESPUESTA:\n{message.text_body}",
            message.external_message_id,
        )
        parsed = _extract_json(response.content)
        try:
            validate(instance=parsed, schema=_REPLY_SCHEMA)
            requests = tuple(_candidate(item) for item in parsed["requests"])
            result = ReplyInterpretation(
                action=parsed["action"],
                requests=requests,
                clarification_question=parsed["clarification_question"],
                provider="litellm",
                model=response.model,
                usage=response.usage,
                latency_ms=response.latency_ms,
            )
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise FlowIntakeAIError("Flow intake AI reply schema validation failed.") from exc
        return result
