from decimal import Decimal

import duckdb
import pytest

from modules.telchi.datalake import receivables_collections_atomic as atomic
from modules.telchi.datalake import receivables_collections_history as history
from modules.telchi.datalake.foundation_read_binding import digest


@pytest.fixture
def historical(tmp_path):
    con = duckdb.connect(config={'threads':2})
    con.execute('LOAD ducklake')
    con.execute(f"ATTACH 'ducklake:{tmp_path}/history.ducklake' AS telchi (DATA_PATH '{tmp_path}/data')")
    atomic.ensure_tables(con)
    documents = [dict(source_object_type='13',source_doc_entry=str(i),customer_code='C1',document_date='2026-09-01',due_date=due,
                      document_total=amount,cancelled=cancelled,cancel_date=cancel_date,currency='BS')
                 for i,due,amount,cancelled,cancel_date in [(1,'2026-09-30','1000','N',None),
                    (2,'2026-10-01','500','N',None),(3,'2026-11-01','100','Y','2026-11-02'),
                    (4,'2026-09-01','70','Y','2026-10-25')]]
    events = [dict(reconciliation_id=str(i),reconciliation_date=day,cancelled='N',cancellation_of_reconciliation_id='0')
              for i,day in [(1,'2026-10-20'),(2,'2026-10-30'),(3,'2026-11-02')]]
    participants = [dict(reconciliation_id=str(i),source_line_id='0',reconciliation_date=day,
                         participant_object_type='13',participant_object_abs='1',is_credit='D',reconciled_amount=amount)
                    for i,day,amount in [(1,'2026-10-20','200'),(2,'2026-10-30','50'),(3,'2026-11-02','100')]]
    inputs = dict(receivable_document=documents,reconciliation_event=events,reconciliation_participant=participants,
        collection_payment=[dict(source_object_type='24',source_doc_entry='9',payment_date='2026-10-15',payment_total='900',cancelled='N',pay_no_document='Y')],
        collection_allocation=[dict(payment_doc_entry='9',target_object_type='13',target_doc_entry='1',allocated_amount='200')],
        payment_method_component=[],payment_term=[])
    for entity, rows in inputs.items():
        normalized = atomic.transform_rows(entity,rows,run_id='ISOLATED_FIXTURE',source_as_of='2026-11-03T00:00:00',built_at='2026-11-03T00:00:00')
        if normalized:
            columns=atomic.ENTITY_COLUMNS[entity]
            con.executemany(f'INSERT INTO telchi.atomic.{entity} VALUES ('+','.join('?' for _ in columns)+')',
                            [[None if r[c] is None else str(r[c]) for c in columns] for r in normalized])
    try:
        yield con
    finally:
        con.close()


def controls(con):
    snapshot=con.execute("SELECT id FROM ducklake_current_snapshot('telchi')").fetchone()[0]
    source=history.snapshot_fingerprint(con,snapshot)
    p=history.plan('2026-10-31','2026-11-04')
    segments={s['id']:dict(reconciled=True,normalized_rows=0) for s in p['segments']}
    for entity, metadata in source['entities'].items():
        last=[s['id'] for s in p['segments'] if s['entity']==entity][-1]
        segments[last]['normalized_rows']=metadata['row_count']
    return snapshot,dict(plan=p,complete=True,prefix_only=False,source_fingerprint=digest(source),
                         opening_balance_status='ACCREDITED',segments=segments)


def execute(con,coverage=None):
    snapshot, default=controls(con)
    return history.historical_snapshot(con,snapshot=snapshot,as_of='2026-10-31',coverage=coverage or default)


def test_historical_debt_is_not_collections_and_30_day_boundary(historical):
    result=execute(historical)
    # 1000 - 200 payment - 50 credit/reconciliation effect; Nov reduction excluded.
    assert result['board']['total_open_receivables']==Decimal('1350')
    assert result['over_30_days_amount']==Decimal('750')
    assert result['over_30_days_documents']==1
    assert result['board']['aging_1_30']==Decimal('500')
    assert result['board']['current_receivables']==Decimal('100')
    assert result['publication_ready'] is False


@pytest.mark.parametrize('mutation', ['prefix','gap','count','opening','source','plan','unreconciled'])
def test_incomplete_or_changed_history_rejected(historical,mutation):
    snapshot,c=controls(historical)
    if mutation=='prefix': c['prefix_only']=True
    if mutation=='gap': c['segments'].pop(next(iter(c['segments'])))
    if mutation=='count': next(iter(c['segments'].values()))['normalized_rows']+=1
    if mutation=='opening': c['opening_balance_status']='UNKNOWN'
    if mutation=='source': c['source_fingerprint']='0'*64
    if mutation=='plan': c['plan']['history_start']='2026-09-21'
    if mutation=='unreconciled': next(iter(c['segments'].values()))['reconciled']=False
    with pytest.raises(history.HistoricalCoverageError):
        history.historical_snapshot(historical,snapshot=snapshot,as_of='2026-10-31',coverage=c)


