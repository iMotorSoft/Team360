"""Registry-led legacy schema review; never a blanket fact scan."""
import csv
import json
from modules.telchi.datalake.ducklake import DATA_ROOT
from modules.telchi.datalake.raw import file_hash
from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb
from .run_gate import OUTPUT

REASONS = {
    'saleSB1Product': 'No CANCELED or stable LineNum and no source-native unit/factor; invoice validity and event uniqueness cannot be revalidated.',
    'ncB1Product': 'No source-native credit unit/factor or BaseEntry/BaseLine; cannot close current credit conversion.',
    'movProductSB1': 'No explicit production-order lineage; TransType/name alone does not prove internal purpose.',
    'productTransform': 'Legacy CodProducto/CodInsumo keys and transform event semantics require validated crosswalk and cancellation/lineage; cannot identify SAP ItemCode by textual similarity.',
    'productSB1': 'Historical master has inventory unit, no sell flag or transaction conversion; current reference and keyed master take precedence.',
    'saleProduct': 'Legacy product/customer keys and SaleStatus fields require validated lineage and status contract; no direct SAP event equivalence assumed.',
    'mpRel': 'Product relationship is context, not actual consumption event.',
}


def main():
    registry_path = DATA_ROOT/'manifests/legacy/legacy_parquet_mirror_v1.csv'
    with registry_path.open() as f:
        registry = list(csv.DictReader(f))
    result = {'registry': str(registry_path), 'registry_sha256': file_hash(registry_path),
              'method': 'Manifest/schema discovery only; no blanket legacy fact scans', 'families': []}
    with open_safe_duckdb(profile=DuckDBSafetyProfile(threads=2, memory_limit='1GB')) as c:
        for family, reason in REASONS.items():
            entries = [r for r in registry if r['family'] == family]
            schemas = {}
            for r in entries:
                schemas.setdefault(r['destination_schema_fingerprint'], r)
            fields = []
            for r in schemas.values():
                path = DATA_ROOT/r['destination_relative_path']
                assert file_hash(path) == r['destination_sha256']
                fields.append({'path': str(path), 'sha256': r['destination_sha256'],
                               'fields': [x[0] for x in c.execute('DESCRIBE SELECT * FROM read_parquet(?)', [str(path)]).fetchall()]})
            result['families'].append({'family': family, 'files_in_registry': len(entries), 'schema_representatives': fields,
                                      'decision': 'CONTEXT_ONLY_NOT_SUFFICIENT_CLOSURE_EVIDENCE', 'reason': reason})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT/'legacy_metadata.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Legacy schema families verified:', len(result['families']))


if __name__ == '__main__':
    main()
