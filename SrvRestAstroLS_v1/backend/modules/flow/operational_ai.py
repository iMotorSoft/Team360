"""Schema-validated LiteLLM interpretation of correlated operational replies."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from jsonschema import ValidationError, validate

from modules.automation_diagnosis.litellm_client import LiteLLMClient
from modules.messaging.domain import InboundMessage

from .domain import OperationalAction, OperationalInterpretation


DEFAULT_OPERATIONAL_MODEL = "openai_gpt-5.4-nano"


class OperationalAIError(RuntimeError):
    """Raised when AI output cannot cross the operational schema boundary."""


class OperationalInterpreterPort(Protocol):
    def interpret(self, message: InboundMessage) -> OperationalInterpretation: ...


_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "summary"],
    "properties": {
        "action": {"enum": [action.value for action in OperationalAction]},
        "summary": {"type": "string", "minLength": 1, "maxLength": 500},
    },
}

_SYSTEM_PROMPT = """
Sos el clasificador de respuestas operativas internas de Team360 Flow.
El mensaje ya fue correlacionado determinísticamente con una asignación; no
decidas identidad ni routing. Respondé SOLO JSON válido con action y summary.
Clasificá únicamente el texto nuevo del responder e ignorá el correo citado.

ACK_OR_PROGRESS: recepción o trabajo iniciado/en curso, por ejemplo "Recibido,
lo verificamos", "la cuadrilla ya va", "estamos terminando", "ya casi está" o
"creemos que está solucionado". Lenguaje no inequívoco de cierre es progreso.
AMBIGUOUS: no permite afirmar recepción operativa o avance; "Ok" solo es ambiguo.
UNRELATED: el contenido explícitamente no corresponde a la solicitud asignada.
RESOLUTION_PROPOSED: afirma de forma inequívoca que el trabajo fue resuelto,
terminado o reparado, por ejemplo "la luminaria quedó reparada", "trabajo
finalizado" o "problema solucionado". Nunca cierra el caso: solo propone.
UNSUPPORTED_OPERATIONAL_ACTION: acción operativa no soportada distinta de
resolución, por ejemplo delegación o reasignación.
""".strip()


def _parse(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:])
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    if start < 0:
        raise OperationalAIError("Operational AI response did not contain JSON.")
    try:
        value, _end = json.JSONDecoder().raw_decode(cleaned[start:])
    except (json.JSONDecodeError, TypeError) as exc:
        raise OperationalAIError("Operational AI returned invalid JSON.") from exc
    try:
        validate(instance=value, schema=_SCHEMA)
    except ValidationError as exc:
        raise OperationalAIError("Operational AI schema validation failed.") from exc
    return value


class LiteLLMOperationalInterpreter:
    def __init__(self, client: LiteLLMClient | None = None, model: str | None = None) -> None:
        self._client = client
        self.model = (
            model
            or os.environ.get("TEAM360_LITELLM_MODEL_ALIAS")
            or DEFAULT_OPERATIONAL_MODEL
        )

    def interpret(self, message: InboundMessage) -> OperationalInterpretation:
        try:
            client = self._client or LiteLLMClient()
            response = client.text_completion(
                self.model,
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Clasificá esta respuesta operativa correlacionada. "
                            'Devolvé {"action":"...","summary":"..."}.\n\n'
                            f"ASUNTO: {message.subject}\nMENSAJE:\n{message.text_body}"
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=300,
                correlation_id=message.external_message_id,
                metadata={
                    "feature": "flow_operational_reply",
                    "model_alias": self.model,
                },
            )
            parsed = _parse(response.content)
            return OperationalInterpretation(
                action=OperationalAction(parsed["action"]),
                summary=parsed["summary"].strip(),
                provider="litellm",
                model=response.model,
                usage=response.usage,
                latency_ms=response.latency_ms,
            )
        except OperationalAIError:
            raise
        except Exception as exc:
            raise OperationalAIError("LiteLLM operational request failed.") from exc
