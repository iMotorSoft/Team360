"""Offline dependency evidence, NOT an exemption from Foundation publication gates.

Material Supply uses document date + item quantity inside its sealed demand
window (run_derivation._foundation_scalars). Due dates/status are not inputs.
Unchanged bounded projections prove this delta has no effect on that historical
window, not that Material Supply has been refreshed to October. Purchasing and
Receivables retain their original source/snapshot contracts, never rebound IDs.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from . import sales_incremental as inc


def demand_projection(documents, lines, start, end):
    dates={str(d['doc_entry']):str(d['doc_date'])[:10] for d in documents}
    quantities=defaultdict(Decimal)
    for line in lines:
        if start <= dates[str(line['doc_entry'])] <= end:
            # Same item-grain quantity sum as the existing derivation, no new
            # cancellation filter or commercial amount interpretation.
            item=line.get('item_code')
            if item:
                quantities[str(item)]+=Decimal(str(line.get('quantity') or 0))
    return {k:str(v.normalize()) for k,v in sorted(quantities.items()) if v}


def validate_physical_files(components, *, max_bytes=32*1024*1024):
    files={}
    for name in ('material_supply','purchasing'):
        for dataset,metadata in components[name]['datasets'].items():
            paths=metadata.get('file_references',[])
            hashes=metadata.get('file_hashes',[])
            if len(paths)!=len(hashes) or not paths:
                raise ValueError('missing sealed physical hashes')
            for path,expected in zip(paths,hashes):
                p=Path(path)
                if p.is_symlink():
                    raise ValueError('sealed dataset symlink')
                if path in files and files[path]['expected_sha256']!=expected:
                    raise ValueError('conflicting sealed hashes')
                files[path]=dict(component=name,dataset=dataset,bytes=p.stat().st_size,expected_sha256=expected)
    if sum(m['bytes'] for m in files.values())>max_bytes:
        raise RuntimeError('RESOURCE_BLOCKED_SEALED_FILE_BUDGET')
    for path,metadata in files.items():
        actual=inc.file_hash(Path(path))
        if actual!=metadata['expected_sha256']:
            raise ValueError('sealed dataset hash mismatch')
        metadata['actual_sha256']=actual
    return files


def revalidate_demand_on(connection, access, rows_by_domain):
    datasets=access.manifest['components']['material_supply']['datasets']
    path=datasets['material_equivalent_demand']['file_references'][0]
    windows=connection.execute('SELECT DISTINCT demand_window_start,demand_window_end FROM read_parquet(?) LIMIT 2',[path]).fetchall()
    if len(windows)!=1:
        raise ValueError('ambiguous sealed demand windows')
    start,end=[str(v)[:10] for v in windows[0]]
    date.fromisoformat(start); date.fromisoformat(end)
    proofs={}
    for domain,rows in rows_by_domain.items():
        candidate=inc.transform_capture(domain,rows,dict(source_as_of=inc.now(),extraction_id='offline-dependency-review'))
        tables={}
        for table,incoming in candidate.tables.items():
            ids=sorted({r['doc_entry'] for r in incoming})
            cur=connection.execute(f'SELECT * FROM {access.relation(domain,table)} WHERE source_system=? AND doc_entry IN ({",".join("?" for _ in ids)})',['SAP_B1_HANA',*ids])
            columns=[c[0] for c in cur.description]
            tables[table]=[dict(zip(columns,r)) for r in cur.fetchall()]
        doc_table='sales_document' if domain=='sales' else 'credit_memo_document'
        line_table='sales_line' if domain=='sales' else 'credit_memo_line'
        before=demand_projection(tables[doc_table],tables[line_table],start,end)
        after=demand_projection(candidate.tables[doc_table],candidate.tables[line_table],start,end)
        proofs[domain]=dict(before_sha256=inc.digest(before),after_sha256=inc.digest(after),
                            unchanged=before==after,affected_item_count=sum(before.get(k)!=after.get(k) for k in set(before)|set(after)),
                            bounded_documents=len(candidate.tables[doc_table]))
    return dict(window_start=start,window_end=end,source_snapshot=access.ducklake_snapshot_id,
                proofs=proofs,status='UNCHANGED_HISTORICAL_INPUTS' if all(p['unchanged'] for p in proofs.values()) else 'REBUILD_REQUIRED',
                coverage_not_advanced=True,
                publication_gate='STILL_REQUIRED; proof does not create a facts-transition envelope or rebind sealed dependencies')
