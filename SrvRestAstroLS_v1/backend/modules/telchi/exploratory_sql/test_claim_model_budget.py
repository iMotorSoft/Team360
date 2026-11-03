"""Incomplete model replies stay non-executable and retain diagnostic evidence."""
import asyncio
import json

import httpx
import pytest

from ..assistant.luna import CREDENTIAL_ENV, MODEL
from .research import LunaSQL


def test_incomplete_response_audited_without_execution_or_fallback(monkeypatch):
    monkeypatch.setenv(CREDENTIAL_ENV, 'synthetic-test-key')
    def respond(request):
        body = json.loads(request.content)
        assert body['max_output_tokens'] == 8192
        assert body['reasoning'] == {'effort': 'medium'} and body['store'] is False
        return httpx.Response(200, json=dict(model=MODEL, status='incomplete', reasoning={'effort': 'medium'},
            incomplete_details={'reason': 'max_output_tokens'}, usage={'output_tokens': 8192}))
    luna = LunaSQL(transport=httpx.MockTransport(respond), max_output_tokens=8192)
    with pytest.raises(RuntimeError, match='completion_mismatch'):
        asyncio.run(luna.next({}))
    assert len(luna.calls) == 1
    assert luna.calls[0]['accepted'] is False
    assert luna.calls[0]['incomplete_details']['reason'] == 'max_output_tokens'
    assert luna.calls[0]['fallback'] is False


@pytest.mark.parametrize('budget', [0, True, 8193, '8192'])
def test_output_ceiling_is_bounded(budget):
    with pytest.raises(ValueError): LunaSQL(max_output_tokens=budget)
