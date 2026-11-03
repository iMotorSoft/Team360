"""Synthetic contract tests only: NOT real accounting certification."""
from datetime import date
from decimal import Decimal

import duckdb
import pytest
from modules.telchi.investigation.validation.datalake_accounting_reaccreditation_v1 import accounting_queries as q

SCOPE = ['TELCHI', 'fixture-only', 'synthetic']
START, END = date(2026,9,1), date(2026,10,1)


@pytest.fixture
def db():
    c = duckdb.connect(config={'threads': 2, 'memory_limit': '256MB'})
    c.execute(q.SCHEMA)
    for tid, day, kind, reversal in [('10','2026-09-01','13',None), ('11','2026-09-30','14','10'),('12','2026-10-01','30',None)]:
        c.execute('INSERT INTO journal VALUES (?,?,?,?,?,?,NULL,?,NULL,?,?)',
                  [*SCOPE, tid,day,day,kind,reversal,'UNCLASSIFIED'])
    for tid in ['10','11','12']:
        for line,account,branch,d1,d2 in [(0,'AR','B','C1','D2'),(1,'REV','C','C2','D3')]:
            c.execute('INSERT INTO journal_line VALUES (?,?,?,?,?,?,?,NULL,?,?,?,NULL,NULL,NULL)',
                      [*SCOPE,tid,line,account,account,branch,d1,d2])
            debit, credit = (Decimal('100'),Decimal('0')) if line == 0 else (Decimal('0'),Decimal('100'))
            if tid=='11': debit,credit=credit,debit
            for basis, currency, factor in [('LOCAL','BOB',Decimal('1')),('SYSTEM','USD',Decimal('0.14')),('FOREIGN','EUR',Decimal('0.12'))]:
                c.execute('INSERT INTO line_amount VALUES (?,?,?,?,?,?,?,?,?)',
                          [*SCOPE,tid,line,basis,currency,debit*factor,credit*factor])
    c.execute("INSERT INTO document_link VALUES (?,?,?,'OINV','1','12345','A','10','A','N')",SCOPE)
    c.execute("INSERT INTO document_link VALUES (?,?,?,'ORIN','2','12345','B','11','A','Y')",SCOPE)
    c.execute("INSERT INTO document_link VALUES (?,?,?,'OINV','3','999','A',NULL,'A','N')",SCOPE)
    yield c
    c.close()


def ledger(db):
    cur = db.execute(q.LEDGER,q.ledger_parameters(SCOPE,'AR','LOCAL','BOB',START,END))
    return [dict(zip([x[0] for x in cur.description],row)) for row in cur.fetchall()]


def test_invoice_preserves_emitter_accounting_branch_and_multiple_dimensions(db):
    rows = db.execute(q.INVOICE,[*SCOPE,'OINV','1']).fetchall()
    cols = [x[0] for x in db.description]
    data = [dict(zip(cols,r)) for r in rows]
    assert len(data)==6  # 2 original lines, 3 independent currency bases
    assert {x['documentary_branch_id'] for x in data}=={'A'}
    assert {x['accounting_branch_id'] for x in data}=={'B','C'}
    assert {x['dimension1'] for x in data}=={'C1','C2'}
    assert {x['dimension2'] for x in data}=={'D2','D3'}


def test_no_inference_when_transid_missing(db):
    rows=db.execute(q.UNLINKED,SCOPE).fetchall()
    assert len(rows)==1 and rows[0][4]=='3'


def test_balance_reconciles_each_currency_basis_without_netting_lines(db):
    rows=db.execute(q.BALANCE,SCOPE).fetchall()
    assert len(rows)==9 and all(r[-1]==0 for r in rows)
    db.execute("UPDATE line_amount SET debit=99 WHERE trans_id='10' AND line_id=0 AND basis='LOCAL'")
    assert any(r[-1]!=0 for r in db.execute(q.BALANCE,SCOPE).fetchall())


def test_diary_dates_are_half_open_and_multicurrency_separated(db):
    rows=db.execute(q.DIARY,[*SCOPE,START,END,'LOCAL','BOB']).fetchall()
    assert len(rows)==4
    assert len(db.execute(q.DIARY,[*SCOPE,START,END,'LOCAL','USD']).fetchall())==0


def test_no_historical_balance_without_certified_opening(db):
    row=ledger(db)[0]
    assert row['initial_balance'] is None and row['final_balance'] is None
    assert row['debit']==100 and row['credit']==100 and not row['balance_accredited']


