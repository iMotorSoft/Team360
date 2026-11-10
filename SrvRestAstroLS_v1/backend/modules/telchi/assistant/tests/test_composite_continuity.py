"""Durable composite references built from the real authorized verifier contract."""
import asyncio
import json
from copy import deepcopy
from dataclasses import asdict

import pytest

from modules.telchi.exploratory_sql.ask_verifier import AskRegistry
from modules.telchi.exploratory_sql.test_quantitative_semantics import quantitative
from modules.telchi.exploratory_sql.test_authorized_foundation import setup
from modules.telchi.assistant.result_references import research_presentation, resolve
from .test_research_continuity import Researcher, context
from .test_research_fallback import build
from .test_assistant import event, latest

OWNER = ['owner']


@pytest.fixture
def result_factory(quantitative):
    registry, execute = quantitative
    manifests = []
    register = registry.register
    def capture(*args):
        manifest = register(*args)
        manifests.append(manifest)
        return manifest
    registry.register = capture
    def make(expression, where="currency='BS' AND doc_date='2026-02-01'"):
        refs = execute(expression, where)
        issued = manifests[-1]
        manifest = next(m for m in registry.manifests() if m['result_id'] == issued['result_id'])
        assert manifest['continuity_cells'] == issued['continuity_cells']
        entry = registry.entries[manifest['result_id']]
        saved = dict(result_id='research-turn', receipt={'binding': {}}, full_result=dict(
            question='Comparable published business values',
            evidence_manifests=[manifest],
            # Only nested citations: old adapter incorrectly discarded this result.
            claim_verifications=[dict(match=True, claim=dict(kind='calculation', operation='subtract', dependencies=refs))],
            results=[asdict(entry[2])]))
        # PostgreSQL/evidence wire preserves Decimal as exact strings.
        saved = json.loads(json.dumps(saved, default=str))
        return research_presentation(saved, OWNER, 'conversation')
    return make


def proposal(operation='absolute_difference', operands=None):
    return dict(intent='RESULT_REFERENCE', action='TRANSFORM_RESULT',
        result_reference=dict(result_id='research-turn', ordinal=None, field=None),
        transformation=dict(operation=operation, operands=operands or [dict(ordinal=1, field='a'), dict(ordinal=1, field='b')]),
        clarification=None)


def apply(view, p=None):
    return resolve(p or proposal(), view, None, OWNER, 'conversation', calculator=AskRegistry.calculate_pair)


def test_two_period_columns_and_signed_difference(result_factory):
    view = result_factory("sum(CASE WHEN doc_date='2026-01-01' THEN doc_total ELSE 0 END) AS a,"
        "sum(CASE WHEN doc_date='2026-02-01' THEN doc_total ELSE 0 END) AS b", "currency='BS'")
    assert len(view['manifest']['continuity_cells']) == 2
    assert '70.00 BS' in apply(view)[1]
    assert '-70.00 BS' in apply(view, proposal('subtract'))[1]
    assert '130.00 BS' in apply(view, proposal('add'))[1]


@pytest.mark.parametrize('dimension', ['doc_date', 'product', 'branch'])
def test_period_product_and_branch_rows(result_factory, dimension):
    view = result_factory(f'{dimension} AS label,sum(doc_total) AS amount', f"currency='BS' GROUP BY {dimension} ORDER BY {dimension}")
    p = proposal(operands=[dict(ordinal=1, field='amount'), dict(ordinal=2, field='amount')])
    assert 'Diferencia absoluta:' in apply(view, p)[1]
    assert len(view['rows']) == 2


def test_many_elements_sort_and_omitted_records(result_factory):
    view = result_factory('doc_entry,sum(doc_total) AS amount', "currency='BS' GROUP BY doc_entry ORDER BY doc_entry")
    assert len(view['rows']) == 3
    _, text = apply(view, proposal('sort_descending', [dict(ordinal=1, field='amount')]))
    assert text.index('60.00') < text.index('40.00') < text.index('30.00')
    page = dict(intent='RESULT_REFERENCE', action='PAGE_RESULT', clarification=None,
        result_reference=dict(result_id='research-turn', ordinal=2, field=None))
    assert '3.' in apply(view, page)[1]


def test_share_and_percent_are_distinct(result_factory):
    view = result_factory("sum(CASE WHEN branch='North' THEN doc_total ELSE 0 END) AS a,sum(doc_total) AS b")
    assert '60.00 %' in apply(view, proposal('share'))[1]
    assert '-40.00 %' in apply(view, proposal('percent_change'))[1]


def test_incompatible_units_and_measures_fail_closed(result_factory):
    view = result_factory("sum(CASE WHEN currency='BS' THEN doc_total ELSE 0 END) AS a,"
        "sum(CASE WHEN currency='USD' THEN doc_total ELSE 0 END) AS b", '1=1')
    with pytest.raises(ValueError, match='units_or_currency'): apply(view)
    view = result_factory('sum(doc_total) AS a,count(doc_entry) AS b')
    with pytest.raises(ValueError, match='compatible_measures'): apply(view)


@pytest.mark.parametrize('change', ['owner', 'conversation', 'result_id', 'missing_cell', 'truncated'])
def test_isolation_and_missing_evidence(result_factory, change):
    view = result_factory('sum(doc_total) AS a,sum(doc_total) AS b')
    p = proposal()
    if change == 'owner': view['owner'] = ['other-user-or-workspace']
    elif change == 'conversation': view['conversation_id'] = 'another-thread'
    elif change == 'result_id': p['result_reference']['result_id'] = 'another-result'
    elif change == 'missing_cell': view['manifest']['continuity_cells'] = []
    else:
        # Full recovery refuses incomplete results before interpretation.
        from .test_research_continuity import saved
        partial = saved(); partial['full_result']['results'][0]['truncated'] = True
        assert research_presentation(partial, OWNER, 'conversation') is None
        return
    with pytest.raises(ValueError): apply(view, p)


def test_ambiguous_reference_asks_without_inventing(result_factory):
    view = result_factory('sum(doc_total) AS a,sum(doc_total) AS b')
    p = dict(intent='RESULT_REFERENCE', action='ASK', result_reference=None,
        clarification=dict(question='¿Qué dos elementos querés comparar?'))
    ordinal, text = apply(view, p)
    assert ordinal is None and '?' in text


def test_handler_transform_revalidates_permissions_and_records_zero_sql(result_factory):
    view = result_factory("sum(CASE WHEN branch='North' THEN doc_total ELSE 0 END) AS a,sum(doc_total) AS b")
    class ExistingResearch(Researcher):
        calculate_result = staticmethod(AskRegistry.calculate_pair)
        async def result_reference(self, ctx, turn):
            return dict(deepcopy(view), owner=turn['owner'], conversation_id=ctx.conversation_id)
    async def run():
        researcher = ExistingResearch()
        handler = build([proposal()], researcher)
        answer = await handler.handle(event('Compará esos valores'), context())
        assert answer.classification == 'DIRECT_AVAILABLE', answer
        audit = latest(handler.store)
        assert audit['decision'] == 'LOCAL_RESULT_TRANSFORM'
        assert audit['research']['sql_executions'] == 0 and audit['capability_calls'] == 0
        researcher.allowed = False
        replay = await handler.handle(event('Compará esos valores'), context())
        assert replay.classification == 'DENIED'
    asyncio.run(run())
