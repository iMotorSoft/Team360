from datetime import datetime, timezone

import pytest

from modules.automation_diagnosis.litellm_client import LiteLLMResponse
from modules.flow.domain import CandidateRequest
from modules.flow.intake.ai import FlowIntakeAIError, LiteLLMFlowIntakeInterpreter
from modules.messaging.domain import InboundMessage


def _message(body: str = "mensaje") -> InboundMessage:
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id="m1",
        external_thread_id="t1",
        sender="vecina@example.com",
        recipients=("mesa@example.com",),
        subject="Solicitud",
        text_body=body,
        received_at=datetime.now(timezone.utc),
    )


class _Client:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def text_completion(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        return LiteLLMResponse(
            content=self.content,
            model="gpt-5.4-nano-2026-03-17",
            usage={"total_tokens": 42},
            latency_ms=12,
        )


def _candidate(description="Reparar luminaria", location="Olleros y Ciudad de la Paz"):
    return {
        "description": description,
        "tentative_category": "alumbrado",
        "location_text": location,
        "missing_data": [],
        "context_notes": None,
        "confidence": 0.94,
    }


def test_initial_schema_accepts_one_request():
    client = _Client(str({"requests": [_candidate()], "clarification_question": None}).replace("'", '"').replace("None", "null"))
    result = LiteLLMFlowIntakeInterpreter(client=client).interpret_initial(_message())
    assert len(result.requests) == 1
    assert result.requests[0].location_text == "Olleros y Ciudad de la Paz"
    assert client.calls[0][0] == "openai_gpt-5.4-nano"


def test_initial_schema_accepts_two_independent_requests_and_context():
    second = _candidate("Retirar árbol caído", "en la misma cuadra")
    second["tentative_category"] = "arbolado"
    second["context_notes"] = "La ubicación depende de la primera solicitud."
    import json
    result = LiteLLMFlowIntakeInterpreter(
        client=_Client(json.dumps({"requests": [_candidate(), second], "clarification_question": None}))
    ).interpret_initial(_message())
    assert len(result.requests) == 2
    assert result.requests[1].location_text == "en la misma cuadra"


def test_initial_schema_preserves_missing_information():
    value = _candidate(location=None)
    value["missing_data"] = ["ubicación"]
    import json
    result = LiteLLMFlowIntakeInterpreter(
        client=_Client(json.dumps({"requests": [value], "clarification_question": None}))
    ).interpret_initial(_message())
    assert result.requests[0].missing_data == ("ubicación",)
    assert result.requests[0].location_text is None


@pytest.mark.parametrize("content", ["not-json", '{"requests": "wrong"}'])
def test_invalid_ai_output_is_controlled(content):
    with pytest.raises(FlowIntakeAIError):
        LiteLLMFlowIntakeInterpreter(client=_Client(content)).interpret_initial(_message())


def test_ambiguous_reply_is_not_treated_as_confirmation():
    import json
    client = _Client(json.dumps({
        "action": "ambiguous",
        "requests": [],
        "clarification_question": "¿Confirmás las dos solicitudes?",
    }))
    result = LiteLLMFlowIntakeInterpreter(client=client).interpret_reply(
        _message("puede ser"),
        (CandidateRequest("Reparar poste", "alumbrado", "Olleros"),),
    )
    assert result.action == "ambiguous"
    assert result.clarification_question


def test_new_information_requires_reinterpretation_with_full_request_list():
    import json
    revised = [_candidate(), _candidate("Retirar árbol caído", "misma cuadra")]
    client = _Client(json.dumps({
        "action": "reinterpret",
        "requests": revised,
        "clarification_question": None,
    }))
    result = LiteLLMFlowIntakeInterpreter(client=client).interpret_reply(
        _message("Además hay un árbol caído"),
        (CandidateRequest("Reparar poste", "alumbrado", "Olleros"),),
    )
    assert result.action == "reinterpret"
    assert len(result.requests) == 2
