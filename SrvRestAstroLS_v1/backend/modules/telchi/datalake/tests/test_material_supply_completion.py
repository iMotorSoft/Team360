"""Independent elapsed-day observations never certify historical quantities."""
from copy import deepcopy
import pytest
from modules.telchi.datalake.material_supply_completion import derive, replay, CONTRACT, OUTPUTS
from modules.telchi.datalake.operational_overlap import groups
from modules.telchi.datalake.foundation_publication import FoundationReaderError


def line(entry, *, base=22, date='2026-10-10', item='M', **kw):
    return dict(DocEntry=entry,LineNum=0,BaseType=base,BaseEntry=1,BaseLine=0,
                DocDate=date,ItemCode=item,Quantity='99',CardCode='S',U_TIPOCOMPRA='IMP',**kw)


def test_lead_time_independent_of_quantities_and_bom():
    receipt=[line(2)]
    po=[line(1,date='2026-10-01')]
    profiles, anomalies, coverage=derive(receipt,[],po)
    assert len(profiles)==4 and not anomalies
    assert all(r['p50_days']==9 and r['sample_count']==1 for r in profiles)
    assert coverage['contract']==CONTRACT
    assert coverage['physical_unit_conversion_required'] is False
    assert coverage['historical_open_orders_accredited'] is False
    changed=deepcopy(receipt);changed[0]['Quantity']='invalid'
    assert derive(changed,[],po)==(profiles,anomalies,coverage)


def test_negative_unlinked_and_item_mismatch_visible():
    receipts=[line(2,date='2026-09-01'),line(3,base=-1),line(4,item='WRONG')]
    profiles, anomalies, coverage=derive(receipts,[],[line(1,date='2026-10-01')])
    assert not profiles
    assert {r[2] for r in anomalies}=={'NEGATIVE_LEAD_TIME','NO_PO_LINEAGE','LINKED_ITEM_MISMATCH'}
    assert coverage['eligible_receipt_lines']==0 and coverage['anomaly_receipt_lines']==3


def test_indirect_native_path():
    receipt=line(3,base=18);receipt['BaseEntry']=2
    profiles, anomalies, coverage=derive([receipt],[line(2)],[line(1,date='2026-10-01')])
    assert profiles and not anomalies
    assert coverage['lineage']['INDIRECT_PO_RECEIPT_VIA_AP_INVOICE']==1


@pytest.mark.parametrize('which',[0,1,2])
def test_duplicate_keys_fail_closed(which):
    inputs=[[line(2)],[],[line(1)]]
    inputs[which]=[line(9),line(9)]
    with pytest.raises(FoundationReaderError,match='duplicate purchasing'):
        derive(*inputs)


@pytest.mark.parametrize('marker',[{}, {'contract':'FORGED'}, {'contract':CONTRACT,'extra':True}])
def test_invalid_contract_rejected_before_source_io(marker):
    with pytest.raises(FoundationReaderError,match='unsupported material lead-time'):
        replay(None,{'overlap':{'material_lead_time':marker}})


def test_profiles_account_for_each_eligible_line_at_every_basis():
    profiles, anomalies, coverage=derive([line(2),line(3),line(4,base=-1)],[],[line(1,date='2026-10-01')])
    assert len(anomalies)==1
    for basis in {p['lead_time_basis'] for p in profiles}:
        assert sum(p['sample_count'] for p in profiles if p['lead_time_basis']==basis)==coverage['eligible_receipt_lines']==2


def test_outputs_opt_in_only():
    original=groups({})
    assert not set(OUTPUTS)&set(original['material_supply'])
    enhanced=groups({'overlap':{'material_lead_time':{'contract':CONTRACT}}})
    assert enhanced['material_supply']==original['material_supply']+OUTPUTS
    assert {k:v for k,v in enhanced.items() if k!='material_supply'}=={k:v for k,v in original.items() if k!='material_supply'}
