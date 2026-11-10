"""Handler reuses selected resolver output; no second retrieval/model router."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from modules.business_semantics import resolver
from .test_assistant import context, event, latest
from .test_research_fallback import build


def test_handler_forwards_the_same_authorized_resolution_once(monkeypatch):
    selected = dict(status='resolved', concepts=[], interpretation_concepts=[],
                    context_concepts=[], ambiguous=False, semantic_guard={})
    calls, retrievals = [], []
    monkeypatch.setattr(resolver, 'luna_context', lambda result: result)

    class Research:
        accepts_business_knowledge = True

        async def __call__(self, question, conversation, ctx, **kwargs):
            calls.append(kwargs)
            return dict(status='READY', business_answer='Fixture result; not live business evidence.')

    async def scope(*args):
        return {'organization_id': 'org'}

    async def resolve(*args, **kwargs):
        retrievals.append(kwargs)
        return selected

    @asynccontextmanager
    async def semantics_turn(turn):
        yield None

    async def run():
        handler = build([{'intent': 'RESEARCH', 'action': 'INVESTIGATE'}], Research())
        handler.concept_resolver = SimpleNamespace(repository=SimpleNamespace(scope=scope), resolve=resolve)
        handler._semantics_turn = semantics_turn
        response = await handler.handle(event('Investigá una caída regional nueva'), context())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert len(retrievals) == len(calls) == len(handler.interpreter.calls) == 1
        assert calls[0]['business_knowledge'] is selected
        assert latest(handler.store)['business_semantics'] == selected
        assert latest(handler.store)['capability_calls'] == 0

    asyncio.run(run())


def test_whatsapp_app_uses_the_same_handler_factory(monkeypatch):
    import sys
    from modules.telchi.assistant import composition
    from modules.telchi.assistant.handler import BusinessPolicy
    sentinel, seen = object(), []
    policy = BusinessPolicy('telchi', 'workspace', 'existing.read')
    monkeypatch.setenv('TEAM360_TELCHI_DURABLE', '0')

    def factory(**kwargs):
        seen.append(kwargs)
        return sentinel

    def app_factory(**kwargs):
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(composition, 'create_telchi_handler', factory)
    monkeypatch.setattr(composition, 'registration', lambda handler: handler)
    monkeypatch.setitem(sys.modules, 'ls_iMotorSoft_Srv05', SimpleNamespace(create_app=app_factory))
    app = composition.create_telchi_app(policy=policy, pool='existing-pool')
    assert app.messaging_handlers['telchi'] is sentinel
    assert seen == [dict(policy=policy, pool='existing-pool')]


def test_standalone_handler_composition_preserves_dev_only_guard(monkeypatch):
    import pytest
    from modules.telchi.assistant.composition import create_telchi_handler
    monkeypatch.setenv('TEAM360_ENV', 'production')
    monkeypatch.setenv('TEAM360_BUSINESS_SEMANTICS', '0')
    monkeypatch.setenv('TEAM360_TELCHI_DURABLE', '1')
    with pytest.raises(ValueError, match='DEV only'):
        create_telchi_handler(policy=None, pool='unused')
