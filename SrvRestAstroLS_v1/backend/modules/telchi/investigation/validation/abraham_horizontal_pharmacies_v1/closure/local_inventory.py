"""Small local-only evidence inventory; no HANA, private config or Foundation writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[8]
DATA = ROOT.parents[1] / 'lab/dataclient/telchi'
LEGACY = Path('/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience')
FIT = ROOT.parent / 'LlmFit/benchmarks/telchi/conversation_state_v1'


def fingerprint(path):
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return dict(path=str(path), size=path.stat().st_size, sha256=digest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing overwrite')
    out = dict(timestamp=datetime.now(timezone.utc).isoformat(), local_only=True,
               sap_accessed=False, threads=2, memory_limit='512MB', sources=[], fingerprints=[])
    with duckdb.connect(config={'threads': 2, 'memory_limit': '512MB'}) as c:
        for folder in ('DS', 'DS0'):
            path = LEGACY / folder / 'clientSB1.parq'
            schema = c.execute('DESCRIBE SELECT * FROM read_parquet(?)', [str(path)]).fetchall()
            stats = c.execute('''SELECT COUNT(*) row_count, COUNT(DISTINCT ClientCode) codes,
                COUNT(*) FILTER(WHERE ClientCode IS NULL) null_codes
                FROM read_parquet(?)''', [str(path)]).fetchall()
            # Classifier labels only; never names or account-level samples.
            properties = c.execute('''SELECT ClientSLPropertyCode, ClientSLPropertyName, COUNT(*) row_count
                FROM read_parquet(?) GROUP BY ALL ORDER BY row_count DESC''', [str(path)]).fetchall()
            out['sources'].append(dict(**fingerprint(path), schema=schema, stats=stats,
                                       property_dictionary=properties,
                                       limitation='Historical 2024 file metadata; not an authoritative 2026 DMS roster'))
        raw_root = DATA / 'raw/sap/table_extract'
        out['raw_table_extract_dictionary_paths'] = {
            table: [str(p) for p in raw_root.rglob(table + '.parquet')]
            for table in ('OCRD', 'NNM1', 'UFD1', 'OUSR')}
        for path in raw_root.rglob('OCRD.parquet'):
            schema = c.execute('DESCRIBE SELECT * FROM read_parquet(?)', [str(path)]).fetchall()
            out['sources'].append(dict(**fingerprint(path), schema=schema))
    files = [ROOT / 'data/reports/telchi/abraham_horizontal_pharmacies_v1/first_run' / name
             for name in ('spontaneous.json', 'independent.json', 'evaluation.json')]
    files += [ROOT / 'SrvRestAstroLS_v1/backend/modules/telchi' / path for path in (
        'assistant/luna.py', 'assistant/state_engine.py', 'assistant/handler.py', 'assistant/capabilities.py',
        'datalake/executive_sales.py', 'datalake/create_initial.py', 'datalake/update.py',
        'investigation/validation/sales_dimensions/channel_homologation.yaml',
        'investigation/validation/sales_dimensions/SALES_DIMENSIONS_FINAL_REPORT.md',
        'investigation/validation/users_audit/application_origin.py',
        'investigation/docs/telchi_order_delivery_source_discovery_v1_report.md')]
    files += [FIT / name for name in ('contracts/state.json', 'fixtures/TCS_001.json', 'domain/catalog.json')]
    out['fingerprints'] = [fingerprint(p) for p in files]
    out['limits'] = ['Bounded inventory, not proof that no DMS export exists elsewhere',
                     'No private files inspected; no credential discovery',
                     'Legacy property labels are candidates only; no pharmacy assignment or sales join',
                     'Prior HTTP and Foundation results are reused evidence, not a fresh live validation']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