def test_opening_plus_movements_and_month_end(db):
    db.execute("INSERT INTO opening VALUES (?,?,?,'AR','LOCAL','BOB','B',?,50,true)",[*SCOPE,START])
    row=ledger(db)[0]
    assert row['initial_balance']==50 and row['final_balance']==50
    assert row['balance_accredited']


def test_opening_wrong_grain_not_used(db):
    db.execute("INSERT INTO opening VALUES (?,?,?,'AR','SYSTEM','USD','B',?,50,true)",[*SCOPE,START])
    assert not ledger(db)[0]['balance_accredited']


def test_opening_only_branch_retained(db):
    db.execute("INSERT INTO opening VALUES (?,?,?,'AR','LOCAL','BOB','Z',?,25,true)",[*SCOPE,START])
    assert any(r['branch_id']=='Z' and r['final_balance']==25 for r in ledger(db))


def test_unaccredited_opening_not_used(db):
    db.execute("INSERT INTO opening VALUES (?,?,?,'AR','LOCAL','BOB','B',?,50,false)",[*SCOPE,START])
    assert not ledger(db)[0]['balance_accredited']


@pytest.mark.parametrize('scope',[['OTHER','fixture-only','synthetic'],['TELCHI','other','synthetic'],['TELCHI','fixture-only','other']])
def test_partition_isolation(db,scope):
    assert not db.execute(q.INVOICE,[*scope,'OINV','1']).fetchall()
    assert not db.execute(q.DIARY,[*scope,START,END,'LOCAL','BOB']).fetchall()


def test_invoice_and_credit_memo_not_confused_by_visible_number(db):
    assert db.execute(q.INVOICE,[*SCOPE,'OINV','1']).fetchone()[0]=='OINV'
    assert db.execute(q.INVOICE,[*SCOPE,'ORIN','2']).fetchone()[0]=='ORIN'
    assert not db.execute(q.INVOICE,[*SCOPE,'OINV','2']).fetchall()


def test_reversed_cancelled_lines_remain_in_diary(db):
    assert len(db.execute(q.DIARY,[*SCOPE,START,END,'LOCAL','BOB']).fetchall())==4
    assert db.execute(q.INVOICE,[*SCOPE,'ORIN','2']).fetchone()[4]=='Y'


def test_duplicate_original_line_rejected(db):
    with pytest.raises(duckdb.ConstraintException):
        db.execute('INSERT INTO journal_line SELECT * FROM journal_line LIMIT 1')


@pytest.mark.parametrize('side,expected',[('DEBIT_NORMAL',Decimal('12')),('CREDIT_NORMAL',Decimal('-12'))])
def test_account_presentation_requires_explicit_nature(side,expected):
    assert q.business_balance(Decimal('12'),side)==expected
    with pytest.raises(ValueError): q.business_balance(Decimal('12'),'UNKNOWN')


def test_monthly_and_branch_documents_are_not_duplicated(db):
    rows=db.execute(q.MONTHLY,[*SCOPE,'AR',START,END,'LOCAL','BOB']).fetchall()
    assert len(rows)==1 and rows[0][-2:]==(Decimal('100'),Decimal('100'))
    documents=db.execute(q.BRANCH_DOCUMENTS,[*SCOPE,START,END,'B']).fetchall()
    assert len(documents)==2
    assert not db.execute(q.BRANCH_DOCUMENTS,[*SCOPE,START,END,'A']).fetchall()


def test_documentary_and_accounting_branch_discrepancy_is_explicit(db):
    assert len(db.execute(q.BRANCH_DIFFERENCES,SCOPE).fetchall())==4
    db.execute('UPDATE document_link SET documentary_branch_id=NULL')
    assert not db.execute(q.BRANCH_DIFFERENCES,SCOPE).fetchall()


def test_unknown_branch_and_opening_null_safe_join(db):
    db.execute("UPDATE journal_line SET branch_id=NULL WHERE account='AR'")
    db.execute("INSERT INTO opening VALUES (?,?,?,'AR','LOCAL','BOB',NULL,?,50,true)",[*SCOPE,START])
    row=ledger(db)[0]
    assert row['branch_id'] is None and row['final_balance']==50


def test_bad_period_rejected():
    with pytest.raises(ValueError): q.ledger_parameters(SCOPE,'AR','LOCAL','BOB',END,START)
