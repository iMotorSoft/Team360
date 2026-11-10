"""Closing stock is ledger-backed native quantities; never November relabelling."""
from copy import deepcopy
import pytest
from modules.telchi.datalake import historical_stock as stock, operational_overlap as overlap, operational_domains as obs
from modules.telchi.datalake.foundation_publication import FoundationReaderError


def control(total='5'):
    return {'queries':{'stock_per_position_ledger_reconciliation':{'rows':[
        dict(union_positions=100,different_positions=0,max_difference='0',
            nonzero_without_ledger=0,nonzero_without_position=0,october_closing_quantity_control=total)]}}}


def table(con):
    con.execute('''CREATE TABLE closing(ItemCode VARCHAR,WhsCode VARCHAR,OnHand VARCHAR,ClosingRows VARCHAR,
        CurrentDifference VARCHAR,CurrentNet VARCHAR,CurrentOnHand VARCHAR,ClosingDate VARCHAR)''')
    con.execute("INSERT INTO closing VALUES ('P1','W1','5','2','0','7','7','2026-10-31')")


def test_closing_quantity_is_not_current_snapshot():
    with obs.database() as con:
        table(con)
        result=stock.validate_relation(con,'closing',control())
        assert result['historical_quantity_control']=='5.000000000000'
        assert result['closing_date']=='2026-10-31'
        assert result['reconstruction']=='SAP_BUSINESS_DATE_LEDGER_AS_OBSERVED_NOT_FROZEN_CLOSE'
        assert result['absent_position_semantics']=='NOT_OBSERVED_NOT_ZERO'
        assert result['commitments_and_open_orders_historical'] is False


@pytest.mark.parametrize('sql',[
    "UPDATE closing SET OnHand='7'",
    "INSERT INTO closing SELECT * FROM closing",
    "UPDATE closing SET ItemCode=NULL",
    "UPDATE closing SET WhsCode=''",
    "UPDATE closing SET CurrentDifference='1'",
    "UPDATE closing SET CurrentNet='8'",
    "UPDATE closing SET CurrentOnHand='bad'",
    "UPDATE closing SET ClosingRows='0'",
    "UPDATE closing SET ClosingDate='2026-11-01'",
])
def test_native_control_identity_and_historical_date_fail_closed(sql):
    with obs.database() as con:
        table(con); con.execute(sql)
        with pytest.raises(FoundationReaderError,match='historical stock native identity'):
            stock.validate_relation(con,'closing',control())


def test_negative_native_stock_preserved_not_hidden():
    with obs.database() as con:
        table(con); con.execute("UPDATE closing SET OnHand='-3'")
        assert stock.validate_relation(con,'closing',control('-3'))['historical_quantity_control']=='-3.000000000000'


@pytest.mark.parametrize('field',['different_positions','max_difference','nonzero_without_ledger','nonzero_without_position'])
def test_unreconciled_full_ledger_cannot_certify_closing(field):
    proof=control(); proof['queries']['stock_per_position_ledger_reconciliation']['rows'][0][field]='1'
    with obs.database() as con:
        table(con)
        with pytest.raises(FoundationReaderError,match='full SAP ledger does not reconcile'):
            stock.validate_relation(con,'closing',proof)


def test_stock_exposure_is_independent_and_explicit():
    assert 'stock' not in overlap.groups({})
    assert overlap.groups({'overlap':{'domains':['stock']}})['stock']==(stock.DATASET,)
    assert 'production_receipt' not in overlap.groups({'overlap':{'domains':['stock']}})['production']
    assert stock.SCOPE['closing_date']!=stock.SCOPE['end_exclusive']
    assert 'OITW' in stock.SQL and 'OINM' in stock.SQL and 'ClosingQty' in stock.SQL
