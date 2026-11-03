from copy import deepcopy
from pathlib import Path

import pytest

from modules.telchi.datalake import sales_controlled_block as block
from modules.telchi.datalake import sales_incremental as inc
from modules.telchi.datalake.source import HanaTransportLimits
from .test_sales_incremental import row, source_for


def header(r, count=1):
    fields = block.header_fields('sales')
    keys = [f.split(' AS ')[-1].split('.')[-1].strip('"') for f in fields]
    return dict({k:r.get(k) for k in keys}, ExpectedLines=count)


def plan():
    return dict(contract=block.CONTRACT,budget=deepcopy(block.BUDGET),excluded={d:[] for d in inc.DOMAINS},
                source='SAP_B1_HANA/TELCHI',business_from='2026-10-01',business_to_exclusive='2026-10-02')


def source(responses):
    s, resources = source_for(responses)
    s.limits = HanaTransportLimits(max_rows=250)
    return s, resources


def test_sql_bounds_scope_and_params():
    for d in inc.DOMAINS:
        h, l = block.header_query(d,[1,2]), block.line_query(d,[3,4])
        assert 'TOP 10' in h and 'NOT IN (?,?)' in h
        assert 'TOP 250' in l and 'OFFSET' not in l
        assert not any(t in h+l for t in ('OINM','OITW','OJDT','JDT1','OACT'))
        assert 'UpdateDate' in h+l and 'CANCELED' in h+l
    with pytest.raises(ValueError):
        block.line_query('sales',list(range(11)))


def test_complete_recovery_idempotency_watermark(tmp_path):
    r = row()
    # Use actual projection keys including None optional source values.
    h = header(r)
    r = dict(r, **{k:v for k,v in h.items() if k != 'ExpectedLines'})
    s, resources = source([[h],[r],[]])
    root = tmp_path/'block'
    pauses = []
    result = block.run(root,plan(),s,sleep=pauses.append)
    assert pauses == [10,10]
    assert result['reason'] == 'AUTHORIZED_SECOND_BLOCK_FINISHED_NO_THIRD_BLOCK',result
    assert len(result['queries']) == 3 and len(result['units']) == 2
    assert all(c.closed and cur.closed for c,cur in resources)
    assert block.recover(root) == block.recover(root)
    wm = block.watermark(root)
    assert wm['date_or_cursor']['sales'] == 1
    assert wm['change_watermark'] is None
    assert not wm['coverage']['october_complete']
    with pytest.raises(FileExistsError):
        block.run(root,plan(),s if not s.query_log else source([])[0])
    (root/'q02.response.json').write_text('[]')
    with pytest.raises(ValueError,match='hash'):
        block.recover(root)


def test_deterministic_line_pagination_over_250(tmp_path):
    r = row()
    h = header(r,251)
    rows = [dict(r,**{k:v for k,v in h.items() if k != 'ExpectedLines'},LineNum=i) for i in range(251)]
    s,_ = source([[h],rows[:250],rows[250:],[]])
    result = block.run(tmp_path/'block',plan(),s,sleep=lambda _:None)
    assert result['units'][0]['metrics']['lines'] == 251,result
    assert len(result['queries']) == 4
    params = inc.read_json(tmp_path/'block/q03.intent.json')['params']
    assert params[-3:] == [1,1,249]


@pytest.mark.parametrize('mutation',['missing','duplicate','changed','cancelled'])
def test_integrity_and_cancellation(mutation):
    r = row()
    h = header(r)
    r = dict(r,**{k:v for k,v in h.items() if k != 'ExpectedLines'})
    if mutation == 'missing':
        rows=[]
    elif mutation == 'duplicate':
        rows=[r,r]
    elif mutation == 'changed':
        rows=[dict(r,DocTotal='999')]
    else:
        h['CANCELED']='Y'; r['CANCELED']='Y'
        assert block.validate_unit('sales',[h],[r])['cancellations']==1
        return
    with pytest.raises(ValueError):
        block.validate_unit('sales',[h],rows)


def test_uncertain_request_and_persistence_failure(tmp_path,monkeypatch):
    s,_=source([])
    state=block.run(tmp_path/'uncertain',plan(),s,sleep=lambda _:None)
    assert not state['units'] and len(state['queries'])==1
    with pytest.raises(RuntimeError,match='UNCERTAIN'):
        block.recover(tmp_path/'uncertain')
    original=inc.seal
    def fail(path,value):
        if path.name.endswith('response.json'):
            raise OSError('disk full')
        original(path,value)
    monkeypatch.setattr(inc,'seal',fail)
    s,_=source([[]])
    state=block.run(tmp_path/'disk',plan(),s,sleep=lambda _:None)
    assert len(state['queries'])==1 and not state['units']
    with pytest.raises(RuntimeError,match='UNCERTAIN'):
        block.recover(tmp_path/'disk')


def test_effective_driver_250_row_limit_closes_resources():
    s,resources=source([[row(i) for i in range(251)]])
    with pytest.raises(RuntimeError,match='ROW_BUDGET'):
        s.query_read_only('lines',block.line_query('sales',[1]),(1,-1,-1,-1))
    assert len(s.query_log)==1
    assert all(c.closed and cur.closed for c,cur in resources)


def test_abnormal_latency_persists_response_then_stops(tmp_path):
    s,_=source([[]])
    original=s.query_read_only
    def slow(*args):
        rows=original(*args)
        s.query_log[-1]['duration_ms']=6000
        return rows
    s.query_read_only=slow
    state=block.run(tmp_path/'slow',plan(),s,sleep=lambda _:None)
    assert state['error_code']=='ABNORMAL_LATENCY_STOP' and len(state['queries'])==1
    assert (tmp_path/'slow/q01.receipt.json').exists()
    assert block.watermark(tmp_path/'slow')['date_or_cursor']['sales']==-1


def test_eight_select_ceiling_and_incomplete_document_no_watermark(tmp_path):
    r=row(); h=header(r,2001)
    rows=[dict(r,**{k:v for k,v in h.items() if k!='ExpectedLines'},LineNum=i) for i in range(1750)]
    s,_=source([[h]]+[rows[i:i+250] for i in range(0,1750,250)])
    result=block.run(tmp_path/'block',plan(),s,sleep=lambda _:None)
    assert len(result['queries'])==8 and not result['units']
    assert block.watermark(tmp_path/'block')['date_or_cursor']['sales']==-1
