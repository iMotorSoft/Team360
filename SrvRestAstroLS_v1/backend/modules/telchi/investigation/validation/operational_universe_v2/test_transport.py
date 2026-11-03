"""Offline adapter boundary and crash matrix. Never loads a real SAP driver."""
import json
import multiprocessing
from pathlib import Path

import pytest

from . import selective as s, transport as t
from ..controlled_physical_capture_v1 import capture as c
from ..controlled_physical_capture_v1.orchestrate import Budget


class Clock:
    def __init__(self):
        self.now = 0
        self.pauses = []
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        self.pauses.append(seconds)
        self.now += seconds


class Adapter:
    def __init__(self, clock, mode='ok'):
        self.clock, self.mode = clock, mode
        self.calls = []
        self.opened = self.closed = 0
        self.connection_closed = False
    def cursor(self):
        self.opened += 1
        return Cursor(self)
    def close(self):
        self.connection_closed = True


class Cursor:
    description = [('ItemCode',), ('U_FormaFarmac',)]
    def __init__(self, adapter):
        self.a = adapter
    def setquerytimeout(self, seconds):
        assert seconds == 3
    def execute(self, sql, params):
        self.a.calls.append((sql, params))
        self.params = params
        self.a.clock.now += 1.6 if self.a.mode=='slow' else .01
        if self.a.mode in ('timeout','disconnect','interrupt'):
            raise {'timeout': TimeoutError, 'disconnect': ConnectionError,
                   'interrupt': KeyboardInterrupt}[self.a.mode]()
    def fetchall(self):
        rows = [(k, None if i%2 else '1') for i,k in enumerate(self.params)]
        mode = self.a.mode
        if mode=='empty':
            return []
        if mode=='missing':
            return rows[:-1]
        if mode=='duplicate':
            return rows[:1]*2
        if mode=='unexpected':
            return [('NOT_REQUESTED', '1')]
        if mode=='unordered':
            return rows[::-1]
        if mode=='bad_width':
            return [('bad',)]
        return rows
    def close(self):
        self.a.closed += 1


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'PRIVATE', tmp_path)
    # A missed injected adapter is a hard offline failure, never a connection.
    monkeypatch.setattr(c, 'connect_hana', lambda: pytest.fail('REAL_HANA_FORBIDDEN'))
    clock = Clock()
    root = tmp_path/'selective'
    plan = s.plan_for([f'K{i:05}' for i in range(150)])
    def run(mode='ok', **kwargs):
        adapter = Adapter(clock, mode)
        result = t.run(root, plan, connect_factory=lambda: adapter,
            sleep=clock.sleep, clock=clock, budget=kwargs.pop('budget', Budget(clock=clock)),
            preflight=lambda _: {}, probe=lambda *_: {}, **kwargs)
        return result, adapter
    return root, plan, clock, run


