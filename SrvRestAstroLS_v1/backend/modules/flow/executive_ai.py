"""Conservative LiteLLM executive interpretation of structured Flow facts."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from jsonschema import ValidationError, validate

from modules.automation_diagnosis.litellm_client import LiteLLMClient

from .executive_query import executive_context


DEFAULT_EXECUTIVE_MODEL = "openai_gpt-5.4-nano"


class ExecutiveAIError(RuntimeError):
    """Raised when model output cannot cross the executive schema boundary."""


class ExecutiveInterpreterPort(Protocol):
    def interpret(
        self, question: str, view: dict[str, Any]
    ) -> str: ...


_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary"],
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
    },
}

_SYSTEM_PROMPT = """
Sos el asistente ejecutivo de Team360 Flow para Dirección.
Recibís hechos estructurados del caso (LIVE o AUDIT_SNAPSHOT) y una pregunta.
Reglas estrictas:
- respondé SOLO con los hechos provistos; no inventes eventos, personas,
  estados ni fechas;
- el campo status_fact es la verdad operacional (closed/open/pending_approval);
  nunca lo contradigas; si NO es "closed", el caso NO está cerrado;
- no infieras cumplimiento de SLA: el backend ya lo calcula en metrics/status;
- distinguí hechos de interpretación;
- si un dato no está disponible, decilo explícitamente;
- usá IDs (routing:<id>, sla:<id>, event:<id>, resolution:<id>,
  approval:<id>, audit:<id>) para trazabilidad;
- respondé en español, conciso y ejecutivo.
Devolvé SOLO JSON válido {"summary": "..."}.
""".strip()


def _parse(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:])
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    if start < 0:
        raise ExecutiveAIError("Executive AI response did not contain JSON.")
    try:
        value, _end = json.JSONDecoder().raw_decode(cleaned[start:])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ExecutiveAIError("Executive AI returned invalid JSON.") from exc
    try:
        validate(instance=value, schema=_SCHEMA)
    except ValidationError as exc:
        raise ExecutiveAIError("Executive AI schema validation failed.") from exc
    return value


def _compact_context(view: dict[str, Any], *, limit: int = 9000) -> str:
    context = executive_context(view)
    encoded = json.dumps(context, ensure_ascii=False, sort_keys=True)
    if len(encoded) > limit:
        return encoded[:limit] + "\n...(truncado por longitud; los IDs citados siguen siendo trazables)"
    return encoded


class LiteLLMExecutiveInterpreter:
    def __init__(
        self, client: LiteLLMClient | None = None, model: str | None = None
    ) -> None:
        self._client = client
        self.model = (
            model
            or os.environ.get("TEAM360_LITELLM_MODEL_ALIAS")
            or DEFAULT_EXECUTIVE_MODEL
        )

    def interpret(self, question: str, view: dict[str, Any]) -> str:
        try:
            client = self._client or LiteLLMClient()
            response = client.text_completion(
                self.model,
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Pregunta ejecutiva:\n"
                            f"{question}\n\n"
                            "Hechos estructurados del caso:\n"
                            f"{_compact_context(view)}\n\n"
                            'Devolvé {"summary":"..."}.'
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=500,
                correlation_id=str(view.get("request_id") or "executive"),
                metadata={
                    "feature": "flow_executive_audit_query",
                    "model_alias": self.model,
                },
            )
            parsed = _parse(response.content)
            return parsed["summary"].strip()
        except ExecutiveAIError:
            raise
        except Exception as exc:
            raise ExecutiveAIError("LiteLLM executive request failed.") from exc
