"""Cheap security regressions; no services or configuration changes."""
import asyncio

from modules.telchi.research_port import presentation
from modules.telchi.assistant.tests.test_research_fallback import build, record, GAP
from modules.telchi.assistant.tests.test_assistant import event, context


def test_durable_presentation_excludes_model_prose_and_sql():
    result = presentation(dict(model_calls=[dict(model='luna', provider='fixture',
        fallback=False, elapsed_seconds=1, output_text='SELECT private_value',
        output_messages=['raw prose'], non_executable_messages=['commentary'])],
        turns=[{'result': {'status': 'COMPLETED'}}, {'result': {'status': 'NOT_EXECUTED'}}]))
    assert result['model_calls'] == [dict(model='luna', provider='fixture',
                                         fallback=False, elapsed_seconds=1)]
    assert result['sql_executions'] == 1
    assert 'private_value' not in repr(result) and 'raw prose' not in repr(result)


def test_durable_result_preserves_decimal_without_float_rounding():
    import json
    from decimal import Decimal
    from types import SimpleNamespace
    from modules.telchi.research_repository import ResearchRecoveryRepository
    from modules.telchi.assistant.tests.test_assistant import context
    stored = []
    class Connection:
        async def execute(self, sql, params):
            adapter = params[-1]
            stored.append(json.loads((adapter.dumps or json.dumps)(adapter.obj)))
            return SimpleNamespace(rowcount=1)
    ctx = context()
    scope = SimpleNamespace(workspace=ctx.channel.workspace_id, user_id=ctx.sender_identity.user_id)
    value = dict(full_result=dict(results=[dict(rows=[[Decimal('12345678901234567890.123456')]])]))
    asyncio.run(ResearchRecoveryRepository().save(Connection(), scope, ctx, value))
    assert stored[0]['full_result']['results'][0]['rows'][0][0] == '12345678901234567890.123456'


def test_legacy_cached_research_without_recovery_receipt_fails_closed():
    async def exercise():
        researcher = record()
        handler = build([GAP], researcher)
        first = await handler.handle(event(), context())
        assert first.classification == 'DIRECT_AVAILABLE'
        cached = await handler.handle(event(), context())
        assert cached.classification == 'DENIED'
        assert first.text not in cached.text
        assert len(researcher.calls) == 1
    asyncio.run(exercise())
