import pytest

from modules.automation_diagnosis.litellm_client import LiteLLMResponse
from modules.flow.approval_ai import (
    ApprovalAIError,
    LiteLLMApprovalInterpreter,
)
from modules.flow.domain import ApprovalDecision


class _Client:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def text_completion(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return LiteLLMResponse(
            content=self.content,
            model="gpt-5.4-nano-2026-03-17",
            usage={"total_tokens": 20},
            latency_ms=12,
        )


def test_deterministic_approve_does_not_call_model():
    client = _Client('{"decision":"APPROVE","reason":""}')
    result = LiteLLMApprovalInterpreter(client=client).interpret("APROBAR")
    assert result.decision == ApprovalDecision.APPROVE
    assert client.calls == []


def test_deterministic_reject_extracts_reason():
    client = _Client('{"decision":"REJECT","reason":""}')
    result = LiteLLMApprovalInterpreter(client=client).interpret(
        "RECHAZAR: falta verificar la luminaria"
    )
    assert result.decision == ApprovalDecision.REJECT
    assert result.reason == "falta verificar la luminaria"
    assert client.calls == []


def test_ambiguous_falls_back_to_model():
    client = _Client('{"decision":"AMBIGUOUS","reason":"no decidible"}')
    result = LiteLLMApprovalInterpreter(client=client).interpret("Ok, lo veo.")
    assert result.decision == ApprovalDecision.AMBIGUOUS
    assert result.reason == "no decidible"
    assert client.calls[0][0][0] == "openai_gpt-5.4-nano"


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"decision":"APPROVE"}',
        '{"decision":"RESOLVED","reason":""}',
    ],
)
def test_approval_ai_rejects_invalid_output(content):
    with pytest.raises(ApprovalAIError):
        LiteLLMApprovalInterpreter(client=_Client(content)).interpret("Ok, lo veo.")
