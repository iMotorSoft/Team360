"""Offline validation of one private capture against local Reference Parquet only."""
from collections import Counter
import json
from pathlib import Path
import sys
import duckdb
from .capture import recover, save, digest
from modules.telchi.datalake.reference_update import physical_classification, validate_physical_rows


def analyze(root):
    if (root / 'sessions').exists():
        raise RuntimeError('multi_session_analysis_requires_consistency_accreditation')
    rows, seen, last = recover(root)
    operation = json.loads((root/'operation.json').read_text())
    data = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi')
    pointer_path = data/'manifests/reference_current.json'
    before = digest(pointer_path)
    pointer = json.loads(pointer_path.read_text())
    db = duckdb.connect(':memory:')
    try:
        db.execute('SET threads=1')
        db.execute("SET memory_limit='256MB'")
        products_path = str(Path(pointer['reference_path'])/'products/*.parquet')
        columns = {r[0] for r in db.execute('DESCRIBE SELECT * FROM read_parquet(?)',[products_path]).fetchall()}
        products = db.execute('SELECT canonical_product_id, source_native_id, item_code FROM read_parquet(?) WHERE source_system = ?', [products_path, 'SAP_HANA']).fetchall()
        crosswalk = db.execute('SELECT canonical_id, source_native_id FROM read_parquet(?) WHERE source_system = ?', [str(Path(pointer['crosswalk_path'])/'product_crosswalk/*.parquet'), 'SAP_HANA']).fetchall()
    finally:
        db.close()
    reference = {r[1]: r[0] for r in products}
    cw = {r[1]: r[0] for r in crosswalk}
    if len(reference) != len(products) or len(cw) != len(crosswalk):
        raise RuntimeError('duplicate_reference_identity')
    if any(native != item for _, native, item in products):
        raise RuntimeError('reference_itemcode_native_mismatch')
    matched = seen & reference.keys()
    mismatches = sum(reference[k] != cw.get(k) for k in matched)
    counts = Counter(row['U_FormaFarmac'] for row in rows)
    table = []
    labels = ['Ninguna','Líquido','Semisólido','Sólido','Medicamento','No corresponde']
    for code, label in zip(map(str, range(6)), labels):
        n = counts.get(code, 0)
        table.append(dict(code=code, category=label, articles=n, percent_of_capture=round(n/len(rows)*100,4) if rows else None))
    other = sum(n for k,n in counts.items() if k not in set(map(str,range(6))))
    table.append(dict(code='OTHER_OR_NULL', category='Sin determinar', articles=other, percent_of_capture=round(other/len(rows)*100,4) if rows else None))
    physical_rows = [dict(source_system='SAP_HANA', **physical_classification(r['U_FormaFarmac'], operation['finished_at'])) for r in rows]
    validate_physical_rows(physical_rows)
    statuses = Counter(r['physical_classification_status'] for r in physical_rows)
    assert all(r['physical_state'] is None for r in physical_rows if r['sap_forma_farmac_code']=='4')
    report = dict(
        verdict='PARTIAL', branch='feature/console-backend-core',
        reason=operation.get('stop_reason'), capture_directory=str(root),
        source='SAP_HANA.OITM', capture_interval=[operation['started_at'],operation['finished_at']],
        operation=operation, classification_table=table,
        percentages_scope='CAPTURED_PREFIX_ONLY_NOT_REPRESENTATIVE_OF_FULL_CATALOG',
        distinct_items=len(seen), duplicate_items=len(rows)-len(seen),
        checkpoint_validation='PASS', strict_order_and_no_overlap='PASS',
        physical_contract_validation='PASS', physical_status_counts=dict(statuses),
        unexpected_values=[{'value':k,'articles':n} for k,n in counts.items() if k is not None and str(k).strip() and k not in set(map(str,range(6)))],
        historical=dict(reference_version=pointer['current_reference_version'],
            reference_source_as_of=pointer['source_as_of'], reference_sap_products=len(reference),
            captured_matching_reference=len(matched), captured_new_to_reference=len(seen-reference.keys()),
            reference_not_observed_in_partial_capture=len(reference.keys()-seen),
            reference_key_coverage_percent=round(len(matched)/len(reference)*100,4),
            confirmed_absent_current_products='NOT_DETERMINABLE_PARTIAL_CAPTURE',
            canonical_id_mismatches=mismatches, reference_physical_columns_present='sap_forma_farmac_code' in columns,
            legacy_classification_changes='PENDING: no physical attributes in current Reference; local legacy product master lacks official U_FormaFarmac; no unvalidated mapping or inference',
            effective_business_dates_inferred=False),
        candidate_ready=False,
        controls_before_candidate=['Complete or explicitly approve partial scope under separate authorization',
            'Do not concatenate a later session without consistency accreditation',
            'Preserve original canonical IDs, all other columns and all crosswalks',
            'Resolve new SAP identities and validate full coverage',
            'Reconcile physical-only projection and existing derived-component compatibility',
            'Separate publication authorization and producer lock/resource guard'],
        safety=dict(sap_write_count=0, shared_data_writes=0, publication_count=0,
            reference_pointer_unchanged=before==digest(pointer_path),
            foundation_catalog_opened=False, retries=0, unrelated_processes_terminated=0),
        artifacts=dict(checkpoint_sha256=digest(root/'checkpoint.json'),operation_sha256=digest(root/'operation.json')))
    if mismatches:
        report['verdict'] = 'FAIL'
    save(root/'offline_report.json',report)
    print(json.dumps(report,ensure_ascii=False))
    return report


if __name__ == '__main__':
    analyze(Path(sys.argv[1]))
