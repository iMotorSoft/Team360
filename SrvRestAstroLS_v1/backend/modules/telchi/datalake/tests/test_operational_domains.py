"""Offline native evidence, no SAP, no shared catalog or publication."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from modules.telchi.datalake import operational_domains as op
from modules.telchi.datalake.foundation_publication import FoundationReaderError


def test_production_unknown_is_not_classified_from_code_or_hours():
    with op.database() as con:
        con.execute('''CREATE TABLE production_issue AS SELECT 1 AS DocEntry,0 AS LineNum,
            'R0001' AS ItemCode,202 AS BaseType,10 AS BaseEntry,DATE '2026-10-01' AS DocDate,
            'N' AS CANCELED,'5' AS Quantity,'HRS' AS unitMsr,NULL::VARCHAR AS UomCode''')
        con.execute("CREATE TABLE oitm AS SELECT 'MATERIAL' AS ItemCode")
        con.execute("CREATE TABLE bom_line AS SELECT 'OTHER' AS Code,290 AS Type")
        con.execute('CREATE TABLE production_order AS SELECT 10 AS DocEntry')
        result = op.production_reconciliation(con)
        assert len(result['unknown_lines']) == 1
        assert result['unknown_lines'][0]['ItemCode'] == 'R0001'
        assert not result['finished_goods_receipts_accredited']
        assert not result['bom_historical_effectivity']
        con.execute("INSERT INTO bom_line VALUES ('R0001',290)")
        result = op.production_reconciliation(con)
        assert result['unknown_lines'] == []
        assert result['classifications'] == {'CURRENT_BOM_RESOURCE_EVIDENCE_NOT_HISTORICAL_EFFECTIVITY': 1}
        con.execute('DELETE FROM production_order')
        result = op.production_reconciliation(con)
        assert result['issue_order_orphans'] == 1
        assert result['unresolved_referenced_orders'][0]['BaseEntry'] == 10


def purchasing_fixture(con, path):
    con.execute('''CREATE TABLE previous AS SELECT '10' AS doc_entry,'0' AS line_num,
        DATE '2026-09-19' AS doc_date,'N' AS canceled,'O' AS doc_status''')
    con.execute('COPY previous TO ' + op.literal(path) + ' (FORMAT PARQUET)')
    con.execute('''CREATE TABLE purchase_order AS SELECT 10 AS DocEntry,DATE '2026-09-30' AS DocDate,
        'N' AS CANCELED,'C' AS DocStatus''')
    con.execute('CREATE TABLE purchase_order_line AS SELECT 10 AS DocEntry,5 AS LineNum')
    for name in ['purchase_receipt','purchase_receipt_line','ap_invoice','ap_invoice_line']:
        con.execute('CREATE TABLE '+ name +' AS SELECT 1 AS DocEntry')


def test_missing_purchase_line_is_revision_not_fabricated_cancellation(tmp_path):
    with op.database() as con:
        path = tmp_path / 'old.parquet'
        purchasing_fixture(con, path)
        result = op.purchasing_reconciliation(con, [str(path)])
        assert result['missing_previous_line_keys'] == 1
        doc = result['documents'][0]
        assert doc['observed_lines'] == 1
        assert doc['observed_canceled'] == 'N'
        assert doc['finding'].startswith('OBSERVED_WHOLE_DOCUMENT_LINE_SET_REVISION')
        assert 'CAUSAL_AUDIT_UNAVAILABLE' in doc['finding']
        assert not result['historical_lines_deleted']
        assert con.execute('SELECT count(*) FROM previous').fetchone()[0] == 1


def test_empty_header_is_preserved_not_silently_dropped(tmp_path):
    with op.database() as con:
        path = tmp_path / 'old.parquet'
        purchasing_fixture(con, path)
        con.execute('DELETE FROM purchase_order_line')
        result = op.purchasing_reconciliation(con, [str(path)])
        assert len(result['headers_without_lines']) == 1
        assert result['documents'][0]['finding'] == 'OBSERVED_HEADER_WITHOUT_LINES; CAUSE_UNACCREDITED'


def test_orphan_purchase_line_rejected(tmp_path):
    with op.database() as con:
        path = tmp_path / 'old.parquet'
        purchasing_fixture(con, path)
        con.execute('INSERT INTO purchase_order_line VALUES (999,0)')
        with pytest.raises(FoundationReaderError, match='orphan document line'):
            op.purchasing_reconciliation(con, [str(path)])


def test_on_account_payment_survives_without_applications():
    with op.database() as con:
        con.execute('''CREATE TABLE collection_payment AS SELECT 1 AS source_doc_entry,'BS' AS currency,
            'N' AS cancelled,'Y' AS pay_no_document,'100' AS payment_total,'100' AS on_account_amount''')
        con.execute('CREATE TABLE collection_allocation(payment_doc_entry INTEGER,target_object_type VARCHAR)')
        con.execute('CREATE TABLE payment_method_component AS SELECT 1 AS payment_doc_entry')
        con.execute('CREATE TABLE reconciliation_event AS SELECT 1 AS reconciliation_id')
        con.execute('CREATE TABLE reconciliation_participant AS SELECT 1 AS reconciliation_id')
        result = op.collections_reconciliation(con)
        assert result['payments_without_allocations'] == 1
        assert result['on_account_payments_retained']
        assert not result['historical_balances_accredited']
        assert not result['current_global_aging_accredited']
        assert not result['absent_coverage_is_zero']
        con.execute("INSERT INTO collection_allocation VALUES (999,'13')")
        with pytest.raises(FoundationReaderError, match='native event link'):
            op.collections_reconciliation(con)


@pytest.mark.parametrize('manifest', [
    {'operational_observations': {}},
    {'candidate_kind': 'FOUNDATION_INDEPENDENT_FACTS_SUCCESSION_V1',
     'operational_observations': {'contract': op.CONTRACT}},
])
def test_unvalidated_observation_dispatch_rejected(manifest):
    with pytest.raises(FoundationReaderError, match='dispatch'):
        op.observation_contract(manifest)


def test_observation_candidate_loader_retains_lossy_catalog_hash(tmp_path):
    from modules.telchi.datalake.foundation_publication import FoundationPublication, ComponentReference
    from modules.telchi.datalake.sales_foundation_promotion import load_candidate
    catalog = {n:ComponentReference(n,n+'_old',source_as_of='2026-09-24')
               for n in ('reference','sales','credit_memo','oinm','oitw')}
    manifest = dict(foundation_publication_id='candidate',candidate_kind='FOUNDATION_INDEPENDENT_FACTS_SUCCESSION_V1',
        components={n:dict(ref.as_dict(),content_identity='rich-metadata-not-in-legacy-catalog') for n,ref in catalog.items()},
        independent_facts_succession={'contract':op.CONTRACT})
    candidate = FoundationPublication('candidate','run',reference_version='reference_old',components=catalog,manifest=manifest)
    path = tmp_path / 'candidate.json'
    op.durable.seal(path,candidate.as_row())
    assert load_candidate(path).as_row() == candidate.as_row()
    row = candidate.as_row()
    row['component_hash'] = 'invalid'
    changed = tmp_path / 'tampered.json'
    op.durable.seal(changed,row)
    with pytest.raises(ValueError, match='CANDIDATE_ROW_INTEGRITY'):
        load_candidate(changed)


@pytest.mark.parametrize('kind', ['FOUNDATION_INDEPENDENT_FACTS_SUCCESSION_V1','FOUNDATION_REFERENCE_REFRESH_V1','SALES_FACTS_TRANSITION_V1'])
def test_future_validated_successors_keep_observation_dispatch(kind):
    from modules.telchi.datalake.independent_facts_succession import CONTRACT as STOCK
    stable = dict(contract=op.CONTRACT)
    manifest = dict(candidate_kind=kind,operational_observations=stable,
        independent_facts_succession={'contract':STOCK},sales_facts_revalidation={})
    assert op.observation_contract(manifest) is stable
    assert op.observation_contract(manifest)['contract'] == op.CONTRACT


def test_historical_publication_has_no_observation_dispatch():
    assert op.observation_contract({}) is None
    with pytest.raises(FoundationReaderError, match='declared domain'):
        op.relation({}, 'collections', 'receivable_document')


def test_sealed_components_or_permission_changes_rejected():
    old = {'components': {'sales': {'publication_id': 'sales-old'}}, 'permissions': ['existing']}
    base = SimpleNamespace(manifest=old, foundation_publication_id='base',reference_version='r', components={'sales': 'old'})
    stable = dict(contract=op.CONTRACT,reference_version='r',base_manifest_sha256=op.durable.digest(old))
    proof = dict(contract=op.CONTRACT,base_manifest_sha256=op.durable.digest(old),replaced_components=[],
        retained_components_sha256=op.durable.digest(old['components']),observations_sha256=op.durable.digest(stable))
    manifest = deepcopy(old)
    manifest.update(candidate_kind='FOUNDATION_INDEPENDENT_FACTS_SUCCESSION_V1',operational_observations=stable,
                    independent_facts_succession=proof,base_foundation_publication_id='base')
    identity = 'foundation_' + op.durable.digest(dict(base='base',proof=proof))[:32]
    publication = SimpleNamespace(manifest=manifest,foundation_publication_id=identity,
        previous_foundation_publication_id='base',reference_version='r',components=base.components)
    manifest['permissions'] = ['expanded']
    with pytest.raises(FoundationReaderError, match='permissions changed'):
        op.validate_transition(publication, base, old['components'])


def test_decimal_basetype_audit_does_not_skip_real_order_orphans(tmp_path, monkeypatch):
    from modules.telchi.datalake import full_refresh_audit as audit_module
    root = tmp_path / 'capture'
    receipts = {}
    with op.database() as con:
        for name, sql in [
            ('production_issue', 'SELECT 1 AS DocEntry,202.0 AS BaseType,999 AS BaseEntry,DATE \'2026-01-01\' AS DocDate'),
            ('production_order', 'SELECT 10 AS DocEntry,DATE \'2026-01-01\' AS PostDate'),
        ]:
            directory = root / 'production' / name
            directory.mkdir(parents=True)
            path = directory / 'source.parquet'
            con.execute('COPY (' + sql + ') TO ' + op.literal(path) + ' (FORMAT PARQUET)')
            op.durable.seal(directory / 'complete.json', {})
            receipts[name] = dict(status='CAPTURE_RECONCILED_NOT_PUBLISHED',row_count=1,
                pages=[dict(path=str(path),sha256=op.durable.file_hash(path))])
    monkeypatch.setattr(audit_module, 'verify_capture', lambda directory: receipts[directory.name])
    report = audit_module.audit(root)
    assert report['relationships']['production_issue_orders']['unmatched_rows'] == 1


def test_native_unit_consumption_excludes_cancelled_unknown_and_orphan(tmp_path):
    op.durable.seal(tmp_path / 'cycle-plan.json', dict(year_start='2026-01-01',end_exclusive='2026-11-02'))
    with op.database() as con:
        con.execute('''CREATE TABLE production_issue AS SELECT 1 AS DocEntry,0 AS LineNum,
            'M1' AS ItemCode,202.0 AS BaseType,10 AS BaseEntry,DATE '2026-10-01' AS DocDate,
            'N' AS CANCELED,'5' AS Quantity,'KG' AS unitMsr,NULL::VARCHAR AS UomCode,'1' AS NumPerMsr''')
        con.execute("CREATE TABLE oitm AS SELECT 'M1' AS ItemCode")
        con.execute('CREATE TABLE production_order AS SELECT 10 AS DocEntry')
        for sql in [
            "INSERT INTO production_issue SELECT 2,0,'M1',202,10,DATE '2026-10-01','Y','100','KG',NULL,'1'",
            "INSERT INTO production_issue SELECT 3,0,'R1',202,10,DATE '2026-10-01','N','100','HRS',NULL,'1'",
            "INSERT INTO production_issue SELECT 4,0,'M1',202,999,DATE '2026-10-01','N','100','KG',NULL,'1'",
            "INSERT INTO production_issue SELECT 5,0,'M1',67,10,DATE '2026-10-01','N','100','KG',NULL,'1'",
            "INSERT INTO production_issue SELECT 6,0,'M1',202,10,DATE '2026-10-01','N','100',NULL,NULL,'1'",
            "INSERT INTO production_issue SELECT 7,0,'M1',202,10,DATE '2026-10-01','N','2','G',NULL,'1'",
        ]:
            con.execute(sql)
        report = op.build_observed_consumption(con, tmp_path)
        assert report['included_issue_lines'] == 2
        assert report['excluded_issue_lines'] == 5
        assert report['rows'] == 2
        assert con.execute('SELECT native_unit_msr,actual_consumption_qty FROM observed_material_actual_consumption ORDER BY 1').fetchall() == [('G','2.000000'),('KG','5.000000')]


@pytest.mark.parametrize('change', ['values','schema','bytes','duplicates'])
def test_replay_rejects_forged_output_even_with_new_hash(tmp_path, monkeypatch, change):
    monkeypatch.setattr(op.durable, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(op, 'GROUPS', {'purchasing': ('purchase_order',)})
    monkeypatch.setattr(op, 'NAMES', {'purchase_order'})
    monkeypatch.setattr(op, 'build_observed_consumption', lambda *_: None)
    directory = tmp_path / 'capture/purchasing/purchase_order'
    directory.mkdir(parents=True)
    op.durable.seal(directory / 'intent.json', {'plan': {'keys':['DocEntry'],'nullable_keys':False}})
    stage = tmp_path / 'staging/run'
    stage.mkdir(parents=True)
    raw, output = directory / 'raw.parquet', stage / 'output.parquet'
    with op.database() as con:
        con.execute('CREATE TABLE source AS SELECT 1 AS DocEntry,10 AS Quantity UNION ALL SELECT 2,20')
        con.execute('COPY source TO ' + op.literal(raw) + ' (FORMAT PARQUET)')
        sql = {
            'values':'SELECT DocEntry,30-Quantity AS Quantity FROM source',
            'schema':'SELECT cast(DocEntry AS VARCHAR) AS DocEntry,Quantity FROM source',
            'bytes':'SELECT * FROM source',
            'duplicates':'SELECT 1 AS DocEntry,10 AS Quantity UNION ALL SELECT 1,10',
        }[change]
        con.execute('COPY (' + sql + ') TO ' + op.literal(output) + ' (FORMAT PARQUET)')
        schema = [[r[0],r[1]] for r in con.execute('DESCRIBE source').fetchall()]
    captures = {'captured_datasets':{'purchase_order': {'file_hashes':[{'path':str(raw)}]}}}
    stable = dict(capture_root=str(tmp_path / 'capture'),limits=op.LIMITS,datasets={
        'purchase_order':dict(path=str(output),sha256=op.durable.file_hash(output),schema=schema,row_count=2)})
    if change == 'bytes':
        output.write_bytes(b'corrupted')
    with pytest.raises(FoundationReaderError):
        op.verify_datasets(stable,captures)
