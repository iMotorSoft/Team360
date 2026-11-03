from copy import deepcopy
import pytest
from .contract import FIELDS, accept_sidecar, plan_current
from modules.telchi.assistant.state_engine import EMPTY


def empty():
    out = {k: None for k in FIELDS}
    for k in ('metrics','dimensions','filters','sort','segments','granularities','geographies','relations','claims','unresolved_requirements'):
        out[k]=[]
    out['scope']={'branch_ids':[],'warehouse_ids':[]}
    return out


def proposal():
    return dict(intent='NEW_QUERY', action='EXECUTE', clarification=None,
                state_delta={'set':{'/metric':'sales.net_amount','/period':{'start':'2026-05-01','end_exclusive':'2026-06-01'}},'unset':[]})


def simple_intent():
    v=empty(); v.update(business_domain='SALES',metrics=['sales.net_amount'],
                       time=dict(kind='PERIOD',as_of=None,periods=[proposal()['state_delta']['set']['/period']]))
    return v


def test_no_state_mutation_and_simple_allowed():
    before=deepcopy(EMPTY); p=proposal(); original=deepcopy(p)
    result=plan_current(before,p,{},'t',simple_intent())
    assert result['executable_capability_plan']['allowed']
    assert not result['executable_capability_plan']['executed']
    assert before==EMPTY and p==original


@pytest.mark.parametrize('field,value',[
 ('metrics',['customer_count']),('segments',['farmacias']),('granularities',['month']),
 ('geographies',['La Paz']),('dimensions',['customer']),('unresolved_requirements',['year']),
 ('scope',{'branch_ids':['B_SECRET'],'warehouse_ids':[]}),('business_domain','CREDIT'),
 ('time',None),('comparison',{'baseline':'2024'}),('limit',50),
 ('measure_context',{'currency':'USD'}), ('measure_context','BS'),
 ('scope','Saavedra'), ('limit',[]), ('business_domain',[])])
def test_unrepresented_requirements_block(field,value):
    v=simple_intent(); v[field]=value
    result=plan_current(EMPTY,proposal(),{},'t',v)
    assert not result['executable_capability_plan']['allowed']
    assert result['requested_business_intent']==v


def test_grounded_relations_not_certified():
    v=empty(); v['relations']=[dict(subject='Citrato',predicate='distribution',object='L&S',
      geography='Cochabamba',evidence='lo hace L&S',source_turn_id='t',status='USER_ASSERTED_UNVERIFIED')]
    accepted,error=accept_sidecar(None,{'requested_business_intent':v},{'t':'En Cochabamba lo hace L&S'})
    assert error is None and accepted==v
    v['relations'][0]['status']='CERTIFIED'
    rejected,error=accept_sidecar(accepted,{'requested_business_intent':v},{'t':'En Cochabamba lo hace L&S'})
    assert error and rejected==accepted


@pytest.mark.parametrize('response', [{}, {'requested_business_intent':{}}, None, {'requested_business_intent':{'/metric':'bad'}}])
def test_atomic_sidecar_rejection(response):
    old=empty()
    assert accept_sidecar(old,response,{})==(old,'SIDECAR_REJECTED_NO_COMMIT')
    assert not plan_current(EMPTY,proposal(),{},'t',old,'error')['executable_capability_plan']['allowed']


def test_raw_execute_on_rejected_proposal_cannot_authorize():
    p=proposal(); p['state_delta']['set']['/geography']='La Paz'
    assert not plan_current(EMPTY,p,{},'t')['executable_capability_plan']['allowed']


def test_no_catalog_availability_bypass():
    p=proposal(); p['state_delta']['set']['/sales_channel']='HORIZONTAL'
    assert not plan_current(EMPTY,p,{},'t')['executable_capability_plan']['allowed']