@pytest.mark.parametrize('reversal_date,expected', [('2026-10-25','1550'),('2026-11-02','1350')])
def test_native_reversal_effective_date(historical,reversal_date,expected):
    historical.execute("UPDATE telchi.atomic.reconciliation_event SET cancelled='Y' WHERE reconciliation_id='1'")
    rows=atomic.transform_rows('reconciliation_event',[dict(reconciliation_id='4',reconciliation_date=reversal_date,cancelled='N',cancellation_of_reconciliation_id='1')],run_id='fixture',source_as_of='2026-11-03T00:00:00')
    columns=atomic.ENTITY_COLUMNS['reconciliation_event']
    historical.executemany('INSERT INTO telchi.atomic.reconciliation_event VALUES ('+','.join('?' for _ in columns)+')',
                          [[None if r[c] is None else str(r[c]) for c in columns] for r in rows])
    snapshot,c=controls(historical)
    with pytest.raises(history.HistoricalCoverageError,match='SEMANTICS_UNACCREDITED'):
        history.historical_snapshot(historical,snapshot=snapshot,as_of='2026-10-31',coverage=c)
    c['cancellation_link_direction']='REVERSAL_TO_ORIGINAL'
    result=history.historical_snapshot(historical,snapshot=snapshot,as_of='2026-10-31',coverage=c)
    assert result['board']['total_open_receivables']==Decimal(expected)


def native_pair(con, day):
    con.execute("""UPDATE telchi.atomic.reconciliation_participant SET transaction_id='51914',
        transaction_row_id='0',account='1120101' WHERE reconciliation_id='1'""")
    con.execute("""UPDATE telchi.atomic.reconciliation_event SET cancelled='Y',
        cancellation_of_reconciliation_id='4', reconciliation_type='3',
        reconciliation_total='200',currency='BS',created_date='2026-10-20',created_timestamp='120000'
        WHERE reconciliation_id='1'""")
    con.execute("""INSERT INTO telchi.atomic.reconciliation_event SELECT * REPLACE(
        'reversal' AS atomic_id, '4' AS reconciliation_id, ? AS reconciliation_date,
        'C' AS cancelled,'1' AS cancellation_of_reconciliation_id,'7' AS reconciliation_type,
        ? AS created_date,'130000' AS created_timestamp)
        FROM telchi.atomic.reconciliation_event WHERE reconciliation_id='1'""", [day,day])
    con.execute("""INSERT INTO telchi.atomic.reconciliation_participant SELECT * REPLACE(
        'reversal-line' AS atomic_id,'4' AS reconciliation_id,? AS reconciliation_date,
        '-200' AS reconciled_amount) FROM telchi.atomic.reconciliation_participant
        WHERE reconciliation_id='1'""", [day])


@pytest.mark.parametrize('day,expected', [('2026-10-25','1550'),('2026-10-31','1550'),('2026-11-02','1350')])
def test_reciprocal_native_pair_daily_close(historical,day,expected):
    native_pair(historical,day)
    result=execute(historical)
    assert result['board']['total_open_receivables']==Decimal(expected)
    assert result['over_30_days_amount']==Decimal(expected)-600
    # The materialization adapter must select precisely the same effects.
    from modules.telchi.datalake.receivables_collections_succession import _CloseProjection
    rows=_CloseProjection(historical,'2026-10-31').execute('''SELECT reconciliation_id
        FROM telchi.atomic.reconciliation_participant ORDER BY reconciliation_id''').fetchall()
    assert rows==([('2',)] if day<='2026-10-31' else [('1',),('2',)])


