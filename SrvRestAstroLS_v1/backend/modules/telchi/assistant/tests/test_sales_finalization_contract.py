"""Daily-cut monetary execution remains a normal committed, authorized query."""
from copy import deepcopy

from modules.telchi.assistant.capabilities import SalesCapabilities
from modules.telchi.assistant import state_engine as engine
from modules.telchi.assistant.luna import SYSTEM
from modules.telchi.datalake.sales_query import MONETARY_PERMISSION, parameters, MONETARY_OPERATION


def test_explicit_daily_cut_uses_existing_monetary_capability():
    state = deepcopy(engine.EMPTY | engine.INTENT_V2)
    state.update(metric='sales.net_amount', requested_metrics=['sales.net_amount'],
                 period=dict(start='2026-10-01', end_exclusive='2026-10-30'))
    capabilities = SalesCapabilities()
    assert capabilities.availability(state).allowed
    assert capabilities.required_permission(state) == MONETARY_PERMISSION
    assert parameters(MONETARY_OPERATION, dict(date_from='2026-10-01',
                      date_to_exclusive='2026-10-30', currency='BS'))[-2:] == ['2026-10-01', '2026-10-30']


def test_interpreter_contract_does_not_reject_daily_cut_or_apply_quantity_window():
    assert 'si el período es parcial o tiene corte diario explícito' in SYSTEM
    assert 'La ventana fija de sales.source_top_items NO limita sales.net_amount' in SYSTEM
    assert 'Un corte diario explícito prevalece' in SYSTEM
