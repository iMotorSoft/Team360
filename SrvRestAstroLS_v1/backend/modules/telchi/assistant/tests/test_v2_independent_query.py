"""Protect V2 new requests from the previous executable documentary plan."""
from modules.telchi.assistant import state_engine as engine
from .test_assistant import plan, proposal


def test_v2_new_query_pending_does_not_inherit_prior_period_or_filters():
    before = dict(plan(), branches=['old'])
    result = engine.process(before, proposal({'/schema_version': 2, '/entity_mention': {'text': 'Calenta', 'type': None}}, intent='NEW_QUERY', action='ASK', clarification={'slot': 'metric', 'question': '¿Importe, cantidades o ambas?'}), {}, 'new')
    assert result['committed']
    state = result['state_after']
    assert state['period'] == before['period']  # active state remains protected
    proposed = state['pending']['proposed']
    assert proposed['period'] is None and proposed['metric'] is None and proposed['branches'] == []
    assert proposed['entity_mention']['text'] == 'Calenta'
