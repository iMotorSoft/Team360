"""The investigation lifecycle is independent from the request-turn deadline."""
import asyncio
import time

from .test_assistant import context, event, latest, proposal
from .test_research_fallback import build


GAP = proposal({'/metric': 'sales.by_products',
                '/period': {'start': '2026-10-01', 'end_exclusive': '2026-11-01'}},
               intent='NEW_QUERY')


def test_research_continues_past_legacy_turn_deadline_and_reports_elapsed_time():
    async def run():
        started = time.monotonic()
        async def researcher(question, conversation_id, ctx):
            await asyncio.sleep(0.03)
            return dict(status='READY', business_answer='Resultado verificado.',
                        publication='foundation_current', snapshot='snapshot-1',
                        question_coverage='COMPLETE', model_calls=[], sql_executions=1,
                        elapsed_seconds=time.monotonic() - started)

        handler = build([GAP], researcher)
        handler.turn_timeout_seconds = 0.001  # controlled substitute for the old 80s guard
        result = await handler.handle(event('Consulta empresarial prolongada'), context())

        assert result.classification == 'DIRECT_AVAILABLE'
        audit = latest(handler.store)
        assert audit['research']['status'] == 'READY'
        assert audit['timings']['research_ms'] >= 20
        assert audit['timings']['handler_total_ms'] >= 20

    asyncio.run(run())
