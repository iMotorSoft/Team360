from copy import deepcopy
from types import SimpleNamespace

import pytest

from modules.telchi.datalake import sales_continuity as c
from modules.telchi.datalake import sales_incremental as inc
from .test_sales_controlled_block import source, header
from .test_sales_incremental import row


class Guard:
    def assess(self):
        return SimpleNamespace(allowed=True,warnings=())


def pair(entry=1, lines=1):
    r = dict(row(entry),DocDate='2026-09-01')
    h = header(r,lines)
    r.update({k:v for k,v in h.items() if k != 'ExpectedLines'})
    return h,[dict(r,LineNum=i) for i in range(lines)]


def test_scope_and_budget():
    p=c.make_plan({})
    c.validate_plan(p)
    assert len(p['windows']) == 118
    assert p['windows'][-1]['end'] == '2026-10-30'
    assert c.BUDGET['max_selects'] == 12000
    for d in inc.DOMAINS:
        sql=c.header_sql(d)+c.line_sql(d,[1,2])
        assert 'TOP 100' in sql and 'TOP 250' in sql and 'IN (?,?)' in sql
        assert not any(t in sql for t in ['OINM','OITW','OJDT','JDT1','OACT'])
    p['budget']=dict(p['budget'],max_selects=12001)
    with pytest.raises(ValueError): c.validate_plan(p)
    with pytest.raises(ValueError): c.windows(end=c.date(2026,11,1))


def test_full_window_ledger_empty_days_resume_and_hashes(tmp_path):
    h,rows=pair(lines=251)
    s,resources=source([[h],rows[:250],rows[250:]]+[[]]*117)
    p=c.make_plan({}); root=tmp_path/'run'
    state=c.run(root,p,s,sleep=lambda _:None,guard=Guard())
    assert state['status']=='CAPTURED_PASS',state
    assert len(state['completed_windows'])==118 and not state['incomplete_windows']
    assert state['metrics']['sales']['lines']==251
    assert state['total_selects']==120
    assert all(conn.closed and cur.closed for conn,cur in resources)
    recovered=c.recover(root)
    assert len(recovered[2])==118 and len(recovered[4])==118
    s,_=source([])
    again=c.run(root,p,s,sleep=lambda _:None,guard=Guard())
    assert not again['queries_this_session'] and again['status']=='CAPTURED_PASS'
    (root/'q000002.response.json').write_text('[]')
    with pytest.raises(ValueError,match='hash'): c.recover(root)


def test_safe_replay_after_unit_write_interruption(tmp_path,monkeypatch):
    p=c.make_plan({}); root=tmp_path/'run'
    original=inc.seal
    def fail(path,value):
        if path.name.startswith('u'): raise OSError('interrupted commit')
        return original(path,value)
    monkeypatch.setattr(inc,'seal',fail)
    s,_=source([[]])
    state=c.run(root,p,s,sleep=lambda _:None,guard=Guard())
    assert state['total_selects']==1 and state['units']==0
    monkeypatch.setattr(inc,'seal',original)
    s,_=source([[]]*117)
    state=c.run(root,p,s,sleep=lambda _:None,guard=Guard())
    assert state['status']=='CAPTURED_PASS'
    assert len(s.query_log)==117  # first receipt replayed without SAP
    assert len(c.recover(root)[1])==118


def test_uncertain_request_no_retry(tmp_path):
    p=c.make_plan({}); root=tmp_path/'run'
    s,resources=source([])
    state=c.run(root,p,s,sleep=lambda _:None,guard=Guard())
    assert state['status']=='PARTIAL' and len(s.query_log)==1
    with pytest.raises(RuntimeError,match='UNCERTAIN'): c.recover(root)
    s,_=source([[]]*118)
    with pytest.raises(RuntimeError,match='UNCERTAIN'):
        c.run(root,p,s,sleep=lambda _:None,guard=Guard())
    assert not s.query_log


@pytest.mark.parametrize('mutation',['duplicate','missing','changed','outside','cancelled'])
def test_document_integrity(mutation):
    h,rows=pair()
    w=c.windows()[0]
    if mutation=='duplicate': rows*=2
    if mutation=='missing': rows=[]
    if mutation=='changed': rows[0]['DocTotal']='999'
    if mutation=='outside': h['DocDate']='2026-11-01'
    if mutation=='cancelled':
        h['CANCELED']='Y';rows[0]['CANCELED']='Y'
        assert c.validate_unit(w,-1,[h],rows)['cancellations']==1
    else:
        with pytest.raises(ValueError): c.validate_unit(w,-1,[h],rows)


def test_fetch_byte_bound():
    cur=c.ByteCursor(SimpleNamespace(description=[('column',)],fetchmany=lambda size:[('x'*c.BUDGET['response_bytes'],)]))
    with pytest.raises(RuntimeError,match='BYTE_BUDGET'): cur.fetchmany(1)


def test_fetch_byte_bound_includes_column_names():
    cursor=SimpleNamespace(description=[('x'*1048576,)],fetchmany=lambda size:[('a',),('b',)])
    with pytest.raises(RuntimeError,match='BYTE_BUDGET'):
        c.ByteCursor(cursor).fetchmany(2)


def test_budget_and_degradation(tmp_path):
    p=c.make_plan({});p['created_at']='2026-01-01T00:00:00+00:00'
    s,_=source([])
    state=c.run(tmp_path/'expired',p,s,sleep=lambda _:None,guard=Guard())
    assert state['code']=='GLOBAL_TIME_BUDGET_STOP' and not s.query_log
    p=c.make_plan({})
    s,_=source([[]]*118)
    original=s.query_read_only
    def slow(*args):
        rows=original(*args); s.query_log[-1]['duration_ms']=4500
        return rows
    s.query_read_only=slow
    state=c.run(tmp_path/'slow',p,s,sleep=lambda _:None,guard=Guard())
    assert state['code']=='SUSTAINED_HANA_DEGRADATION_STOP' and len(s.query_log)==5
    assert len(c.recover(tmp_path/'slow')[4])==5


def test_inflight_pagination_resume(tmp_path,monkeypatch):
    h,rows=pair(lines=251)
    p=c.make_plan({});root=tmp_path/'run'
    original=inc.seal
    def stop(path,value):
        result=original(path,value)
        if path.name=='q000002.receipt.json': raise KeyboardInterrupt()
        return result
    monkeypatch.setattr(inc,'seal',stop)
    s,_=source([[h],rows[:250]])
    state=c.run(root,p,s,sleep=lambda _:None,guard=Guard())
    assert state['units']==0
    monkeypatch.setattr(inc,'seal',original)
    s,_=source([rows[250:]]+[[]]*117)
    state=c.run(root,p,s,sleep=lambda _:None,guard=Guard())
    assert state['status']=='CAPTURED_PASS'
    assert len(s.query_log)==118 and state['total_selects']==120
