"""Conservative source-gap regressions; no services or source access."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from modules.telchi.investigation.validation.product_commercial_semantics_source_gap_v1.rules import purpose_decision, supported_factor, unique_events, rectangular_rows


def evidence(sales=0, issues=0, bom=0):
    return {'sales_documents': sales, 'production_issue_lines': issues, 'bom_lines': bom,
            'sap_sell_item': 'Y', 'business_class': 'RAW_MATERIAL',
            'classification_status': 'VALIDATED', 'classification_basis': 'COMBINED'}


def test_history_and_consumption_resolve_mixed_with_existing_rule():
    result, gap, _, missing = purpose_decision(evidence(issues=3), historical_documents=2)
    assert result['commercial_purpose'] == 'MIXED'
    assert gap == 'RESOLVABLE_FROM_EXISTING_DATALAKE' and not missing


def test_isolated_sale_preserves_unknown_despite_internal_use():
    result, gap, _, _ = purpose_decision(evidence(issues=3), historical_documents=1)
    assert result is None and gap == 'TRUE_BUSINESS_UNKNOWN'


def test_bom_is_context_and_never_consumption():
    result, gap, reason, _ = purpose_decision(evidence(bom=3), historical_documents=2)
    assert result is None and gap == 'REQUIRES_DATALAKE_INGESTION'
    assert reason == 'MISSING_PRODUCTION_CONSUMPTION'


def test_repeated_commerce_cannot_prove_exclusive_purpose_without_history():
    result, gap, _, _ = purpose_decision(evidence(), historical_documents=20)
    assert result is None and gap == 'REQUIRES_DATALAKE_INGESTION'


def test_no_events_needs_business_definition_not_invented_use():
    result, gap, _, missing = purpose_decision(evidence(), historical_documents=0)
    assert result is None and gap == 'TRUE_BUSINESS_UNKNOWN' and missing


def conversion(factor='2', unit='BOX', item='A', target='U'):
    return {'item_code':item,'source_uom':unit,'inventory_uom_id':target,
            'conversion_factor':factor,'document_key':('INVOICE','1','0'),'file_hash':'verified-hash'}


def test_supported_exact_item_unit_target_and_factor():
    assert supported_factor('A','BOX','U',[conversion(),conversion()]) == (Decimal('2'),'UOM_RESOLVED_SUPPORTED')


@pytest.mark.parametrize('item,unit,target', [('B','BOX','U'),('A','UNI','U'),('A','BOX','OTHER')])
def test_supported_rejects_different_keys(item,unit,target):
    assert supported_factor(item,unit,target,[conversion()])[0] is None


def test_current_credit_missing_unit_cannot_borrow_invoice_unit():
    assert supported_factor('A',None,'U',[conversion()])[0] is None


def test_supported_factors_conflict_never_select_frequency_or_average():
    assert supported_factor('A','BOX','U',[conversion(),conversion(),conversion('3')]) == (None,'UOM_CONVERSION_CONFLICT')


def test_documentary_proof_required():
    row=conversion(); row.pop('file_hash')
    assert supported_factor('A','BOX','U',[row])[0] is None


def test_evidence_fanout_rejected():
    with pytest.raises(ValueError, match='fanout'):
        unique_events([{'doc':'1','line':'0'},{'doc':'1','line':'0'}], ['doc','line'])


def test_sparse_evidence_schema_roundtrip_keeps_canonical_hash(tmp_path):
    import duckdb
    from modules.telchi.datalake.product_commercial_semantics import row_digest
    rows = rectangular_rows([{'item':'A','unit_proof':'GR'}, {'item':'B','purpose_proof':'MIXED'}])
    source = tmp_path/'rows.json'
    source.write_text(json.dumps(rows))
    output = tmp_path/'rows.parquet'
    with duckdb.connect() as c:
        c.execute('SET threads=2')
        c.execute('CREATE TEMP TABLE evidence AS SELECT * FROM read_json_auto(?)', [str(source)])
        c.execute('COPY evidence TO ? (FORMAT PARQUET)', [str(output)])
        cur = c.execute('SELECT * FROM read_parquet(?)', [str(output)])
        columns = [d[0] for d in cur.description]
        recovered = [dict(zip(columns,r)) for r in cur.fetchall()]
    assert row_digest(rows)==row_digest(recovered)


def test_materialized_replay_and_cohorts_are_conserved():
    root=Path(__file__).resolve().parents[6]/'data/reports/telchi/product_commercial_semantics_source_gap_v1'
    if not (root/'report.json').exists():
        pytest.skip('real gate evidence has not been materialized')
    report=json.loads((root/'report.json').read_text())
    matrix=json.loads((root/'commercial_matrix.json').read_text())
    uom=json.loads((root/'uom_matrix.json').read_text())
    replay=json.loads((root/'replay.json').read_text())
    assert len(matrix)==720 and len({r['ItemCode'] for r in matrix})==720
    assert len({r['ItemCode'] for r in uom})==114
    assert report['FINAL_COMMERCIAL_PURPOSE_UNRESOLVED'] + report['COMMERCIAL_PURPOSE_RESOLVED_FROM_EXISTING_DATA']==720
    assert report['FINAL_UOM_UNRESOLVED'] + report['UOM_RESOLVED_EXACT_NEW'] + report['UOM_RESOLVED_SUPPORTED_NEW']==114
    assert report['UOM_FALSE_FANOUT']==report['COMMERCIAL_EVIDENCE_FALSE_FANOUT']==0
    assert report['FINAL_REPLAY_PRODUCTS']==808+len(replay['additional'])-len(replay['removed'])
    for row in matrix:
        assert row['reason'] and row['coverage'] and row['source_gap_class']
        if row['proposed_commercial_purpose']=='UNKNOWN': assert row['missing_evidence']
        if row['proposed_commercial_purpose']=='MIXED':
            assert row['commercial_evidence']==row['internal_evidence']=='YES'
            assert row['sales_doc_count']>=2 and row['production_issue_count']>0
