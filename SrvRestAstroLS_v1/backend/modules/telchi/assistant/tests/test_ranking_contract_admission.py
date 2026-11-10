"""The failed gate is an invalid interpreter plan, never a reason to loosen RBAC."""
from copy import deepcopy
from modules.telchi.assistant import state_engine
from modules.telchi.assistant.luna import SYSTEM
from modules.telchi.assistant.tests.test_assistant import proposal


def test_legacy_ranking_rejection_and_supported_product_contract():
    period={'start':'2026-01-01','end_exclusive':'2026-09-16'}
    invalid=proposal({'/metric':'sales.source_top_items','/ranking_by':'quantity','/period':period})
    result=state_engine.process(deepcopy(state_engine.EMPTY),invalid,{},'original-invalid')
    assert not result['committed'] and result['contract_error']=='CONTRACT_ERROR_NO_COMMIT'
    valid=proposal({'/metric':'sales.commercial_line_amount_by','/group_by':'sap_product',
                    '/ranking_by':'quantity','/period':period})
    result=state_engine.process(deepcopy(state_engine.EMPTY),valid,{},'supported')
    assert result['committed']
    assert 'Nunca enviarlo con sales.source_top_items' in SYSTEM
