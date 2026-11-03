import shutil

import pytest

from modules.telchi.datalake import sales_reference_release as release
from modules.telchi.datalake import sales_incremental as inc


@pytest.mark.parametrize('columns,types', [
    (['text','qty','at','missing'], ['VARCHAR','DECIMAL(20,4)','TIMESTAMP WITH TIME ZONE','VARCHAR']),
    (['text'], ['VARCHAR']), ([], [])])
def test_fast_projection_retains_exact_typed_multiset(columns, types):
    from collections import Counter
    from datetime import datetime, timezone
    from decimal import Decimal
    rows = [dict(text=True, qty=Decimal('1.2500'), at=datetime(2026,1,1,tzinfo=timezone.utc)),
            dict(text='true', qty='1.25', at='2025-12-31T20:00:00-04:00')]
    result = release._projected_rows(rows, columns, types)
    if len(columns)>1:
        assert result == Counter({('true','1.25','2026-01-01T00:00:00+00:00',None):2})
    elif columns:
        assert result == Counter({('true',):2})
    else:
        assert result == Counter({():2})


def test_identity_projection_fast_path_still_checks_every_row(monkeypatch):
    cols=['source_system','source_native_id','qty']
    types=['VARCHAR','VARCHAR','DECIMAL(20,4)']
    before=[dict(source_system='SAP_HANA',source_native_id=str(n),qty='1.0000') for n in range(100)]
    after=[dict(r) for r in reversed(before)]
    calls=[]
    original=release._projected_rows
    def project(rows, columns, schema):
        calls.append(len(rows))
        return original(rows, columns, schema)
    monkeypatch.setattr(release,'_projected_rows',project)
    assert release._same_identity_rows(before,after,cols,types)
    assert calls==[0,0]
    after[0]['qty']='1'
    assert release._same_identity_rows(before,after,cols,types)
    assert calls[-2:]==[1,1]
    after[0]['qty']='2'
    assert not release._same_identity_rows(before,after,cols,types)
    with pytest.raises(ValueError,match='duplicate'):
        release._same_identity_rows(before,after+after[:1],cols,types)
    assert not release._same_identity_rows(before,after[:-1],cols,types)


def test_exact_bounded_query():
    sql = release.query('customer', ['C1', 'C2'])
    assert '"OCRD"' in sql and 'IN (?,?)' in sql
    assert 'C1' not in sql
    assert 'OINV' not in sql
    with pytest.raises(ValueError):
        release.query('product', [str(i) for i in range(26)])
    with pytest.raises(ValueError):
        release.query('customer', ['C1', 'C1'])


def customer():
    fields = release.FIELDS['customer'][2]
    return {**dict.fromkeys(fields), 'CardCode': 'C1', 'CardName': 'Accredited', 'CardType': 'C'}


class Source:
    def __init__(self):
        self.calls = 0
        self.query_log = []

    def query_read_only(self, name, sql, params):
        self.calls += 1
        self.query_log.append({'duration_ms': 1, 'cursor_closed': True, 'connection_closed': True})
        return [customer()]


def test_durable_resume_zero_queries(tmp_path):
    source = Source()
    keys = {'customer': ['C1'], 'product': []}
    first = release.capture_missing(tmp_path, keys, source)
    second = release.capture_missing(tmp_path, keys, source)
    assert first == second
    assert source.calls == 1
    response = tmp_path/'customer-00.response.json'
    response.write_text('[]')
    with pytest.raises(ValueError, match='hash mismatch'):
        release.capture_missing(tmp_path, keys, source)
    assert source.calls == 1


def test_resume_checks_missing_key_reconciliation(tmp_path):
    source=Source()
    keys={'customer':['C1'], 'product':[]}
    release.capture_missing(tmp_path,keys,source)
    receipt_path=tmp_path/'customer-00.receipt.json'
    receipt=inc.read_json(receipt_path)
    receipt['pending']=['C1']
    receipt_path.unlink()
    inc.seal(receipt_path,receipt)
    with pytest.raises(ValueError,match='missing-key reconciliation'):
        release.capture_missing(tmp_path,keys,source,resume_only=True)
    assert source.calls==1


def test_scheduler_remains_disabled():
    config=inc.read_json(release.Path(release.__file__).with_name('sales_refresh_scheduler.disabled.json'))
    assert config['enabled'] is False and config['installed'] is False
    assert config['schedule'] is None
    assert config['watermarks']['published_through_inclusive'] is None
    assert config['watermarks']['global_modification_watermark'] is None
    assert config['proposed_policy_not_extraction_entitlement']['retries']==0
    assert config['late_changes']['cdc_claim'] is False


def test_uncertain_request_never_retried(tmp_path):
    source = Source()
    keys = {'customer': ['C1'], 'product': []}
    release.capture_missing(tmp_path, keys, source)
    (tmp_path/'customer-00.receipt.json').unlink()
    with pytest.raises(RuntimeError, match='UNCERTAIN'):
        release.capture_missing(tmp_path, keys, source)
    assert source.calls == 1


