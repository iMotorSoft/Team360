"""Explicit local read-only reaccreditation. Never extracts SAP or publishes.

Run from backend with python -m modules.telchi.investigation.validation.
datalake_accounting_reaccreditation_v1.audit --output <new-report-directory>.
Only local DuckLake PostgreSQL metadata and sealed Parquet are read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.reference_compatibility import reference_projection

ROOT = Path(__file__).resolve().parents[7]
PREVIOUS = ROOT / 'data/reports/telchi/reference-v2-foundation-offline-final-r2'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def records(con, sql, params=None):
    cur = con.execute(sql, params or [])
    return [dict(zip([c[0] for c in cur.description], row)) for row in cur.fetchall()]


def run(output):
    output = Path(output).resolve()
    allowed = (ROOT / 'data/reports/telchi').resolve()
    if allowed not in output.parents or output.exists():
        raise ValueError('Requires a NEW report directory under data/reports/telchi')
    output.mkdir(parents=True)
    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, default=str) + '\n')
    old = json.loads((PREVIOUS / 'report.json').read_text())
    pointer = DATA_ROOT / 'manifests/reference_current.json'
    before = sha(pointer)
    c = DuckLakeConnector()
    if c.host not in ('localhost', '127.0.0.1', '::1') or not c.data_path.is_dir():
        raise RuntimeError('Only existing local catalog permitted')
    result = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'mode': 'LOCAL_READ_ONLY', 'hana_connections': 0,
              'threads': 2, 'memory_limit': '768MB', 'queries': {}}
    # Existing connector opens READ_ONLY; path already exists, no builder/store DDL.
    with c.session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='768MB'")
        a = FoundationReader(connector=c).resolve_on(con)
        save('access.json', a.as_dict())
        save('manifest.json', a.manifest)
        result['preflight'] = records(con, 'SELECT 1 AS local_catalog_ready')
        result['tables'] = records(con, "SELECT table_schema,table_name FROM information_schema.tables WHERE table_catalog='telchi' ORDER BY 1,2")
        result['schema'] = {}
        for component, table in [('sales', 'sales_document'), ('sales', 'sales_line'),
                                 ('credit_memo', 'credit_memo_document'), ('credit_memo', 'credit_memo_line'),
                                 ('oinm', 'inventory_movement'), ('oitw', 'inventory_balance'),
                                 ('receivables_collections', 'receivable_settlement_status')]:
            rel = a.relation(component, table)
            result['schema'][table] = records(con, 'DESCRIBE SELECT * FROM ' + rel)
            cols = {r['column_name'] for r in result['schema'][table]}
            date = next((x for x in ('doc_date', 'source_as_of') if x in cols), None)
            sql = 'SELECT count(*) AS rows' + (f', min({date}) AS first_date, max({date}) AS last_date' if date else '') + ' FROM ' + rel
            result['queries'][table] = {'sql': sql, 'result': records(con, sql)}
        result['sealed_datasets'] = {}
        for component, entry in a.manifest['components'].items():
            for dataset, ds in entry.get('datasets', {}).items():
                paths = ds.get('file_references', [])
                if not paths:
                    continue
                actual = [sha(path) for path in paths]
                checks = actual == ds.get('file_hashes')
                rows = 0
                schemas = []
                for path in paths:
                    rows += con.execute('SELECT count(*) FROM read_parquet(?)', [path]).fetchone()[0]
                    schemas.append(records(con, 'DESCRIBE SELECT * FROM read_parquet(?)', [path]))
                result['sealed_datasets'][component + '.' + dataset] = {
                    'hashes': actual, 'hash_match': checks, 'rows': rows,
                    'row_count_match': rows == ds.get('row_count'), 'schemas': schemas}
        result['reference_datasets'] = {}
        for path in sorted(a.reference_path.glob('*/part-*.parquet')):
            result['reference_datasets'][path.parent.name] = {
                'sha256': sha(path),
                'rows': con.execute('SELECT count(*) FROM read_parquet(?)', [str(path)]).fetchone()[0],
                'schema': records(con, 'DESCRIBE SELECT * FROM read_parquet(?)', [str(path)])}
        result['pointer'] = json.loads(pointer.read_text())
        result['foundation_manifest_matches_previous'] = a.manifest == json.loads((PREVIOUS / 'base-foundation-manifest.json').read_text())
        result['foundation'] = a.as_dict()
        # No publication methods called, including recovery/rollback.
        result['current_at_end'] = con.execute('SELECT foundation_publication_id FROM telchi.ops.foundation_current_v1 WHERE slot=1').fetchone()[0]
    save('local-audit.json', result)
    candidate = Path(old['candidate']['reference_path'])
    proof = reference_projection(Path(result['foundation']['reference_path']), candidate)
    save('reference-compatibility.json', proof)
    save('candidate-files.json', {str(p): sha(p) for root in (candidate, Path(old['candidate']['crosswalk_path'])) for p in sorted(root.rglob('*.parquet'))})
    # Historical source metadata is evidence of schema, not a published journal.
    history = json.loads((Path(__file__).parent.parent / 'financial_foundation/structure_discovery_v1.json').read_text())
    wanted = ['OJDT','JDT1','OACT','OINV','INV1','ORIN','RIN1','OCRD','OBPL','OPRC','OOCR','OCR1','ODIM']
    save('historical-accounting-source.json', {
        'evidence_date': history['generated_at_utc'],
        'evidence_sha256': sha(Path(__file__).parent.parent / 'financial_foundation/structure_discovery_v1.json'),
        'published_journal_rows_accredited': 0, 'published_journal_lines_accredited': 0,
        'historical_source_counts_not_current_lake_counts': history['gl_overview'],
        'document_to_ojdt_map': history['document_to_ojdt_map'],
        'schemas': {t: history['inventory']['columns'].get(t) for t in wanted}})
    save('preservation.json', {'reference_pointer_sha256_before': before,
        'reference_pointer_sha256_after': sha(pointer), 'reference_pointer_unchanged': before == sha(pointer),
        'foundation_id_unchanged': result['current_at_end'] == result['foundation']['foundation_publication_id'],
        'candidate_compatibility_proof_matches_previous': proof == json.loads((PREVIOUS / 'reference-compatibility.json').read_text()),
        'shared_writes_requested': 0, 'hana_connections': 0})
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    run(parser.parse_args().output)
