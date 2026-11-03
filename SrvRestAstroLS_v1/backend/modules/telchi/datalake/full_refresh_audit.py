"""Offline freshness/identity audit of explicit refresh receipts, not CURRENT.

Results describe captured candidates only. Date maxima never certify coverage.
"""
from pathlib import Path

from . import sales_incremental as durable
from .full_refresh_capture import verify_capture
from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb

DATE_FIELDS = {'production_order':'PostDate', 'production_issue':'DocDate',
    'purchase_order':'DocDate', 'purchase_order_line':'DocDate', 'purchase_receipt':'DocDate',
    'purchase_receipt_line':'DocDate', 'ap_invoice':'DocDate', 'ap_invoice_line':'DocDate',
    'inventory_movement':'DocDate', 'receivable_document':'document_date',
    'collection_payment':'payment_date', 'collection_allocation':'payment_date',
    'reconciliation_event':'reconciliation_date', 'reconciliation_participant':'reconciliation_date',
    'payment_method_component':'payment_date'}


def audit(root):
    root = Path(root)
    db = open_safe_duckdb(profile=DuckDBSafetyProfile(memory_limit='512MB', threads=2))
    report = dict(captured_datasets={}, relationships={}, publication=False,
                  observations='Source dates, statement observation windows and publication are distinct')
    try:
        for domain in sorted(p for p in root.iterdir() if p.is_dir()):
            for directory in sorted(p for p in domain.iterdir() if p.is_dir()):
                complete = directory/'complete.json'
                prefix = directory/'prefix-reconciliation.json'
                if complete.exists():
                    result = verify_capture(directory)
                    pages = result['pages']
                elif prefix.exists():
                    result = durable.read_json(prefix)
                    if durable.file_hash(directory/'intent.json') != result['original_intent_sha256']:
                        raise ValueError('PREFIX_INTENT_CHANGED')
                    paths = sorted(directory.glob('checkpoint-*.json'))
                    if [durable.file_hash(p) for p in paths] != result['checkpoint_hashes']:
                        raise ValueError('PREFIX_CHECKPOINTS_CHANGED')
                    pages = [durable.read_json(p) for p in paths]
                    if any(durable.file_hash(Path(p['path'])) != p['sha256'] for p in pages):
                        raise ValueError('PREFIX_FILES_CHANGED')
                else:
                    continue
                name = directory.name
                # Dataset names originate only in the bounded runner, not SQL input.
                if not name.replace('_','').isalnum():
                    raise ValueError('INVALID_DATASET')
                if not pages:
                    report['captured_datasets'][name] = dict(status=result['status'],rows=0)
                    continue
                files = [p['path'] for p in pages]
                file_sql = '[' + ','.join("'" + f.replace("'", "''") + "'" for f in files) + ']'
                db.execute(f'CREATE VIEW "{name}" AS SELECT * FROM read_parquet({file_sql}, union_by_name=true)')
                date_column = DATE_FIELDS.get(name)
                extrema = db.execute(f'SELECT MIN("{date_column}"),MAX("{date_column}") FROM "{name}"').fetchone() if date_column else (None,None)
                report['captured_datasets'][name] = dict(domain=domain.name, status=result['status'],
                    rows=result['row_count'], file_count=len(pages), receipt_sha256=durable.file_hash(complete if complete.exists() else prefix),
                    min_document_date=str(extrema[0]) if extrema[0] is not None else None,
                    max_document_date=str(extrema[1]) if extrema[1] is not None else None,
                    extraction_seconds=result.get('elapsed_seconds'),
                    source_before=result.get('source_before',result.get('captured_observation_start')),
                    source_after=result.get('source_after'), scope=result.get('semantic_scope'),
                    file_hashes=[dict(path=p['path'],sha256=p['sha256']) for p in pages],
                    coverage_complete=False if prefix.exists() else 'ONLY_DECLARED_STATEMENT_SCOPE; NOT_GLOBAL_CDC',
                    published=False)
        checks = {
            'stock_products': 'SELECT count(*) FROM stock S ANTI JOIN oitm P ON S."ItemCode"=P."ItemCode"',
            'stock_warehouses': 'SELECT count(*) FROM stock S ANTI JOIN owhs W ON S."WhsCode"=W."WhsCode"',
            'production_products': 'SELECT count(*) FROM production_order O ANTI JOIN oitm P ON O."ItemCode"=P."ItemCode"',
            'production_issue_products': 'SELECT count(*) FROM production_issue I ANTI JOIN oitm P ON I."ItemCode"=P."ItemCode" WHERE I."ItemCode" IS NOT NULL',
            'bom_header_for_lines': 'SELECT count(*) FROM bom_line L ANTI JOIN bom_header H ON L."Father"=H."Code"',
            'production_issue_orders': 'SELECT count(*) FROM production_issue I ANTI JOIN production_order O ON I."BaseEntry"=O."DocEntry" WHERE try_cast(I."BaseType" AS DECIMAL(18,6))=202',
            'purchase_supplier': 'SELECT count(*) FROM purchase_order O ANTI JOIN ocrd S ON O."CardCode"=S."CardCode" AND S."CardType"=\'S\'',
            'purchase_order_orphan_lines': 'SELECT count(*) FROM purchase_order_line L ANTI JOIN purchase_order H ON L."DocEntry"=H."DocEntry"',
            'purchase_receipt_orphan_lines': 'SELECT count(*) FROM purchase_receipt_line L ANTI JOIN purchase_receipt H ON L."DocEntry"=H."DocEntry"',
            'ap_invoice_orphan_lines': 'SELECT count(*) FROM ap_invoice_line L ANTI JOIN ap_invoice H ON L."DocEntry"=H."DocEntry"',
            'allocation_payment': 'SELECT count(*) FROM collection_allocation A ANTI JOIN collection_payment P ON A."payment_doc_entry"=P."source_doc_entry"',
            'reconciliation_event_for_participant': 'SELECT count(*) FROM reconciliation_participant P ANTI JOIN reconciliation_event E ON P."reconciliation_id"=E."reconciliation_id"',
        }
        for name, sql in checks.items():
            try:
                report['relationships'][name] = dict(unmatched_rows=db.execute(sql).fetchone()[0],
                    interpretation='DIRECT_NATIVE_KEYS_ONLY; unmatched is not proof that the SAP entity does not exist')
            except Exception as exc:
                report['relationships'][name] = dict(status='NOT_VERIFIED',error_type=type(exc).__name__)
        return report
    finally:
        db.close()