@pytest.mark.parametrize('mutation', ['orphan','self','type','date','currency','amount','line','missing','normal_link','created','invalid_number','participant_date','duplicate','missing_identity'])
def test_native_pair_contradictions_fail_closed(historical,mutation):
    native_pair(historical,'2026-10-25')
    if mutation=='orphan': historical.execute("DELETE FROM telchi.atomic.reconciliation_event WHERE reconciliation_id='4'")
    if mutation=='self': historical.execute("UPDATE telchi.atomic.reconciliation_event SET cancellation_of_reconciliation_id='4' WHERE reconciliation_id='4'")
    if mutation=='type': historical.execute("UPDATE telchi.atomic.reconciliation_event SET reconciliation_type='3' WHERE reconciliation_id='4'")
    if mutation=='date': historical.execute("UPDATE telchi.atomic.reconciliation_event SET reconciliation_date='2026-10-19' WHERE reconciliation_id='4'")
    if mutation=='currency': historical.execute("UPDATE telchi.atomic.reconciliation_event SET currency='USD' WHERE reconciliation_id='4'")
    if mutation=='amount': historical.execute("UPDATE telchi.atomic.reconciliation_participant SET reconciled_amount='-199' WHERE reconciliation_id='4'")
    if mutation=='line': historical.execute("UPDATE telchi.atomic.reconciliation_participant SET transaction_id='other' WHERE reconciliation_id='4'")
    if mutation=='missing': historical.execute("DELETE FROM telchi.atomic.reconciliation_participant WHERE reconciliation_id='4'")
    if mutation=='normal_link': historical.execute("UPDATE telchi.atomic.reconciliation_event SET cancellation_of_reconciliation_id='1' WHERE reconciliation_id='2'")
    if mutation=='created': historical.execute("UPDATE telchi.atomic.reconciliation_event SET created_date='2026-10-19' WHERE reconciliation_id='4'")
    if mutation=='invalid_number': historical.execute("UPDATE telchi.atomic.reconciliation_participant SET reconciled_amount_system='bad' WHERE reconciliation_id IN ('1','4')")
    if mutation=='participant_date': historical.execute("UPDATE telchi.atomic.reconciliation_participant SET reconciliation_date='2026-10-24' WHERE reconciliation_id='4'")
    if mutation=='duplicate': historical.execute("INSERT INTO telchi.atomic.reconciliation_event SELECT * REPLACE('duplicate' AS atomic_id) FROM telchi.atomic.reconciliation_event WHERE reconciliation_id='4'")
    if mutation=='missing_identity': historical.execute("UPDATE telchi.atomic.reconciliation_participant SET transaction_id=NULL WHERE reconciliation_id IN ('1','4')")
    with pytest.raises(history.HistoricalCoverageError): execute(historical)


def test_native_generated_journal_self_reference_and_non_authoritative_seconds(historical):
    native_pair(historical,'2026-10-20')
    # Shape observed in SAP: original CreateTS can be seconds later than C.
    historical.execute("UPDATE telchi.atomic.reconciliation_event SET created_timestamp='140639' WHERE reconciliation_id='1'")
    historical.execute("UPDATE telchi.atomic.reconciliation_event SET created_timestamp='140636' WHERE reconciliation_id='4'")
    historical.execute("""INSERT INTO telchi.atomic.reconciliation_participant SELECT * REPLACE(
        atomic_id || '-journal' AS atomic_id, 'journal' AS source_line_id,
        '321' AS participant_object_type,reconciliation_id AS participant_object_abs,
        '10182922' AS transaction_id,'0' AS transaction_row_id)
        FROM telchi.atomic.reconciliation_participant WHERE reconciliation_id IN ('1','4')""")
    assert execute(historical)['board']['total_open_receivables']==Decimal('1550')
    # A reference to some other reconciliation is not a valid self-reference.
    historical.execute("UPDATE telchi.atomic.reconciliation_participant SET participant_object_abs='unrelated' WHERE reconciliation_id='4' AND participant_object_type='321'")
    with pytest.raises(history.HistoricalCoverageError,match='PARTICIPANTS_DIFFER'): execute(historical)


def test_ambiguous_cancel_date_blocks(historical):
    historical.execute("UPDATE telchi.atomic.receivable_document SET cancel_date=NULL WHERE source_doc_entry='4'")
    with pytest.raises(history.HistoricalCoverageError,match='INVALID_HISTORICAL_OBLIGATION'):
        execute(historical)


def invoice_receipt(con, tmp_path, day='2026-11-02', mutation=None):
    from modules.telchi.datalake.raw import write_raw
    from modules.telchi.runtime.config import DuckDBSafetyProfile
    import hashlib
    con.execute("UPDATE telchi.atomic.receivable_document SET cancelled='N',cancel_date=NULL")
    con.execute("""UPDATE telchi.atomic.receivable_document SET cancelled='Y',
        document_total_foreign='0',document_total_system='100',transaction_id='T1'
        WHERE source_doc_entry='1'""")
    con.execute("""INSERT INTO telchi.atomic.receivable_document SELECT * REPLACE(
        'cancellation-document' AS atomic_id,'5' AS source_doc_entry,'C' AS cancelled,
        ? AS document_date,? AS posting_date,'T5' AS transaction_id)
        FROM telchi.atomic.receivable_document WHERE source_doc_entry='1'""",[day,day])
    rows=[]
    for key,role,posting,pair,sign in [('1','Y','2026-09-01','5',1),('5','C',day,'1',-1)]:
        rows.append(dict(doc=key,role=role,posting=posting,tax='2026-09-01',created='2026-11-03',
            customer='C1',currency='BS',total='1000',foreign_total='0',system_total='100',
            transaction='T'+key,journal_posting=posting,journal_tax='2026-09-01',
            journal_created='2026-11-03',journal_type='13',journal_document=key,
            pair_min=pair,pair_max=pair,lines=2,linked_lines=2,
            ledger_min=posting,ledger_max=posting,ledger_lines=1,
            local_effect=str(sign*1000),foreign_effect='0',system_effect=str(sign*100)))
    if mutation: mutation(rows)
    return write_raw(root=tmp_path/'raw',segment_id='invoices',extraction_id='test',rows=rows,
        metadata=dict(contract=history.INVOICE_DATE_CONTRACT,params=['2022-03-31','2026-11-04'],
            source_as_of='2026-11-03T00:00:00',query_hash=hashlib.sha256(history.INVOICE_DATE_SQL.encode()).hexdigest()),
        profile=DuckDBSafetyProfile(threads=2,memory_limit='256MB'))


