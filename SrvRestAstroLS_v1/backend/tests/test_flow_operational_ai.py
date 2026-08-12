from datetime import datetime, timezone

import pytest

from modules.automation_diagnosis.litellm_client import LiteLLMResponse
from modules.flow.domain import OperationalAction
from modules.flow.operational_ai import (
    LiteLLMOperationalInterpreter,
    OperationalAIError,
)
from modules.messaging.domain import InboundMessage


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


def _message(text):
    return InboundMessage(
        provider="gmail",
        channel="email",
        external_message_id="reply-1",
        external_thread_id="different-mailbox-thread",
        sender="technician@example.com",
        recipients=("mesa@example.com",),
        subject="Re: [Team360 Flow] Nueva solicitud #request",
        text_body=text,
        received_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize(
    ("text", "action"),
    [
        ("Recibido. Lo estamos verificando.", "ACK_OR_PROGRESS"),
        ("La cuadrilla ya va.", "ACK_OR_PROGRESS"),
        ("Ok.", "AMBIGUOUS"),
        ("Este mensaje no corresponde al caso.", "UNRELATED"),
        ("Ya quedó reparado.", "UNSUPPORTED_OPERATIONAL_ACTION"),
    ],
)
def test_operational_ai_accepts_schema_valid_actions(text, action):
    client = _Client(f'{{"action":"{action}","summary":"clasificado"}}')
    result = LiteLLMOperationalInterpreter(client=client).interpret(_message(text))
    assert result.action == OperationalAction(action)
    assert client.calls[0][0][0] == "openai_gpt-5.4-nano"


@pytest.mark.parametrize(
    "content",
    ["not json", '{"action":"ACK_OR_PROGRESS"}', '{"action":"RESOLVED","summary":"x"}'],
)
def test_operational_ai_rejects_invalid_output(content):
    with pytest.raises(OperationalAIError):
        LiteLLMOperationalInterpreter(client=_Client(content)).interpret(
            _message("Recibido")
        )