def test_origin_and_all_130_real_batches(tmp_path, monkeypatch):
    plan = t.validate_origin()
    assert len(plan['item_codes'])==3242 and len(plan['batches'][-1]['parameters'])==17
    monkeypatch.setattr(s,'PRIVATE',tmp_path)
    monkeypatch.setattr(c,'connect_hana',lambda: pytest.fail('REAL_HANA_FORBIDDEN'))
    before = c.file_inventory(t.CAPTURE)
    clock = Clock()
    adapter = Adapter(clock)
    root = tmp_path/'full'
    # Production budget remains <=1800s: complete in successive invocations.
    result = t.run(root,plan,max_blocks=26,connect_factory=lambda:adapter,
        clock=clock,sleep=clock.sleep,budget=Budget(clock=clock),
        preflight=lambda _: {},probe=lambda *_: {})
    assert result['status']=='PARTIAL' and result['reason']=='global_budget_exhausted'
    assert adapter.connection_closed
    second = Adapter(clock)
    result = t.run(root,plan,resume=True,max_blocks=26,connect_factory=lambda:second,
        clock=clock,sleep=clock.sleep,budget=Budget(clock=clock),
        preflight=lambda _: {},probe=lambda *_: {})
    assert result['status']=='COMPLETE'
    calls = adapter.calls + second.calls
    assert calls==[(b['sql'],b['parameters']) for b in plan['batches']]
    assert [k for _,params in calls for k in params]==plan['item_codes']
    assert len(calls)==130 and len({i//5 for i in range(len(calls))})==26
    assert len(calls[-1][1])==17
    assert adapter.opened==adapter.closed and second.opened==second.closed
    assert set(clock.pauses)<={10,30} and clock.pauses.count(30)>=25
    cp=s.recover(root,plan)
    assert len(cp['batches'])==130
    assert before==c.file_inventory(t.CAPTURE)
    assert all('OFFSET' not in sql and 'COUNT' not in sql and sql.count('?')==len(params)
               and all(k not in sql for k in params) for sql,params in calls)


def test_microcapture_completed_block_resume_and_no_requery(harness):
    root,plan,clock,run=harness
    result,adapter=run()
    assert result['status']=='BLOCKS_COMPLETE' and result['queries']==5
    assert clock.pauses==[10]*4
    before=c.file_inventory(root)
    assert len(s.recover(root,plan)['batches'])==5 and before==c.file_inventory(root)
    result,adapter2=run(resume=True)
    assert result['status']=='COMPLETE' and result['queries']==1
    assert adapter2.calls[0][1]==plan['batches'][5]['parameters']
    assert clock.pauses[-1]==30
    result,adapter3=run(resume=True)
    assert result['queries']==0 and not adapter3.calls


@pytest.mark.parametrize('mode',['empty','missing'])
def test_missing_terminal_never_fabricated(harness, mode):
    root,plan,_,run=harness
    result,adapter=run(mode)
    assert result['status']=='BLOCKS_COMPLETE'
    batch=json.loads((root/'selective-000000.json').read_text())
    assert len(batch['not_returned'])==(25 if mode=='empty' else 1)
    assert not (root/'request.json').exists()
    assert adapter.opened==adapter.closed and adapter.connection_closed


@pytest.mark.parametrize('mode',['duplicate','unexpected','unordered','bad_width',
    'timeout','disconnect','interrupt'])
def test_invalid_or_interrupted_responses_block_retry_before_connect(harness, mode):
    root,plan,_,run=harness
    result,adapter=run(mode)
    assert result['status']=='PARTIAL' and len(adapter.calls)==1
    assert result['completed']==0 and (root/'request.json').exists()
    assert adapter.opened==adapter.closed and adapter.connection_closed
    with pytest.raises(RuntimeError,match='manual_review_no_retry'):
        run(resume=True)
    # Explicit offline review preserves intent and permits a later authorized repeat.
    before=c.digest(root/'request.json')
    with c.destination_lock(root):
        s.acknowledge_uncertain(root,plan,reason='operator reviewed uncertain physical outcome')
    assert before in c.file_inventory(root/'interrupted').values()
    result,adapter=run(resume=True)
    assert result['queries']==5


def test_slow_hana_persists_then_stops_without_retry(harness):
    root,plan,_,run=harness
    result,adapter=run('slow')
    assert result['reason']=='hana_latency_exceeded' and result['completed']==1
    assert len(s.recover(root,plan)['batches'])==1
    assert len(adapter.calls)==1 and adapter.connection_closed


def test_slow_persistence_not_misclassified_as_hana(harness, monkeypatch):
    root,plan,clock,run=harness
    original=s.commit_response
    def slow(*args,**kwargs):
        result=original(*args,**kwargs)
        clock.now+=10.1
        return result
    monkeypatch.setattr(s,'commit_response',slow)
    result,adapter=run()
    assert result['reason']=='PersistenceBlocked' and result['completed']==1
    assert result['hana_seconds']==pytest.approx([.01])
    assert result['persistence_seconds'][0]>10
    assert adapter.connection_closed and len(s.recover(root,plan)['batches'])==1


def test_stop_before_query_never_connects(harness):
    _,_,clock,run=harness
    budget=Budget(clock=clock); budget.request_stop()
    result,adapter=run(budget=budget)
    assert result['reason']=='signal_stop_requested' and not adapter.calls
    assert adapter.opened==0


@pytest.mark.parametrize('stage',[
    'before_execute','after_fetch','partial_journal','journal_fsynced_tmp',
    'after_journal','partial_batch','batch_fsynced_tmp','after_batch',
    'partial_checkpoint','after_checkpoint'])
def test_crash_matrix_a_to_h(harness, monkeypatch, stage):
    root,plan,_,run=harness
    original=s.save
    commit=s.commit_response
    reserve=s.reserve_request
    def stop_before(*args,**kwargs):
        reserve(*args,**kwargs)
        raise KeyboardInterrupt()
    def stop_after(*args,**kwargs):
        raise KeyboardInterrupt()
    if stage=='before_execute':
        monkeypatch.setattr(s,'reserve_request',stop_before)
    elif stage=='after_fetch':
        monkeypatch.setattr(s,'commit_response',stop_after)
    else:
        target = ('pending.json' if stage in ('partial_journal','journal_fsynced_tmp','after_journal')
                  else 'checkpoint.json' if 'checkpoint' in stage else 'selective-000000.json')
        def fault(path,value):
            if path.name==target and (root/'request.json').exists():
                if stage.startswith('partial') or stage.endswith('_tmp'):
                    tmp=path.with_suffix('.json.tmp')
                    with tmp.open('wb') as f:
                        f.write(b'{"partial":' if stage.startswith('partial') else c.encoded(value))
                        f.flush()
                        import os
                        os.fsync(f.fileno())
                else:
                    original(path,value)
                raise KeyboardInterrupt()
            original(path,value)
        monkeypatch.setattr(s,'save',fault)
    result,adapter=run()
    assert result['status']=='PARTIAL' and adapter.connection_closed
    assert len(adapter.calls)==(0 if stage=='before_execute' else 1)
    monkeypatch.setattr(s,'save',original)
    monkeypatch.setattr(s,'commit_response',commit)
    monkeypatch.setattr(s,'reserve_request',reserve)
    uncertain=stage in ('before_execute','after_fetch','partial_journal')
    with c.destination_lock(root):
        if stage=='partial_journal':
            with pytest.raises(RuntimeError,match='temporary'):
                s.recover(root,plan)
        else:
            cp=s.recover(root,plan)
            assert len(cp['batches'])==(0 if uncertain else 1)
        if uncertain:
            s.acknowledge_uncertain(root,plan,reason='offline crash review; repeat may be necessary')
        snapshot=c.file_inventory(root)
        cp=s.recover(root,plan)
        assert s.recover(root,plan)==cp and c.file_inventory(root)==snapshot
    result,next_adapter=run(resume=True)
    assert next_adapter.calls[0][1]==plan['batches'][0 if uncertain else 1]['parameters']
    assert result['status']=='BLOCKS_COMPLETE'


def test_plan_mutation_and_durable_corruption_prevent_connection(harness):
    root,plan,_,run=harness
    run()
    changed=s.plan_for(plan['item_codes']+['ZZZ'])
    with pytest.raises(RuntimeError,match='plan_mismatch'):
        t.run(root,changed,resume=True,preflight=lambda _: {})
    (root/'selective-000000.json').write_text('{}')
    with pytest.raises(RuntimeError,match='hash_mismatch'):
        run(resume=True)


def test_device_guard_blocks_before_adapter(harness):
    root,plan,clock,_=harness
    adapter=Adapter(clock)
    def blocked(_):
        raise t.persistence.PersistenceBlocked('destination_device_sustained_pressure')
    with pytest.raises(t.persistence.PersistenceBlocked):
        t.run(root,plan,connect_factory=lambda:adapter,preflight=blocked)
    assert not root.exists() and not adapter.calls and adapter.opened==0


def test_query_contract_rejects_sql_substitution(harness):
    _,plan,clock,_=harness
    adapter=Adapter(clock)
    batch=dict(plan['batches'][0],sql='SELECT * FROM "TELCHI"."OITM"')
    with pytest.raises(RuntimeError,match='unexpected_selective_sql'):
        t.fetch(adapter,batch,clock=clock)
    assert adapter.opened==0 and not adapter.calls


def test_cooperative_stop_during_fetch_commits_only_current_batch(harness):
    root,plan,clock,_=harness
    budget=Budget(clock=clock)
    class StopCursor(Cursor):
        def fetchall(self):
            budget.request_stop()
            return super().fetchall()
    class StopAdapter(Adapter):
        def cursor(self):
            self.opened+=1
            return StopCursor(self)
    adapter=StopAdapter(clock)
    result=t.run(root,plan,connect_factory=lambda:adapter,
        sleep=clock.sleep,clock=clock,budget=budget,
        preflight=lambda _: {},probe=lambda *_: {})
    assert result['status']=='PARTIAL' and result['reason']=='signal_stop_requested'
    assert result['completed']==1 and result['queries']==1
    assert len(s.recover(root,plan)['batches'])==1
    assert adapter.connection_closed and adapter.opened==adapter.closed==1


def test_failed_connection_close_never_reports_complete(harness):
    root,plan,clock,_=harness
    class BadClose(Adapter):
        def close(self):
            raise ConnectionError()
    adapter=BadClose(clock)
    result=t.run(root,plan,connect_factory=lambda:adapter,
        sleep=clock.sleep,clock=clock,preflight=lambda _: {},probe=lambda *_: {})
    assert result['status']=='PARTIAL' and result['close_error']=='ConnectionError'
    assert not result['connection_closed'] and result['completed']==5
    assert result['cursors_opened']==result['cursors_closed']==5


def lock_child(path, queue):
    try:
        with c.destination_lock(Path(path)):
            queue.put('UNEXPECTED_LOCK')
    except RuntimeError as exc:
        queue.put(str(exc))


def test_two_processes_same_destination(harness):
    root,_,_,run=harness
    run()
    context=multiprocessing.get_context('spawn')
    queue=context.Queue()
    with c.destination_lock(root):
        process=context.Process(target=lock_child,args=(str(root),queue))
        process.start()
        try:
            assert queue.get(timeout=10)=='capture_already_running'
        finally:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate(); process.join(timeout=5)
            queue.close(); queue.join_thread()
        assert process.exitcode==0
