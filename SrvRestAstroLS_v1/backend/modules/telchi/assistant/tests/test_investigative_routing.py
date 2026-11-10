"""Routing guarantees at the real handler boundary, not answer-quality claims.

Fixtures deliberately vary questions and commercial failure classes. No product,
customer or phrase in these tests is a runtime routing rule.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant.luna import LunaError
from .test_assistant import context, event, latest, proposal
from .test_research_fallback import build, record, PERIOD

AUDITED_QUESTION = 'cual es cliente que compra mas acido nitrico de los ultimos 3 meses'
AUDITED_PROPOSAL = proposal({
    '/metric': 'sales.commercial_line_amount_by', '/group_by': 'card_code',
    '/ranking_by': 'amount', '/entity_mention': None, '/schema_version': 2,
    '/requested_metrics': ['sales.commercial_line_amount_by'],
    '/temporal_reference': None, '/product_search_text': 'acido nitrico',
}, unset=['/period', '/comparison', '/branches', '/sales_channel', '/product_target',
          '/customer_target', '/business_category', '/selected_item_codes', '/limit',
          '/breakdown_by', '/periods', '/period_mode'], action='ASK', intent='NEW_QUERY',
    clarification={'slot': 'period',
                   'question': '¿Qué fechas exactas querés considerar para los últimos tres meses?'})


def test_audited_rejection_reaches_research_without_executing_or_committing_delta():
    async def run():
        research = record()
        h = build([AUDITED_PROPOSAL], research)
        response = await h.handle(event(AUDITED_QUESTION), context())
        a = latest(h.store)
        assert response.classification == 'DIRECT_AVAILABLE'
        assert [c[0] for c in research.calls] == [AUDITED_QUESTION]
        assert a['research']['routing_category'] == 'CONTRACT_SCOPE_UNSUPPORTED'
        assert a['contract_error'] == 'CONTRACT_ERROR_NO_COMMIT'
        assert a['interpretation_proposed'] == AUDITED_PROPOSAL
        assert a['capability_calls'] == 0 and a['committed'] is False
        assert a['confirmed_state'] == engine.EMPTY
    asyncio.run(run())


@pytest.mark.parametrize('question', [
    'Ranking de clientes por familia química en los últimos tres meses',
    'Compará nuestras ventas de este trimestre con el anterior',
    'Incluí todas las presentaciones del producto y verificá la cobertura',
    '¿Y cuáles de esos clientes no volvieron a comprar?',
    '¿Cuántas órdenes abiertas tienen recepción parcial por proveedor?',
])
def test_same_luna_can_choose_research_without_a_commercial_state(question):
    async def run():
        research = record()
        h = build([{'intent': 'RESEARCH', 'action': 'INVESTIGATE'}], research)
        response = await h.handle(event(question), context())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert research.calls[0][0] == question
        assert h.interpreter.calls[0]['research_available'] is True
        assert latest(h.store)['capability_calls'] == 0
        assert latest(h.store)['research']['routing_category'] == 'RESEARCH_REQUESTED'
    asyncio.run(run())


@pytest.mark.parametrize('category', [
    'MAPPING_MISSING', 'METRIC_MISSING', 'TEMPORAL_METADATA_MISSING',
    'RANKING_UNAVAILABLE', 'CATEGORY_CAPABILITY_UNAVAILABLE',
    'OPERATIONAL_SCOPE_UNAVAILABLE', 'PERIOD_SET_UNSUPPORTED',
    'PERIOD_PARAMETER_UNSUPPORTED', 'DIMENSION_NOT_ACCREDITED',
])
def test_representation_limits_are_researchable(category):
    from modules.telchi.assistant.capabilities import Availability
    class Catalog(SalesCapabilities):
        def availability(self, state):
            return Availability(False, 'fixture catalog limit', category)
    async def run():
        research = record()
        h = build([proposal({'/metric': 'sales.net_amount', '/period': PERIOD},
                            intent='NEW_QUERY')], research)
        h.capabilities = Catalog()
        response = await h.handle(event('Pregunta empresarial fuera del camino rápido'), context())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert latest(h.store)['research']['routing_category'] == category
    asyncio.run(run())


@pytest.mark.parametrize('bad', [
    proposal({'/sql': 'SELECT 1'}),
    proposal({'/product_context': {'rows': []}}),
    proposal({'/selected_item_codes': ['UNPROVED']}),
    proposal({'/reference': 'unknown-result'}),
    proposal({'/period': {'start': 'not-a-date', 'end_exclusive': '2026-11-01'}}),
    {'intent': 'RESEARCH', 'action': 'INVESTIGATE', 'sql': 'SELECT 1'},
])
def test_malformed_or_unproven_plans_never_gain_research_authority(bad):
    async def run():
        research = record()
        h = build([bad], research)
        await h.handle(event('Investigar no es un bypass de integridad'), context())
        assert not research.calls
        assert latest(h.store)['execution_status'] == 'not_executed'
    asyncio.run(run())


def test_denied_identity_never_calls_either_luna_or_research():
    async def run():
        research = record()
        h = build([{'intent': 'RESEARCH', 'action': 'INVESTIGATE'}], research)
        c = context()
        c = replace(c, sender_identity=replace(c.sender_identity, permissions=frozenset()))
        result = await h.handle(event('Investigá ventas'), c)
        assert result.classification == 'DENIED'
        assert not h.interpreter.calls and not research.calls
    asyncio.run(run())


def test_complete_accelerator_keeps_single_execution_and_idempotent_replay():
    from .test_assistant import setup, plan
    async def run():
        h, store, interpreter, calls = setup([proposal({
            '/metric': 'sales.source_top_items', '/period': plan()['period']}, intent='NEW_QUERY')])
        research = record()
        h.researcher = research
        response = await h.handle(event('Productos por cantidad en el período indicado'), context())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert len(calls) == 1 and len(interpreter.calls) == 1
        assert not research.calls
        assert await h.handle(event(), context()) == response
        assert len(calls) == 1 and len(interpreter.calls) == 1
    asyncio.run(run())


def test_primary_research_never_requires_a_valid_state_engine_contract():
    async def run():
        research = record()
        h = build([{'intent': 'RESEARCH', 'action': 'INVESTIGATE'}], research)
        def forbidden_engine(*args, **kwargs):
            raise AssertionError('commercial state engine must not gate research')
        h.engine = forbidden_engine
        response = await h.handle(event('Investigá la cobertura de abastecimiento'), context())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert len(research.calls) == 1
        assert latest(h.store)['capability_calls'] == 0
    asyncio.run(run())


def test_commercial_semantic_mismatch_is_not_a_source_permission_denial(monkeypatch):
    from types import SimpleNamespace
    from contextlib import asynccontextmanager
    from modules.business_semantics import resolver
    monkeypatch.setattr(resolver, 'luna_context', lambda result: {})
    async def scope(*args):
        return {'organization_id': 'org'}
    async def resolve(*args, **kwargs):
        return {'semantic_guard': {'requires_clarification': True}}
    async def run():
        research = record()
        h = build([], research)
        h.concept_resolver = SimpleNamespace(repository=SimpleNamespace(scope=scope), resolve=resolve)
        @asynccontextmanager
        async def semantics_turn(turn):
            yield None
        h._semantics_turn = semantics_turn
        response = await h.handle(event('Pregunta sin definición comercial preestablecida'), context())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert research.calls[0][0] == 'Pregunta sin definición comercial preestablecida'
        assert not h.interpreter.calls
        assert latest(h.store)['capability_calls'] == 0
        assert latest(h.store)['committed'] is False
    asyncio.run(run())


def test_technical_model_failure_is_not_a_catalog_gap():
    async def run():
        research = record()
        h = build([], research)
        async def fail(**kwargs):
            raise LunaError('credential_unavailable', kind='configuration')
        h.interpreter.interpret = fail
        result = await h.handle(event('Consultá ventas'), context())
        assert result.classification == 'ERROR'
        assert not research.calls
    asyncio.run(run())


def test_clarification_is_not_reported_as_executed_research():
    async def run():
        research = record(status='NEEDS_CLARIFICATION', text='¿Importe comercial o cantidad?')
        h = build([{'intent': 'RESEARCH', 'action': 'INVESTIGATE'}], research)
        response = await h.handle(event('¿Quién compra más?'), context())
        assert response.classification == 'NEEDS_CLARIFICATION'
        assert latest(h.store)['execution_status'] == 'not_executed'
    asyncio.run(run())


def test_fast_path_clarification_still_preserves_real_ambiguity():
    async def run():
        research = record()
        h = build([proposal({'/metric': 'sales.net_amount'}, intent='NEW_QUERY', action='ASK',
                            clarification={'slot': 'period', 'question': '¿Qué período?'} )], research)
        response = await h.handle(event('¿Cuánto facturamos?'), context())
        assert response.classification == 'NEEDS_CLARIFICATION'
        assert not research.calls
    asyncio.run(run())


@pytest.mark.parametrize('status', ['PARTIAL', 'UNKNOWN_STATUS'])
def test_unfinished_or_unknown_report_never_counts_as_a_completed_answer(status):
    async def run():
        research = record(status=status, text='No hay cifras suficientes para responder.')
        h = build([{'intent': 'RESEARCH', 'action': 'INVESTIGATE'}], research)
        response = await h.handle(event('Investigá los principales proveedores'), context())
        assert response.classification == 'DIRECT_UNAVAILABLE'
        assert latest(h.store)['research']['status'] == status
        assert latest(h.store)['timings']['handler_total_ms'] >= 0
    asyncio.run(run())


def test_resource_stop_is_not_misreported_as_a_commercial_catalog_rejection():
    async def run():
        research = record(status='BLOCKED', text='unverified figures must not be shown',
                          reason='execution_stopped:host_io_or_memory_pressure')
        h = build([{'intent': 'RESEARCH', 'action': 'INVESTIGATE'}], research)
        response = await h.handle(event('Investigá las compras'), context())
        assert response.classification == 'DIRECT_UNAVAILABLE'
        assert 'límite de recursos' in response.text
        assert 'unverified figures' not in response.text
        assert latest(h.store)['decision'] == 'RESEARCH_BLOCKED'
        assert latest(h.store)['execution_status'] == 'not_completed'
    asyncio.run(run())


def test_specific_commercial_permission_denial_never_falls_back():
    async def run():
        research = record()
        h = build([proposal({'/metric': 'sales.net_amount', '/period': PERIOD},
                            intent='NEW_QUERY')], research)
        response = await h.handle(event('Facturación neta de octubre 2026'), context())
        assert response.classification == 'DENIED'
        assert not research.calls
        assert latest(h.store)['capability_calls'] == 0
    asyncio.run(run())


def test_product_lookup_failure_is_not_a_missing_source_or_integrity_failure():
    from modules.telchi.assistant.capabilities import ProductResolutionError
    class UnresolvedProduct(SalesCapabilities):
        async def execute(self, state):
            raise ProductResolutionError([])
    async def run():
        research = record()
        h = build([proposal({'/metric': 'sales.source_top_items',
                            '/period': {'start': '2026-01-01', 'end_exclusive': '2026-09-16'}},
                            intent='NEW_QUERY')], research)
        h.capabilities = UnresolvedProduct()
        response = await h.handle(event('Investigar las presentaciones del producto'), context())
        assert response.classification == 'DIRECT_AVAILABLE'
        assert latest(h.store)['research']['routing_category'] == 'PRODUCT_LOOKUP_UNRESOLVED'
    asyncio.run(run())


@pytest.mark.parametrize('reason', [
    'commercial_reconciliation_failed', 'commercial_catalog_integrity_failed',
    'product_binding_changed', 'commercial_quantity_unaccredited', 'datalake_busy',
])
def test_actual_source_integrity_and_runtime_failures_do_not_trigger_research(reason):
    class BrokenSource(SalesCapabilities):
        async def execute(self, state):
            raise ValueError(reason)
    async def run():
        research = record()
        h = build([proposal({'/metric': 'sales.source_top_items',
                            '/period': {'start': '2026-01-01', 'end_exclusive': '2026-09-16'}},
                            intent='NEW_QUERY')], research)
        h.capabilities = BrokenSource()
        await h.handle(event('Consulta con fuente no acreditable'), context())
        assert not research.calls
        assert latest(h.store)['decision'] != 'RESEARCH'
    asyncio.run(run())


def test_corrupt_prior_state_is_not_reclassified_as_commercial_limit():
    before = deepcopy(engine.EMPTY)
    before['group_by'] = 'invalid-dimension'
    result = engine.process(before, AUDITED_PROPOSAL, {}, 'turn')
    assert result['committed'] is False
    assert 'researchable_contract_error' not in result
