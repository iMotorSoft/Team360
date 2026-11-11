from copy import deepcopy

from modules.telchi.assistant import business_scope, state_engine
from modules.telchi.assistant.commercial_continuity import request_contract
from modules.telchi.exploratory_sql.adaptive_research import bounded_payload


def plan(**overrides):
    value = dict(state_engine.DEFAULTS)
    value.update(schema_version=2, requested_metrics=['sales.net_amount'],
                 metric='sales.net_amount',
                 period={'start': '2026-09-01', 'end_exclusive': '2026-10-01'},
                 sales_channel='HORIZONTAL')
    value.update(overrides)
    state_engine.validate(value)
    return value


def proposal(set_values, *, intent='REFINE', action='EXECUTE', clarification=None):
    return dict(intent=intent, action=action,
                state_delta={'set': set_values, 'unset': []},
                clarification=clarification)


def test_material_channel_ambiguity_becomes_durable_pending_not_sql_authority():
    before = plan()
    proposed = request_contract(
        proposal({'/period': {'start': '2026-10-01', 'end_exclusive': '2026-11-01'},
                  '/branches': ['Segundo Anillo']}),
        '¿Cuánto vendió el Segundo Anillo en octubre?', before)
    assert proposed['action'] == 'ASK'
    assert proposed['clarification']['slot'] == 'sales_channel'
    pending = state_engine.process(before, proposed, {}, 'turn-1')
    assert pending['committed']
    assert pending['state_after']['pending']['proposed']['branches'] == ['Segundo Anillo']
    assert pending['state_after']['pending']['proposed']['sales_channel'] is None
    assert pending['state_after']['pending']['base_state_hash']


def test_clarification_selection_resumes_original_scope_and_all_channels_clears_filter():
    before = plan()
    ask = request_contract(proposal({'/branches': ['Segundo Anillo']}),
                           '¿Cuánto vendió el Segundo Anillo en octubre?', before)
    pending = state_engine.process(before, ask, {}, 'turn-1')['state_after']
    answer = proposal({'/sales_channel': None}, intent='ANSWER_CLARIFICATION')
    resumed = state_engine.process(pending, answer, {}, 'turn-2')
    assert resumed['committed']
    assert resumed['state_after']['branches'] == ['Segundo Anillo']
    assert resumed['state_after']['sales_channel'] is None
    assert resumed['state_after']['pending'] is None


def test_effective_scope_separates_explicit_and_inherited_filters():
    state = plan(branches=['Segundo Anillo'])
    contract = business_scope.effective_scope(
        state, question='ventas del Segundo Anillo', intent='REFINE', resolution='confirmed')
    contract['explicit_filters'] = {'branches': ['Segundo Anillo']}
    contract['inherited_confirmed_filters'] = {'sales_channel': 'HORIZONTAL'}
    assert contract['explicit_filters']['branches'] == ['Segundo Anillo']
    assert contract['inherited_confirmed_filters']['sales_channel'] == 'HORIZONTAL'
    assert contract['state_hash']


def test_catalog_and_observations_fit_without_repeating_full_metadata():
    columns = [dict(name=f'c{i}', sql_type='VARCHAR', semantic_constraints=[])
               for i in range(80)]
    catalog = dict(tables=[dict(name=f'source_{i}', grain='document', permission='read',
                                columns=columns, semantic_constraints=[])
                           for i in range(20)], source_column_dictionary=[])
    payload = dict(question='q', conversation=[], catalog=catalog,
                   observations=[dict(turn=i, evidence_manifest={'columns': [], 'row_ids': []},
                                      rows=[{'amount': '1'}]) for i in range(1, 3)])
    compact = bounded_payload(payload)
    assert len(str(compact).encode()) <= 32768
    assert all(entry['rows'] for entry in compact['observations'])
