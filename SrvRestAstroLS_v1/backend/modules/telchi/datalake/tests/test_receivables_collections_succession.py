"""CxC update/receipt/snapshot regression. No operational DATA_ROOT or SAP."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
import hashlib
import json

import duckdb
import pytest

from modules.telchi.datalake import receivables_collections_succession as cxc
from modules.telchi.datalake import receivables_collections_atomic as atomic
from modules.telchi.datalake import receivables_collections_history as history
from modules.telchi.datalake import independent_facts_succession as independent
from modules.telchi.datalake.foundation_publication import ComponentReference, FoundationPublication, FoundationReaderError
from modules.telchi.datalake.raw import write_raw
from modules.telchi.runtime.config import DuckDBSafetyProfile


@pytest.fixture
def prepared(tmp_path, request, monkeypatch):
    monkeypatch.setenv('TELCHI_DUCKDB_TEMP_DIRECTORY',str(tmp_path/'runtime_tmp'))
    con = duckdb.connect(config={'threads': 2})
    con.execute('LOAD ducklake')
    con.execute(f"ATTACH 'ducklake:{tmp_path}/catalog.ducklake' AS telchi (DATA_PATH '{tmp_path}/data')")
    atomic.ensure_tables(con)
    native = {name: [] for name in atomic.ENTITY_ORDER}
    native['receivable_document'] = [dict(source_object_type='13', source_doc_entry='1', customer_code='C1',
        document_date='2026-09-01', due_date='2026-09-30', document_total='1000', currency='BS',
        cancelled='N', cancel_date=None)]
    native['collection_payment'] = [dict(source_object_type='24', source_doc_entry='9', customer_code='C1',
        payment_date='2026-10-20', payment_total='200', cancelled='N', pay_no_document='N')]
    native['collection_allocation'] = [dict(payment_doc_entry='9', payment_date='2026-10-20',
        target_object_type='13', target_doc_entry='1', allocated_amount='200')]
    native['reconciliation_event'] = [dict(reconciliation_id='1', reconciliation_date='2026-10-20',
        cancelled='N', cancellation_of_reconciliation_id='0')]
    native['reconciliation_participant'] = [dict(reconciliation_id='1', source_line_id='0',
        reconciliation_date='2026-10-20', participant_object_type='13', participant_object_abs='1',
        is_credit='D', reconciled_amount='200')]
    scenario = getattr(request, 'param', None)
    if scenario in {'reversal_before', 'reversal_after'}:
        native['reconciliation_event'][0]['cancelled'] = 'Y'
        day = '2026-10-25' if scenario == 'reversal_before' else '2026-11-02'
        native['reconciliation_event'].append(dict(reconciliation_id='2', reconciliation_date=day,
            cancelled='N', cancellation_of_reconciliation_id='1'))
        native['reconciliation_participant'].append(dict(reconciliation_id='2', source_line_id='0',
            reconciliation_date=day, participant_object_type='13', participant_object_abs='1',
            is_credit='D', reconciled_amount='200'))
    if scenario in {'native_before', 'native_after', 'native_at_close'}:
        day = {'native_before':'2026-10-25','native_after':'2026-11-02','native_at_close':'2026-10-31'}[scenario]
        native['reconciliation_event'][0].update(cancelled='Y',cancellation_of_reconciliation_id='2',
            reconciliation_type='3',reconciliation_total='200',currency='BS',created_date='2026-10-20')
        native['reconciliation_event'].append(dict(reconciliation_id='2',reconciliation_date=day,
            cancelled='C',cancellation_of_reconciliation_id='1',reconciliation_type='7',
            reconciliation_total='200',currency='BS',created_date=day))
        native['reconciliation_participant'][0].update(transaction_id='51914',transaction_row_id='0',account='1120101')
        native['reconciliation_participant'].append(dict(native['reconciliation_participant'][0],
            reconciliation_id='2',reconciliation_date=day,reconciled_amount='-200'))
    if scenario == 'future_effect':
        native['reconciliation_event'].append(dict(reconciliation_id='2', reconciliation_date='2026-11-02',
            cancelled='N', cancellation_of_reconciliation_id='0'))
        native['reconciliation_participant'].append(dict(reconciliation_id='2', source_line_id='0',
            reconciliation_date='2026-11-02', participant_object_type='13', participant_object_abs='1',
            is_credit='D', reconciled_amount='100'))
    if scenario == 'native_integer_transport':
        native['receivable_document'][0].update(salesperson_code=-1,payment_term_code=1)
    if scenario == 'cancel_after':
        native['receivable_document'][0].update(cancelled='Y', cancel_date='2026-11-02')
    if scenario in {'invoice_before','invoice_at','invoice_after'}:
        day={'invoice_before':'2026-10-25','invoice_at':'2026-10-31','invoice_after':'2026-11-02'}[scenario]
        native['receivable_document'][0].update(cancelled='Y',transaction_id='T1',
            document_total_foreign='0',document_total_system='100')
        native['receivable_document'].append(dict(native['receivable_document'][0],
            source_doc_entry='5',cancelled='C',transaction_id='T5',document_date=day))
    receipts, controls = {}, {}
    plan = history.plan('2026-10-31', '2026-11-04')
    clock = '2026-11-03T00:00:00'
    for segment in atomic.plan_segments(atomic.HISTORY_START, date(2026, 11, 4)):
        entity = segment.entity
        rows = [r for r in native[entity] if not segment.start or
            segment.start.isoformat() <= r[atomic.DATE_COLUMN[entity]] < segment.end.isoformat()]
        metadata = atomic._raw_manifest(segment, 'fixture', rows, clock,
            hashlib.sha256(atomic.SQL[entity].encode()).hexdigest())
        raw = None
        if rows:
            transport_rows=rows
            if scenario=='native_integer_transport' and entity=='receivable_document':
                transport_rows=[dict(row,salesperson_code=-1.0,payment_term_code=1.0) for row in rows]
            raw = write_raw(root=tmp_path/'raw', segment_id=segment.segment_id,
                extraction_id='fixture', rows=transport_rows, metadata=metadata,
                profile=DuckDBSafetyProfile(threads=2, memory_limit='256MB'))
            raw = {k:raw[k] for k in ('extraction_id', 'path', 'manifest_hash', 'row_count')}
        normalized = atomic.transform_rows(entity, rows, run_id='fixture', source_as_of=clock, built_at=clock)
        cxc._insert(con, entity, normalized)
        receipts[segment.segment_id] = dict(metadata, status='COMPLETED', raw_manifest=raw,
            atomic_row_count=len(normalized))
        controls[segment.segment_id] = dict(reconciled=True, normalized_rows=len(normalized))
    snapshot = con.execute("SELECT id FROM ducklake_current_snapshot('telchi')").fetchone()[0]
    coverage = dict(plan=plan, complete=True, prefix_only=False, opening_balance_status='ACCREDITED',
        segments=controls, source_fingerprint=history.digest(history.snapshot_fingerprint(con, snapshot)))
    if scenario in {'reversal_before', 'reversal_after'}:
        coverage['cancellation_link_direction'] = 'REVERSAL_TO_ORIGINAL'
    if scenario in {'invoice_before','invoice_at','invoice_after'}:
        rows=[]
        for d in native['receivable_document']:
            key=d['source_doc_entry']; sign=1 if key=='1' else -1; posting=d['document_date']
            rows.append(dict(doc=key,role=d['cancelled'],posting=posting,tax='2026-09-01',
                created='2026-11-03',customer='C1',currency='BS',total='1000',foreign_total='0',system_total='100',
                transaction='T'+key,journal_posting=posting,journal_tax='2026-09-01',journal_created='2026-11-03',
                journal_type='13',journal_document=key,pair_min='5' if key=='1' else '1',
                pair_max='5' if key=='1' else '1',lines=2,linked_lines=2,ledger_min=posting,
                ledger_max=posting,ledger_lines=1,local_effect=str(sign*1000),foreign_effect='0',system_effect=str(sign*100)))
        coverage['invoice_cancellation_receipt']=write_raw(root=tmp_path/'supplement',segment_id='dates',
            extraction_id='fixture',rows=rows,metadata=dict(contract=history.INVOICE_DATE_CONTRACT,
                params=['2022-03-31','2026-11-04'],source_as_of=clock,
                query_hash=hashlib.sha256(history.INVOICE_DATE_SQL.encode()).hexdigest()),
            profile=DuckDBSafetyProfile(threads=2,memory_limit='256MB'))
    catalog = {name:ComponentReference(name, name+'_old', source_as_of='2026-09-01T00:00:00')
               for name in ('reference', 'sales', 'credit_memo', 'oinm', 'oitw')}
    catalog['reference'] = ComponentReference('reference', 'ref')
    components = {name:ref.as_dict() for name,ref in catalog.items()}
    for name in ('material_supply', cxc.NAME, 'product_commercial_semantics'):
        components[name] = dict(name=name, publication_id=name+'_old', source_as_of='2026-09-01T00:00:00')
    base = FoundationPublication('foundation_base', 'base', status='CURRENT', reference_version='ref',
        components=catalog, manifest=dict(foundation_publication_id='foundation_base', components=components,
            base_snapshot_id=snapshot, facts_base_snapshot_id=0, sales_facts_revalidation={'sealed':'unchanged'},
            permission='UNCHANGED'))
    class Store:
        @contextmanager
        def connection_factory(self):
            yield con
    try:
        yield con, snapshot, coverage, receipts, base, Store()
    finally:
        con.close()


def produce(prepared):
    con, snapshot, coverage, receipts, *_ = prepared
    return cxc.materialize(con, atomic_snapshot=snapshot, as_of='2026-10-31', coverage=coverage,
        receipts=receipts, built_at='2026-11-03T00:00:00')


def test_bounded_column_batches_preserve_nulls_unicode_and_exact_amounts(tmp_path,monkeypatch):
    monkeypatch.setenv('TELCHI_DUCKDB_TEMP_DIRECTORY',str(tmp_path/'runtime_tmp'))
    rows=atomic.transform_rows('receivable_document',[
        dict(source_object_type='13',source_doc_entry=str(i),customer_code='Ñ-客户',
            document_total='123456789.123456',currency='BS',cancelled='N') for i in range(2051)],
        run_id='batch-test',source_as_of='2026-11-03')
    with cxc.scratch() as con:
        cxc._insert(con,'receivable_document',rows)
        assert con.execute('''SELECT count(*),count(DISTINCT atomic_id),min(customer_code),
            sum(cast(document_total AS DECIMAL(38,6))),count(cancel_date)
            FROM telchi.atomic.receivable_document''').fetchone()==(2051,2051,'Ñ-客户',
                __import__('decimal').Decimal('123456789.123456')*2051,0)


@pytest.mark.parametrize('prepared',['native_integer_transport'],indirect=True)
def test_native_integer_transport_reproduces_original_hashes_and_cells(prepared):
    component=produce(prepared)
    con=prepared[0]
    assert cxc.verify_component(con,component)
    assert con.execute('SELECT salesperson_code,payment_term_code FROM telchi.atomic.receivable_document').fetchone()==('-1','1')


@pytest.mark.parametrize('value',[1.25,float('nan'),float('inf'),float(2**31)])
def test_native_integer_transport_never_rounds_or_accepts_out_of_range(value):
    with pytest.raises(FoundationReaderError,match='native SAP INTEGER'):
        cxc._native_replay_rows('receivable_document',[dict(salesperson_code=value)])


def test_native_integer_transport_preserves_amounts_nulls_and_nvarchar():
    rows=[dict(installment_id=-99.0,reconciled_amount='1.2500',foreign_currency=None,
        participant_object_type='13')]
    result=cxc._native_replay_rows('reconciliation_participant',rows)[0]
    assert result==dict(installment_id=-99,reconciled_amount='1.2500',foreign_currency=None,
        participant_object_type='13')


def test_month_bounded_comparison_keeps_first_day_nulls_and_exact_cells():
    left=duckdb.connect(config={'threads':1})
    right=duckdb.connect(config={'threads':1})
    try:
        rows=[('1','2026-09-01','Ñ'),('2','2026-10-01T00:00:00','123.000001'),
              ('3','2026-11-30','x'),('4',None,'unknown')]
        for con in (left,right):
            con.execute('CREATE TABLE facts(id VARCHAR,document_date VARCHAR,value VARCHAR)')
            con.executemany('INSERT INTO facts VALUES (?,?,?)',rows)
        columns=['id','document_date','value']
        cxc._compare(left,right,'facts','facts',columns)
        right.execute("UPDATE facts SET value='123.000002' WHERE id='2'")
        with pytest.raises(FoundationReaderError,match='replay differs'):
            cxc._compare(left,right,'facts','facts',columns)
        right.execute("UPDATE facts SET value='123.000001',document_date='2026-11-01' WHERE id='2'")
        with pytest.raises(FoundationReaderError,match='date coverage differs'):
            cxc._compare(left,right,'facts','facts',columns)
    finally:
        left.close();right.close()


def test_disk_scratch_cleanup_on_failure_and_disk_budget(tmp_path,monkeypatch):
    from pathlib import Path
    from modules.telchi.runtime.resource_guard import SafeAbort
    root=tmp_path/'runtime_tmp'
    monkeypatch.setenv('TELCHI_DUCKDB_TEMP_DIRECTORY',str(root))
    with pytest.raises(RuntimeError,match='owned failure'):
        with cxc.scratch() as con:
            path=Path(con.execute("SELECT path FROM duckdb_databases() WHERE database_name='telchi'").fetchone()[0])
            assert path.is_file() and path.parent.parent==root
            with (path.parent/'owned-budget-probe').open('wb') as stream:
                stream.truncate(4*1024**3+1)
            with pytest.raises(SafeAbort,match='SCRATCH_DISK_BUDGET'):
                cxc._scratch_budget(con)
            raise RuntimeError('owned failure')
    assert not list(root.glob('cxc-replay-*'))


def test_cxc_promotion_loader_preserves_retained_stock_catalog_shape(prepared,tmp_path):
    from modules.telchi.datalake.sales_foundation_promotion import load_candidate
    *_,base,store=prepared
    # Real CURRENT has rich stock manifest fields but lossy legacy catalog columns.
    base.manifest['components']['oitw'].update(content_identity='sealed-stock',row_count=1400000)
    candidate=cxc.make_candidate(base,base.manifest['components'][cxc.NAME],update_run_id='loader-only')
    path=tmp_path/'candidate.json'
    path.write_text(json.dumps(candidate.as_row(),default=str))
    loaded=load_candidate(path)
    assert loaded.components==base.components
    assert loaded.component_hash()==candidate.component_hash()
    assert loaded.manifest==candidate.manifest


def test_exact_source_business_snapshot_and_retained_components(prepared, monkeypatch):
    con, snapshot, coverage, receipts, base, store = prepared
    component = produce(prepared)
    assert cxc.verify_component(con, component)
    row = con.execute('SELECT open_amount_local FROM telchi.business.receivable_settlement_status').fetchone()
    assert str(row[0]) == '800.000000'
    candidate = cxc.make_candidate(base, component, update_run_id='fixture-update')
    assert independent.validate_transition(store, candidate, base, base.manifest['components']) == candidate.manifest['components']
    assert cxc.snapshot_for(candidate.manifest) > snapshot
    assert cxc.snapshot_for(base.manifest) == snapshot
    from modules.telchi.datalake import receivables_collections_foundation as component_reader
    monkeypatch.setattr(component_reader, 'validate_manifest', lambda *args: candidate.manifest['components'])
    pinned = component_reader._resolve(candidate, reader_mode='EXPLICIT_PINNED_VALIDATION', store=store)
    assert pinned.snapshot_id == cxc.snapshot_for(candidate.manifest)
    assert str(con.execute('SELECT open_amount_local FROM ' + pinned.relation('receivable_settlement_status')).fetchone()[0]) == '800.000000'
    for name, entry in base.manifest['components'].items():
        if name != cxc.NAME:
            assert candidate.manifest['components'][name] == entry
    # Full persistence roundtrip must not invalidate Decimal historical evidence.
    persisted = json.loads(json.dumps(component, default=str))
    assert cxc.verify_component(con, persisted)
    # Old pin remains unchanged even if another update overwrites latest tables.
    pin = cxc.snapshot_for(candidate.manifest)
    con.execute('UPDATE telchi.business.receivable_settlement_status SET open_amount_local=0')
    assert str(con.execute(f'SELECT open_amount_local FROM telchi.business.receivable_settlement_status AT (VERSION => {pin})').fetchone()[0]) == '800.000000'
    assert cxc.verify_component(con, component)


@pytest.mark.parametrize('prepared,expected', [('reversal_before', '1000.000000'),
    ('reversal_after', '800.000000'), ('future_effect', '800.000000'), ('cancel_after', '800.000000'),
    ('native_before', '1000.000000'), ('native_after', '800.000000'), ('native_at_close', '1000.000000')], indirect=['prepared'])
def test_daily_close_materialization_reuses_historical_semantics(prepared, expected):
    con, _, _, _, base, store = prepared
    component = produce(prepared)
    assert cxc.verify_component(con, component)
    candidate = cxc.make_candidate(base, component, update_run_id='temporal')
    independent.validate_transition(store, candidate, base, base.manifest['components'])
    amount, cancelled = con.execute('SELECT open_amount_local, cancelled FROM telchi.business.receivable_settlement_status').fetchone()
    assert str(amount) == expected
    assert cancelled == 'N'
    assert component['history_succession']['historical_evidence']['board']['total_open_receivables'] == expected


@pytest.mark.parametrize('prepared,expected', [('invoice_before','0.000000'),
    ('invoice_at','0.000000'),('invoice_after','800.000000')],indirect=['prepared'])
def test_supplemental_invoice_dates_survive_physical_replay_and_receipt(prepared,expected):
    from pathlib import Path
    con,_,coverage,_,base,store=prepared
    component=produce(prepared)
    assert component['history_succession']['coverage']['invoice_cancellation_receipt']==coverage['invoice_cancellation_receipt']
    assert component['history_succession']['historical_evidence']['board']['total_open_receivables']==expected
    assert cxc.verify_component(con,json.loads(json.dumps(component,default=str)))
    candidate=cxc.make_candidate(base,component,update_run_id='dated-invoice')
    independent.validate_transition(store,candidate,base,base.manifest['components'])
    assert all(candidate.manifest['components'][k]==v for k,v in base.manifest['components'].items() if k!=cxc.NAME)
    path=Path(coverage['invoice_cancellation_receipt']['path'])
    path.write_bytes(path.read_bytes()+b'tampered')
    with pytest.raises(history.HistoricalCoverageError,match='RECEIPT_INVALID'):
        cxc.verify_component(con,component)


@pytest.mark.parametrize('mutation', ['gap','query','raw_hash','raw_manifest','zero','count','plan','normalized'])
def test_source_receipt_fail_closed(prepared, mutation):
    con, snapshot, coverage, receipts, *_ = prepared
    receipts = deepcopy(receipts)
    nonempty = next(r for r in receipts.values() if r['row_count'])
    if mutation == 'gap': receipts.pop(next(iter(receipts)))
    if mutation == 'query': nonempty['query_hash'] = '0'*64
    if mutation == 'raw_hash':
        from pathlib import Path
        with Path(nonempty['raw_manifest']['path']).open('ab') as f: f.write(b'corrupt')
    if mutation == 'raw_manifest': nonempty['raw_manifest']['manifest_hash'] = '0'*64
    if mutation == 'zero': next(r for r in receipts.values() if not r['row_count'])['status'] = 'EXTRACTED'
    if mutation == 'count': nonempty['atomic_row_count'] += 1
    if mutation == 'plan': nonempty['source_range']['from'] = '2026-10-01'
    if mutation == 'normalized':
        con.execute("UPDATE telchi.atomic.receivable_document SET document_total='999'")
        snapshot = con.execute("SELECT id FROM ducklake_current_snapshot('telchi')").fetchone()[0]
    with cxc.scratch() as target, pytest.raises((FoundationReaderError, history.HistoricalCoverageError)):
        cxc.replay_sources(con, snapshot=snapshot, coverage=coverage, receipts=receipts, target=target)


def test_unadvanced_source_rejected_and_observations_retained(prepared):
    from modules.telchi.datalake import operational_domains as observations
    _, _, _, _, base, store = prepared
    base.manifest['operational_observations'] = dict(contract=observations.CONTRACT, datasets={})
    component = produce(prepared)
    candidate = cxc.make_candidate(base, component, update_run_id='observation-retention')
    assert observations.observation_contract(candidate.manifest) == base.manifest['operational_observations']
    independent.validate_transition(store, candidate, base, base.manifest['components'])
    base.manifest['components'][cxc.NAME]['source_as_of'] = component['source_as_of']
    candidate = cxc.make_candidate(base, component, update_run_id='stale-cut')
    with pytest.raises(FoundationReaderError, match='cutoff did not advance'):
        independent.validate_transition(store, candidate, base, base.manifest['components'])


@pytest.mark.parametrize('field', ['permission', 'base_snapshot_id', 'facts_base_snapshot_id', 'sales_facts_revalidation'])
def test_reject_inherited_changes(prepared, field):
    _, _, _, _, base, store = prepared
    candidate = cxc.make_candidate(base, produce(prepared), update_run_id='bad-update')
    candidate.manifest[field] = 'MODIFIED'
    with pytest.raises(FoundationReaderError):
        independent.validate_transition(store, candidate, base, base.manifest['components'])


@pytest.mark.parametrize('mutation', ['sales','material_supply','fingerprint','snapshot','data'])
def test_reject_other_components_and_self_attestation(prepared, mutation):
    con, _, _, _, base, store = prepared
    component = produce(prepared)
    if mutation == 'fingerprint': component['component_fingerprint'] = '0'*64
    if mutation == 'snapshot': component['history_succession']['business_snapshot_id'] = 0
    if mutation == 'data':
        con.execute('UPDATE telchi.business.receivable_settlement_status SET open_amount_local=123')
        component['history_succession']['business_snapshot_id'] = con.execute("SELECT id FROM ducklake_current_snapshot('telchi')").fetchone()[0]
    candidate = cxc.make_candidate(base, component, update_run_id='bad-update')
    if mutation in {'sales', 'material_supply'}:
        candidate.manifest['components'][mutation]['publication_id'] = 'OTHER'
    with pytest.raises((FoundationReaderError, duckdb.Error)):
        independent.validate_transition(store, candidate, base, base.manifest['components'])


@pytest.mark.parametrize('failure', [None, 'source', 'business', 'receipt', 'interrupt'])
def test_cxc_atomic_publication_and_failed_update_preserves_current(prepared, failure, monkeypatch):
    from types import SimpleNamespace
    from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
    from modules.telchi.datalake.foundation_read_binding import make_binding
    from modules.telchi.datalake.foundation_reader import FoundationReader
    con, _, _, _, base, adapter_store = prepared
    component = produce(prepared)
    candidate = cxc.make_candidate(base, component, update_run_id='publication-test')
    store = FoundationPublicationStore(adapter_store.connection_factory)
    store.ensure_schema()
    store.create_candidate(base)
    con.execute(f'INSERT INTO {store.pointer_table} VALUES (1, ?, ?)', [base.foundation_publication_id, 'fixture'])
    def binding(publication):
        snapshot = con.execute("SELECT id FROM ducklake_current_snapshot('telchi')").fetchone()[0]
        return make_binding(publication, SimpleNamespace(commit_snapshot_id=snapshot, ducklake_snapshot_id=0), commercial=True)
    store.accredit_read_binding(base, binding(base))
    prior = store.read_binding(base.foundation_publication_id)
    if failure == 'source':
        next(r for r in component['history_succession']['receipts'].values() if r['row_count'])['query_hash'] = '0'*64
        candidate = cxc.make_candidate(base, component, update_run_id='publication-test')
    if failure == 'business':
        con.execute('UPDATE telchi.business.receivable_settlement_status SET open_amount_local=123')
        component['history_succession']['business_snapshot_id'] = con.execute("SELECT id FROM ducklake_current_snapshot('telchi')").fetchone()[0]
        candidate = cxc.make_candidate(base, component, update_run_id='publication-test')
    store.create_candidate(candidate)
    def accredit(selected, connection):
        superseded_base = store.get(base.foundation_publication_id)
        assert superseded_base.status == 'SUPERSEDED'
        independent.validate_transition(adapter_store, selected, superseded_base, superseded_base.manifest['components'])
        receipt = binding(selected)
        if failure == 'receipt': receipt['manifest_sha256'] = '0'*64
        if failure == 'interrupt': raise KeyboardInterrupt('isolated precommit interruption')
        return receipt
    if failure:
        with pytest.raises((FoundationReaderError, KeyboardInterrupt)):
            store.logical_commit(candidate.foundation_publication_id, accredit=accredit)
        assert store.current_pointer() == base.foundation_publication_id
        assert store.get(base.foundation_publication_id).status == 'CURRENT'
        assert store.read_binding(base.foundation_publication_id) == prior
        with pytest.raises(FoundationReaderError): store.read_binding(candidate.foundation_publication_id)
    else:
        store.logical_commit(candidate.foundation_publication_id, accredit=accredit)
        assert store.current_pointer() == candidate.foundation_publication_id
        assert store.get(base.foundation_publication_id).status == 'SUPERSEDED'
        receipt = store.read_binding(candidate.foundation_publication_id)
        assert receipt['components'][cxc.NAME] == json.loads(json.dumps(component, default=str))
        def forbidden_replay(*args, **kwargs):
            raise AssertionError('ordinary CxC reads must not replay physical source receipts')
        monkeypatch.setattr(cxc, 'verify_component', forbidden_replay)
        access = FoundationReader().resolve_on(con)
        assert access.foundation_publication_id == candidate.foundation_publication_id
        assert access.ducklake_snapshot_id == 0  # sales/stock snapshot untouched
        relation = access.receivables_collections('receivable_settlement_status')
        assert f'VERSION => {cxc.snapshot_for(candidate.manifest)}' in relation
        assert str(con.execute('SELECT open_amount_local FROM ' + relation).fetchone()[0]) == '800.000000'
        assert store.read_binding(base.foundation_publication_id) == prior
