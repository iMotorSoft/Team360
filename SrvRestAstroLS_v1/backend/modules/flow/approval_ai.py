"""Conservative supervisor closure decision interpretation via LiteLLM."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from jsonschema import ValidationError, validate

from modules.automation_diagnosis.litellm_client import LiteLLMClient

from .domain import (
    ApprovalDecision,
    ApprovalDecisionResult,
    approval_reason_after_command,
    deterministic_approval_decision,
)


DEFAULT_APPROVAL_MODEL = "openai_gpt-5.4-nano"


class ApprovalAIError(RuntimeError):
    """Raised when model output cannot cross the approval schema boundary."""


class ApprovalInterpreterPort(Protocol):
    def interpret(
        self, text: str, *, correlation_id: str | None = None
    ) -> ApprovalDecisionResult: ...


_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "reason"],
    "properties": {
        "decision": {"enum": [decision.value for decision in ApprovalDecision]},
        "reason": {"type": "string", "maxLength": 500},
    },
}

_SYSTEM_PROMPT = """
Sos el intérprete conservador de la respuesta de un supervisor de Team360 Flow.
Recibís el texto nuevo de una respuesta a un pedido de aprobación de cierre.
Respondé SOLO JSON válido con decision y reason.
Nunca cierres un caso por tu cuenta: devolvé APPROVE únicamente ante un mandato
inequívoco; ante cualquier duda devolvé AMBIGUOUS.

APPROVE: mandato inequívoco de autorizar el cierre, por ejemplo "APROBAR",
"aprobado", "autorizo el cierre".
REJECT: rechazo inequívoco, por ejemplo "RECHAZAR: falta verificar", "no aprobar".
AMBIGUOUS: no permite decidir, por ejemplo "Ok, lo veo", "gracias".
""".strip()


def _parse(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:])
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    if start < 0:
        raise ApprovalAIError("Approval AI response did not contain JSON.")
    try:
        value, _end = json.JSONDecoder().raw_decode(cleaned[start:])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApprovalAIError("Approval AI returned invalid JSON.") from exc
    try:
        validate(instance=value, schema=_SCHEMA)
    except ValidationError as exc:
        raise ApprovalAIError("Approval AI schema validation failed.") from exc
    return value


class LiteLLMApprovalInterpreter:
    def __init__(
        self, client: LiteLLMClient | None = None, model: str | None = None
    ) -> None:
        self._client = client
        self.model = (
            model
            or os.environ.get("TEAM360_LITELLM_MODEL_ALIAS")
            or DEFAULT_APPROVAL_MODEL
        )

    def interpret(
        self, text: str, *, correlation_id: str | None = None
    ) -> ApprovalDecisionResult:
        deterministic = deterministic_approval_decision(text)
        if deterministic is not None:
            reason = (
                approval_reason_after_command(text)
                if deterministic == ApprovalDecision.REJECT
                else ""
            )
            return ApprovalDecisionResult(deterministic, reason)
        try:
            client = self._client or LiteLLMClient()
            response = client.text_completion(
                self.model,
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Interpretá la decisión del supervisor. "
                            'Devolvé {"decision":"...","reason":"..."}.\n\n'
                            f"RESPUESTA:\n{text}"
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=300,
                correlation_id=correlation_id,
                metadata={
                    "feature": "flow_closure_approval",
                    "model_alias": self.model,
                },
            )
            parsed = _parse(response.content)
            return ApprovalDecisionResult(
                decision=ApprovalDecision(parsed["decision"]),
                reason=(parsed.get("reason") or "").strip(),
            )
        except ApprovalAIError:
            raise
        except Exception as exc:
            raise ApprovalAIError("LiteLLM approval request failed.") from exc