def test_contradictory_or_incomplete_master_rejected():
    row = customer()
    row['CardType'] = 'S'
    with pytest.raises(ValueError, match='contradictory'):
        release.validate_response('customer', ['C1'], [row])
    with pytest.raises(ValueError):
        release.validate_response('customer', ['C1'], [{'CardCode': 'C1'}])
    assert release.validate_response('customer', ['C1'], []) == ['C1']


def test_budget_rejected_before_request(tmp_path):
    source = Source()
    with pytest.raises(ValueError):
        release.capture_missing(tmp_path, {'customer': [str(n) for n in range(46)], 'product': []}, source)
    assert source.calls == 0


def test_secondary_foreign_keys_are_not_fabricated(tmp_path):
    observed={**customer(), 'GroupNum':'-1'}
    cols=['source_system','source_native_id','customer_id','code','name','payment_term_id']
    merged,_,_=release.merge_accredited('customer',[observed],[],cols,[],
        ['source_system','source_native_id','canonical_id'],tmp_path)
    assert merged[0]['payment_term_id'] is None
    fields=release.FIELDS['product'][2]
    item={**dict.fromkeys(fields),'ItemCode':'P1','ItemName':'Known','InvntryUom':'KG'}
    cols=['source_system','source_native_id','canonical_product_id','item_code','canonical_name','inventory_uom_id']
    merged,_,_=release.merge_accredited('product',[item],[],cols,[],
        ['source_system','source_native_id','canonical_id'],tmp_path)
    assert merged[0]['inventory_uom_id'] is None


def test_read_only_verifier_never_extracts(tmp_path):
    source = Source()
    with pytest.raises(RuntimeError, match='NO_EXTRACTION_ALLOWED'):
        release.capture_missing(tmp_path, {'customer':['C1'], 'product':[]}, source, resume_only=True)
    assert source.calls == 0


@pytest.fixture
def appended(tmp_path, monkeypatch):
    monkeypatch.setattr(inc, 'DATA_ROOT', tmp_path)
    oldref=tmp_path/'reference/_versions/old'
    oldcw=tmp_path/'crosswalk/_versions/old'
    for entity,cfg in release.ENTITY_CONFIG.items():
        if entity not in release.FIELDS:
            continue
        native='old_'+entity
        cols=['source_system','source_native_id',cfg['canonical'],
              'code' if entity=='customer' else 'item_code',
              'name' if entity=='customer' else 'canonical_name']
        row=dict(zip(cols,['SAP_HANA',native,'id_'+native,native,'Historical']))
        release.write_parquet(oldref/cfg['ref']/'part-00000.parquet',cols,['VARCHAR']*len(cols),[row])
        cc=['source_system','source_native_id','canonical_id','confidence']
        release.write_parquet(oldcw/cfg['crosswalk']/'part-00000.parquet',cc,
                              ['VARCHAR']*3+['DECIMAL(20,12)'],
                              [dict(zip(cc,['SAP_HANA',native,'id_'+native,'1']))])
    source=Source()
    root=tmp_path/'raw/sap/sales-reference-release-v1/unit'
    observations,_=release.capture_missing(root,{'customer':['C1'],'product':[]},source)
    prepared=release.prepare(oldref,oldcw,observations,tmp_path/'stage')
    newref=tmp_path/'reference/_versions'/prepared['reference_version']
    newcw=tmp_path/'crosswalk/_versions'/prepared['reference_version']
    shutil.copytree(prepared['reference_path'],newref)
    shutil.copytree(prepared['crosswalk_path'],newcw)
    return oldref,newref,root


def test_append_proof_preserves_history_and_is_repeatable(appended):
    old,new,root=appended
    first=release.append_proof(old,new,root)
    assert first==release.append_proof(old,new,root)
    assert first['new_identities']=={'customer':1,'product':0}
    cols,types,rows=release.read_parquet_rows(new/'customers/part-00000.parquet')
    assert len(rows)==2
    assert next(r for r in rows if r['source_native_id']=='old_customer')['name']=='Historical'


@pytest.mark.parametrize('mutation',['old_name','new_name','crosswalk','missing_receipt','schema'])
def test_append_proof_negative_matrix(appended,mutation):
    old,new,root=appended
    target=new/'customers/part-00000.parquet'
    if mutation=='missing_receipt':
        (root/'customer-00.receipt.json').unlink()
    else:
        if mutation=='crosswalk':
            target=new.parents[2]/'crosswalk/_versions'/new.name/'customer_crosswalk/part-00000.parquet'
        cols,types,rows=release.read_parquet_rows(target)
        if mutation=='old_name': rows[0]['name']='Forged history'
        if mutation=='new_name':
            next(r for r in rows if r['source_native_id']=='C1')['name']='Invented'
        if mutation=='crosswalk': rows[0]['canonical_id']='wrong'
        if mutation=='schema': cols.append('unexpected');types.append('VARCHAR')
        target.unlink()
        release.write_parquet(target,cols,types,rows)
    with pytest.raises((ValueError,RuntimeError)):
        release.append_proof(old,new,root)
