"""L01 durable population: 311 authorized records, no duplicate or loss.

The controller recovers the whole grouped population with bounded keyset pages
of the same scope. The durable carrier persists every recovered record once, so
a continuation serves those records without repeating the investigation.
"""
from copy import deepcopy

import pytest

from modules.telchi.assistant import result_references as refs


def accounts(total, start=0):
    return [{'card_code': f'C{index:06d}', 'customer_name': f'Cliente {index}',
             'documentary_line_count': index % 7 + 1} for index in range(start, start + total)]


def payload(total=311, complete=True, first_page=100):
    rows = accounts(total)
    names = ['card_code', 'customer_name', 'documentary_line_count']
    manifest = dict(result_id='executed', query_id='query', publication='p', snapshot='1',
                    group_expressions=['card_code', 'customer_name'],
                    columns=[{'alias': name} for name in names],
                    filter_expression='currency COMPARE_EQUAL "BS"')
    first = rows[:first_page]
    chunks = [rows[start:start + 100] for start in range(first_page, total, 100)]
    recovery = dict(complete=complete, pages=len(chunks),
                    recovered_records=len(first) + sum(len(chunk) for chunk in chunks),
                    entity_column='card_code',
                    distinct_entities=len(first) + sum(len(chunk) for chunk in chunks))
    return dict(result_id='research-turn', receipt={'binding': {}}, full_result=dict(
        question='¿Qué clientes compraron ácido nítrico en todas sus presentaciones en octubre de 2026?',
        claim_verifications=[dict(match=True, claim=dict(kind='executed_cell', result_id='executed'))],
        evidence_manifests=[manifest],
        results=[dict(query_id='query', status='COMPLETED', truncated=not complete,
                      schema=[dict(name=name, sql_type='VARCHAR') for name in names],
                      rows=[[row[name] for name in names] for row in first])],
        population_recovery={'executed': recovery},
        population_pages={'executed': [dict(query_id=f'page-{number}', page=number + 1,
            schema=[dict(name=name, sql_type='VARCHAR') for name in names],
            rows=[[row[name] for name in names] for row in chunk], status='COMPLETED', truncated=False)
            for number, chunk in enumerate(chunks)]} if complete else {},
        presentation_pages={'executed': list(range(1, 11))}))


def test_every_recovered_record_is_durable_once_and_ordered():
    view = refs.research_presentation(payload(), ['owner'], 'conversation')
    assert len(view['rows']) == 311
    assert [row['card_code'] for row in view['rows']] == [f'C{index:06d}' for index in range(311)]
    assert view['next_ordinal'] == 11
    assert refs.interpreter_context(view)['row_count'] == 311


def test_continuation_serves_durable_records_without_research():
    view = refs.research_presentation(payload(), ['owner'], 'conversation')
    proposal = dict(intent='RESULT_REFERENCE', action='PAGE_RESULT',
                    result_reference=dict(result_id='research-turn', ordinal=11, field=None),
                    clarification=None)
    ordinal, text = refs.resolve(proposal, view, None, ['owner'], 'conversation')
    assert ordinal == 15
    for index in range(10, 15):
        assert f'C{index:06d}' in text
    assert '11–15 de 311 registros conservados' in text and 'Podés pedir los siguientes' in text
    beyond = dict(proposal, result_reference=dict(result_id='research-turn', ordinal=300, field=None))
    ordinal, text = refs.resolve(beyond, view, None, ['owner'], 'conversation')
    assert ordinal == 304 and '300–304 de 311 registros conservados' in text
    last = dict(proposal, result_reference=dict(result_id='research-turn', ordinal=311, field=None))
    ordinal, text = refs.resolve(last, view, None, ['owner'], 'conversation')
    assert ordinal == 311 and '311–311 de 311 registros conservados' in text


def test_repeated_boundary_row_never_duplicates_a_durable_record():
    value = payload()
    duplicated = deepcopy(value)
    first_of_second = duplicated['full_result']['population_pages']['executed'][0]['rows'][0]
    duplicated['full_result']['population_pages']['executed'][0]['rows'] = [
        duplicated['full_result']['population_pages']['executed'][0]['rows'][-1]] + \
        duplicated['full_result']['population_pages']['executed'][0]['rows']
    assert first_of_second in duplicated['full_result']['population_pages']['executed'][0]['rows']
    view = refs.research_presentation(duplicated, ['owner'], 'conversation')
    assert view is None or len(view['rows']) == 311


def test_incomplete_recovery_is_not_referencable_as_the_population():
    value = payload(complete=False)
    assert refs.research_presentation(value, ['owner'], 'conversation') is None
    # An unrecovered truncated page keeps the previous behaviour: no durable list.
    truncated = payload()
    truncated['full_result']['population_pages'] = {}
    truncated['full_result']['results'][0]['truncated'] = True
    assert refs.research_presentation(truncated, ['owner'], 'conversation') is None

def test_accounting_mismatch_fails_closed():
    value = payload()
    value['full_result']['population_recovery']['executed']['recovered_records'] = 312
    assert refs.research_presentation(value, ['owner'], 'conversation') is None
    missing_schema = payload()
    missing_schema['full_result']['population_pages']['executed'][0]['schema'] = [dict(name='card_code')]
    assert refs.research_presentation(missing_schema, ['owner'], 'conversation') is None


@pytest.mark.parametrize('total', [100, 311])
def test_durable_population_survives_the_interpreter_disclosure_bound(total):
    view = refs.research_presentation(payload(total=total), ['owner'], 'conversation')
    assert len(view['rows']) == total
    context = refs.interpreter_context(view)
    assert len(context['rows']) == min(total, 50) and context['rows_complete'] is (total <= 50)

def test_recovered_population_survives_the_single_page_byte_ceiling():
    """311 authorized accounts do not fit one page; the durable view must still hold them."""
    wide = deepcopy(payload())
    full = wide['full_result']
    names = ['card_code', 'customer_name', 'documentary_line_count']
    # Real shape of the L01 answer: measures and dates widen each record.
    names = names + ['presentation_count', 'commercial_line_amount', 'min_doc_date', 'max_doc_date']
    for result in full['results'] + [page for pages in full['population_pages'].values() for page in pages]:
        result['schema'] = [dict(name=name, sql_type='VARCHAR') for name in names]
        result['rows'] = [row + [row[2], '123456.78', '2026-10-01T00:00:00', '2026-10-31T00:00:00']
                          for row in result['rows']]
    wide['full_result']['evidence_manifests'][0]['columns'] = [{'alias': name} for name in names]
    rows = refs.research_presentation(wide, ['owner'], 'conversation')['rows']
    assert len(rows) == 311
    assert len({row['card_code'] for row in rows}) == 311
    assert len(__import__('json').dumps(rows).encode()) > refs.MAX_BYTES
    # The page-sized ceiling still refuses an unrecovered list.
    truncated = payload(complete=False)
    assert refs.research_presentation(truncated, ['owner'], 'conversation') is None