@pytest.mark.parametrize('day,expected', [('2026-10-25','670'),('2026-10-31','670'),('2026-11-02','1420')])
def test_invoice_accounting_date_not_creation_or_tax(historical,tmp_path,day,expected):
    receipt=invoice_receipt(historical,tmp_path,day)
    snapshot,c=controls(historical)
    c['invoice_cancellation_receipt']=receipt
    result=history.historical_snapshot(historical,snapshot=snapshot,as_of='2026-10-31',coverage=c)
    assert result['board']['total_open_receivables']==Decimal(expected)
    assert result['invoice_cancellation_lineage']['pairs']==1
    from modules.telchi.datalake.receivables_collections_succession import _CloseProjection,_derive
    projection=_CloseProjection(historical,'2026-10-31',c)
    # C is never reactivated into another positive invoice before its posting.
    rows=projection.execute('SELECT source_doc_entry,cancelled,cancel_date FROM telchi.atomic.receivable_document ORDER BY source_doc_entry').fetchall()
    assert ('5','C',__import__('datetime').date.fromisoformat(day)) in rows if day<='2026-10-31' else all(r[0]!='5' for r in rows)
    contract=history.snapshot_fingerprint(historical,snapshot)
    _derive(historical,'2026-10-31',contract,'2026-11-03',c)
    assert historical.execute("SELECT count(*) FROM telchi.business.receivable_settlement_status WHERE document_id='5' AND settlement_state<>'CANCELLED'").fetchone()[0]==0


@pytest.mark.parametrize('mutation', ['posting','ledger','amount','foreign','system','role','pair','duplicate','missing','lines','identity'])
def test_invoice_date_contradictions_fail_closed(historical,tmp_path,mutation):
    def change(rows):
        if mutation=='posting': rows[1]['journal_posting']='2026-11-01'
        if mutation=='ledger': rows[1]['ledger_min']='2026-11-01'
        if mutation=='amount': rows[1]['local_effect']='-999'
        if mutation=='foreign': rows[1]['foreign_effect']='1'
        if mutation=='system': rows[1]['system_effect']='-99'
        if mutation=='role': rows[1]['role']='Y'
        if mutation=='pair': rows[1]['pair_max']='2'
        if mutation=='duplicate': rows.append(dict(rows[1]))
        if mutation=='missing': rows.pop()
        if mutation=='lines': rows[1]['linked_lines']=1
        if mutation=='identity': rows[1]['journal_document']='other'
    receipt=invoice_receipt(historical,tmp_path,mutation=change)
    snapshot,c=controls(historical)
    c['invoice_cancellation_receipt']=receipt
    with pytest.raises(history.HistoricalCoverageError):
        history.historical_snapshot(historical,snapshot=snapshot,as_of='2026-10-31',coverage=c)


def test_invoice_date_physical_tampering_rejected(historical,tmp_path):
    from pathlib import Path
    receipt=invoice_receipt(historical,tmp_path)
    path=Path(receipt['path'])
    path.write_bytes(path.read_bytes()+b'tampered')
    snapshot,c=controls(historical)
    c['invoice_cancellation_receipt']=receipt
    with pytest.raises(history.HistoricalCoverageError,match='RECEIPT_INVALID'):
        history.historical_snapshot(historical,snapshot=snapshot,as_of='2026-10-31',coverage=c)


def test_old_capture_cannot_certify_future_close(historical):
    historical.execute("UPDATE telchi.atomic.receivable_document SET source_as_of='2026-09-28T00:00:00'")
    with pytest.raises(history.HistoricalCoverageError,match='SOURCE_OBSERVED_BEFORE_CLOSE'):
        execute(historical)
