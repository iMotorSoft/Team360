"""Offline continuity reconciliation and isolated candidate preparation.

Never changes Foundation metadata, CURRENT, Reference, SAP or trusted Atomic.
Complete raw windows are a capture guarantee, not an operational publication.
A durable build contains canonical upserts plus independent exact raw monetary
summaries. Existing semantic limits (notably credit line tax/UoM) are retained.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
import time

from . import sales_incremental as inc
from . import sales_continuity as capture
from .ducklake import DuckLakeConnector
from .foundation_reader import FoundationReader
from .foundation_publication import FoundationPublicationStore
from .foundation_manifest import validate_manifest
from .sales_incremental_review import compare_tables
from .sales_sealed_revalidation import demand_projection, validate_physical_files
from modules.telchi.runtime.resource_guard import ResourceGuard

TABLES = {'sales':('sales_document','sales_line'),
          'credit_memo':('credit_memo_document','credit_memo_line')}
CONTRACT='sales-continuity-offline-v1.0.0'


def query_rows(con, sql, params=None):
    cur=con.execute(sql,params or [])
    names=[c[0] for c in cur.description]
    return [dict(zip(names,row)) for row in cur.fetchall()]


def sql_literal(text):
    return "'"+str(text).replace("'","''")+"'"


def difference_predicate(con, incoming):
    from .sales_incremental_review import LINEAGE, NUMERIC
    columns=[r[0] for r in con.execute(f'DESCRIBE {incoming}').fetchall()]
    tests=[]
    for col in columns:
        if col in LINEAGE:
            continue
        n,o=f'n."{col}"',f'o."{col}"'
        if col in NUMERIC:
            n,o=f'cast({n} AS DECIMAL(38,12))',f'cast({o} AS DECIMAL(38,12))'
        tests.append(f'{n} IS DISTINCT FROM {o}')
    return ' OR '.join(tests)


def comparison_sql(con, incoming, previous, *, lines=False):
    """Canonical business comparison, ignoring ingestion lineage only."""
    keys=['source_system','doc_entry']+(['line_num'] if lines else [])
    join=' AND '.join(f'n."{k}"=o."{k}"' for k in keys)
    changed=difference_predicate(con,incoming)
    rows=con.execute(f'''SELECT CASE WHEN o.doc_entry IS NULL THEN 'new'
WHEN ({changed}) THEN 'modified' ELSE 'identical' END AS state,count(*)
FROM {incoming} n LEFT JOIN {previous} o ON {join} GROUP BY state''').fetchall()
    stats=dict(new=0,modified=0,identical=0,removed=0)
    stats.update({state:int(count) for state,count in rows})
    if lines:
        stats['removed']=int(con.execute(f'''SELECT count(*) FROM {previous} o
WHERE EXISTS (SELECT 1 FROM {incoming} n WHERE n.source_system=o.source_system AND n.doc_entry=o.doc_entry)
AND NOT EXISTS (SELECT 1 FROM {incoming} n WHERE {join})''').fetchone()[0])
    return stats


def import_canonical(con, root, commits, access, guard):
    """Stream <=100-document units; avoid retaining all raw history in Python."""
    totals=Counter()
    monetary={}
    for domain,tables in TABLES.items():
        for table in tables:
            con.execute(f'CREATE TEMP TABLE incoming_{table} AS SELECT * FROM {access.relation(domain,table)} LIMIT 0')
    for n,unit in enumerate(commits):
        assessment=guard.assess()
        if not assessment.allowed:
            raise RuntimeError('RESOURCE_BLOCKED_OFFLINE')
        rows=[r for key in unit['pages'] for r in inc.read_json(root/f'{key}.response.json')]
        if not rows:
            continue
        domain=unit['domain']
        manifest=dict(extraction_id=root.name,source_as_of=unit['committed_at'],
                      reference_version=access.foundation.reference_version,
                      reference_manifest_hash=inc.digest(access.manifest['components']['reference']))
        candidate=inc.transform_capture(domain,rows,manifest)
        for table,records in candidate.tables.items():
            # DuckDB reads the in-memory JSON parameter with explicit VARCHAR
            # types; no pandas/Arrow dependency or inference of native keys.
            columns={r[0]:'VARCHAR' for r in con.execute(f'DESCRIBE incoming_{table}').fetchall()}
            # read_json accepts a file, not JSON text. One build-owned transient
            # input is retained per committed unit for reproducibility.
            path=Path(con.execute("SELECT current_setting('temp_directory')").fetchone()[0])/f'{n:06}_{table}.json'
            if not path.exists():
                inc.seal(path,records)
            elif inc.read_json(path)!=records:
                raise ValueError('immutable canonical input mismatch')
            column_spec='{'+','.join(sql_literal(k)+':'+sql_literal(v) for k,v in columns.items())+'}'
            con.execute(f'INSERT INTO incoming_{table} BY NAME SELECT * FROM read_json(?,columns={column_spec})',[str(path)])
        headers={int(r['DocEntry']):r for r in rows}
        totals[domain+'_documents']+=len(headers)
        totals[domain+'_lines']+=len(rows)
        for row in headers.values():
            key=(domain,str(row['DocDate'])[:7],row['DocCur'],row['CANCELED'])
            bucket=monetary.setdefault(key,dict(documents=0,doc_total=Decimal(0),header_tax=Decimal(0)))
            bucket['documents']+=1
            bucket['doc_total']+=Decimal(str(row['DocTotal']))
            bucket['header_tax']+=Decimal(str(row['HeaderVatSum']))
    return dict(totals),[dict(domain=k[0],month=k[1],currency=k[2],cancelled=k[3],**{n:str(v) if isinstance(v,Decimal) else v for n,v in b.items()}) for k,b in sorted(monetary.items())]


def merge_sql(previous, incoming):
    # Replace the entire document keyset for BOTH header and line tables.
    return f'''SELECT o.* FROM {previous} o WHERE NOT EXISTS
(SELECT 1 FROM {incoming} n WHERE n.source_system=o.source_system AND n.doc_entry=o.doc_entry)
UNION ALL SELECT * FROM {incoming}'''


def integrity(con, domain, coverage=None):
    doc,line=TABLES[domain]
    checks={}
    for table,keys in ((doc,'source_system,doc_entry'),(line,'source_system,doc_entry,line_num')):
        checks[table+'_duplicate_keys']=int(con.execute(f'SELECT count(*) FROM (SELECT {keys} FROM incoming_{table} GROUP BY {keys} HAVING count(*)<>1)').fetchone()[0])
        checks[table+'_duplicate_ids']=int(con.execute(f'SELECT count(*)-count(DISTINCT atomic_id) FROM incoming_{table}').fetchone()[0])
    checks['orphan_lines']=int(con.execute(f'''SELECT count(*) FROM incoming_{line} l
ANTI JOIN incoming_{doc} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry''').fetchone()[0])
    checks['headers_without_lines']=int(con.execute(f'''SELECT count(*) FROM incoming_{doc} d
ANTI JOIN incoming_{line} l ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry''').fetchone()[0])
    scope = "o.doc_date>='2026-09-01' AND o.doc_date<'2026-10-30'"
    if coverage is not None:
        scope = '(' + ' OR '.join('(o.doc_date>='+sql_literal(w['start'])+' AND o.doc_date<'+sql_literal(w['end'])+')'
                                for w in coverage if w['domain']==domain) + ')'
    checks['unreturned_historical_documents']=int(con.execute(f'''SELECT count(*) FROM old_{doc} o
WHERE o.source_system='SAP_B1_HANA' AND ({scope})
AND NOT EXISTS(SELECT 1 FROM incoming_{doc} n WHERE n.source_system=o.source_system AND n.doc_entry=o.doc_entry)''').fetchone()[0])
    if any(checks.values()):
        raise ValueError('canonical integrity failure: '+json.dumps(checks))
    return checks


def document_changes(con, domain):
    """A line-only mutation or removed line makes the document MODIFIED."""
    doc,line=TABLES[domain]
    changed=[]
    for table in (doc,line):
        join='n.source_system=o.source_system AND n.doc_entry=o.doc_entry'
        if table==line:
            join+=' AND n.line_num=o.line_num'
        predicate=difference_predicate(con,'incoming_'+table)
        changed.append(f'''SELECT n.source_system,n.doc_entry FROM incoming_{table} n
LEFT JOIN old_{table} o ON {join} WHERE o.doc_entry IS NULL OR ({predicate})''')
    changed.append(f'''SELECT o.source_system,o.doc_entry FROM old_{line} o
WHERE EXISTS(SELECT 1 FROM incoming_{doc} d WHERE d.source_system=o.source_system AND d.doc_entry=o.doc_entry)
AND NOT EXISTS(SELECT 1 FROM incoming_{line} n WHERE n.source_system=o.source_system AND n.doc_entry=o.doc_entry AND n.line_num=o.line_num)''')
    return f'''WITH changed AS ({' UNION '.join(changed)})
SELECT n.source_system,n.doc_entry,n.doc_num,n.doc_date,n.canceled,n.currency,
CASE WHEN o.doc_entry IS NULL THEN 'new' WHEN c.doc_entry IS NOT NULL THEN 'modified' ELSE 'identical' END AS state
FROM incoming_{doc} n LEFT JOIN old_{doc} o ON n.source_system=o.source_system AND n.doc_entry=o.doc_entry
LEFT JOIN changed c ON n.source_system=c.source_system AND n.doc_entry=c.doc_entry'''


def demand_proof(con, access):
    path=access.manifest['components']['material_supply']['datasets']['material_equivalent_demand']['file_references'][0]
    windows=con.execute('SELECT DISTINCT demand_window_start,demand_window_end FROM read_parquet(?) LIMIT 2',[path]).fetchall()
    if len(windows)!=1:
        raise ValueError('ambiguous historical demand window')
    start,end=map(str,windows[0])
    proofs={}
    for domain,(doc,line) in TABLES.items():
        def projection(prefix):
            return query_rows(con,f'''SELECT l.item_code, sum(cast(l.quantity AS DECIMAL(38,12))) AS quantity
FROM {prefix}_{line} l JOIN {prefix}_{doc} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
WHERE d.doc_date>=? AND d.doc_date<=? AND l.item_code IS NOT NULL GROUP BY l.item_code ORDER BY l.item_code''',[start,end])
        before,after=projection('old'),projection('full')
        old_quantities={r['item_code']:r['quantity'] for r in before}
        new_quantities={r['item_code']:r['quantity'] for r in after}
        affected=sum(old_quantities.get(k,Decimal(0))!=new_quantities.get(k,Decimal(0)) for k in old_quantities.keys()|new_quantities.keys())
        proofs[domain]=dict(before_sha256=inc.digest(before),after_sha256=inc.digest(after),unchanged=before==after,
                            affected_items=affected)
    return dict(start=start,end=end,proofs=proofs,unchanged=all(p['unchanged'] for p in proofs.values()),
                historical_coverage_not_advanced=True,algorithm='Same DocDate+item+quantity projection as sealed derivation; no new cancellation filter')


def commercial_answers(con, identity):
    reports={}
    for domain,(doc,line) in TABLES.items():
        reports[domain+'_daily']=query_rows(con,f'''SELECT substr(doc_date,1,10) AS day,currency,
count(*) AS documents,sum(cast(doc_total AS DECIMAL(38,6))) AS documentary_total
FROM full_{doc} WHERE source_system='SAP_B1_HANA' AND doc_date>='2026-09-01' AND doc_date<'2026-10-30'
AND canceled='N' GROUP BY day,currency ORDER BY day,currency''')
        reports[domain+'_monthly']=query_rows(con,f'''SELECT substr(doc_date,1,7) AS month,currency,
count(*) AS documents,sum(cast(doc_total AS DECIMAL(38,6))) AS documentary_total
FROM full_{doc} WHERE source_system='SAP_B1_HANA' AND doc_date>='2026-09-01' AND doc_date<'2026-10-30'
AND canceled='N' GROUP BY month,currency ORDER BY month,currency''')
    reports['net_documentary_billing']=query_rows(con,'''WITH invoice AS (
SELECT substr(doc_date,1,7) AS month,currency,sum(cast(doc_total AS DECIMAL(38,6))) AS amount
FROM full_sales_document WHERE source_system='SAP_B1_HANA' AND doc_date>='2026-09-01' AND doc_date<'2026-10-30'
AND canceled='N' GROUP BY month,currency), credit AS (
SELECT substr(doc_date,1,7) AS month,currency,sum(cast(doc_total AS DECIMAL(38,6))) AS amount
FROM full_credit_memo_document WHERE source_system='SAP_B1_HANA' AND doc_date>='2026-09-01' AND doc_date<'2026-10-30'
AND canceled='N' GROUP BY month,currency)
SELECT coalesce(i.month,c.month) AS month,coalesce(i.currency,c.currency) AS currency,
coalesce(i.amount,0) AS invoice_doc_total,coalesce(c.amount,0) AS credit_doc_total,
coalesce(i.amount,0)-coalesce(c.amount,0) AS net_documentary_billing
FROM invoice i FULL JOIN credit c ON i.month=c.month AND i.currency=c.currency ORDER BY month,currency''')
    reports['october_peak_gross_billing_day']=query_rows(con,'''SELECT substr(doc_date,1,10) AS day,currency,
sum(cast(doc_total AS DECIMAL(38,6))) AS invoice_documentary_total
FROM full_sales_document WHERE source_system='SAP_B1_HANA' AND doc_date>='2026-10-01' AND doc_date<'2026-10-30'
AND canceled='N' GROUP BY day,currency
QUALIFY dense_rank() OVER(PARTITION BY currency ORDER BY invoice_documentary_total DESC)=1 ORDER BY currency,day''')
    reports['top_billed_customers']=query_rows(con,'''SELECT substr(doc_date,1,7) AS month,currency,card_code,
sum(cast(doc_total AS DECIMAL(38,6))) AS invoice_documentary_total,count(*) AS invoices
FROM full_sales_document WHERE source_system='SAP_B1_HANA' AND doc_date>='2026-09-01'
AND doc_date<'2026-10-30' AND canceled='N' GROUP BY month,currency,card_code
QUALIFY row_number() OVER(PARTITION BY month,currency ORDER BY invoice_documentary_total DESC,card_code)<=10
ORDER BY month,currency,invoice_documentary_total DESC,card_code''')
    reports['top_products_line_amount']=query_rows(con,'''SELECT substr(d.doc_date,1,7) AS month,l.currency,l.item_code,
sum(cast(l.line_total AS DECIMAL(38,6))) AS invoice_line_amount
FROM full_sales_line l JOIN full_sales_document d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
WHERE d.source_system='SAP_B1_HANA' AND d.doc_date>='2026-09-01' AND d.doc_date<'2026-10-30'
AND d.canceled='N' GROUP BY month,l.currency,l.item_code
QUALIFY row_number() OVER(PARTITION BY month,l.currency ORDER BY invoice_line_amount DESC,l.item_code)<=10
ORDER BY month,l.currency,invoice_line_amount DESC,l.item_code''')
    reports['equivalent_periods']=query_rows(con,'''WITH amounts AS (
SELECT substr(doc_date,1,7) AS month,currency,CASE WHEN substr(doc_date,9,2)<='29' THEN 'days_01_29' ELSE 'day_30' END AS period,
sum(cast(doc_total AS DECIMAL(38,6))) AS gross_documentary_billing
FROM full_sales_document WHERE source_system='SAP_B1_HANA' AND doc_date>='2026-09-01' AND doc_date<'2026-10-30' AND canceled='N'
GROUP BY month,currency,period) SELECT * FROM amounts ORDER BY month,currency,period''')
    reports['metadata']=dict(identity=identity,status='ISOLATED_OFFLINE_NOT_PUBLISHED',cutoff='2026-10-29',
        coverage='Business-date daily windows; per-query source observation, not transactional remote snapshot',
        metric='DocTotal of active invoices; credit DocTotal reported separately; net documentary billing is invoice minus credit, not pre-tax revenue',
        warnings=['No currency conversion','No incompatible quantity sums','Billed customer only, not classified commercial customer',
                  'Line amounts are not asserted equal to DocTotal; credit line taxes/discounts remain unaccredited',
                  'No conversational capability enabled; permissions unchanged','Other Foundation components retain historical cutoffs'])
    return reports


def build(root, destination):
    guard=ResourceGuard(temp_directory=destination.parent.resolve())
    if not guard.assess().allowed:
        raise RuntimeError('RESOURCE_BLOCKED_OFFLINE')
    with inc.locked(root):
        p,receipts,commits,cursors,finished=capture.recover(root)
    if len(finished)!=len(p['windows']):
        raise RuntimeError('INCOMPLETE_CAPTURE_NO_COMPLETE_CANDIDATE')
    allowed_capture=(inc.DATA_ROOT/'raw/sap'/p['contract']).resolve()
    allowed_output=(inc.DATA_ROOT/'staging'/p['contract']).resolve()
    if root.resolve().parent!=allowed_capture or destination.resolve().parent!=allowed_output:
        raise ValueError('capture/build destinations must remain in contract-owned DATA_ROOT')
    destination.mkdir(mode=0o700,exist_ok=False)
    inc.sync_dir(destination.parent)
    temp=destination/'canonical_inputs';temp.mkdir()
    connector=DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=1');con.execute("SET memory_limit='512MB'")
        con.execute(f'SET temp_directory={sql_literal(temp)}');con.execute("SET max_temp_directory_size='2GB'")
        access=FoundationReader(connector).resolve_on(con)
        @contextmanager
        def same(): yield con
        store=FoundationPublicationStore(same)
        base=store.get(access.foundation_publication_id)
        validate_manifest(store,base)
        incremental = p.get('base') is not None
        if incremental and (p['base']!=base.foundation_publication_id or p['base_manifest_sha256']!=inc.digest(base.manifest)):
            raise RuntimeError('CURRENT_CHANGED_INCREMENTAL_RECONCILIATION_REQUIRED')
        inc.seal(destination/'base-manifest.json',base.manifest)
        for domain,tables in TABLES.items():
            for table in tables:
                con.execute(f'CREATE TEMP VIEW old_{table} AS SELECT * FROM {access.relation(domain,table)}')
        totals,monetary=import_canonical(con,root,commits,access,guard)
        stats,checks,datasets={}, {}, {}
        for domain,tables in TABLES.items():
            checks[domain]=integrity(con,domain,p['windows'] if incremental else None)
            stats[domain]={}
            for table in tables:
                incoming,previous=f'incoming_{table}',f'old_{table}'
                stats[domain][table]=comparison_sql(con,incoming,previous,lines=table.endswith('_line'))
                con.execute(f'CREATE TEMP VIEW full_{table} AS {merge_sql(previous,incoming)}')
                path=destination/f'{table}.parquet'
                con.execute(f'COPY (SELECT * FROM full_{table} ORDER BY source_system,doc_entry'+(',line_num' if table.endswith('_line') else '')+f') TO {sql_literal(path)} (FORMAT PARQUET,COMPRESSION ZSTD)')
                with path.open('rb') as stream: os.fsync(stream.fileno())
                columns=con.execute(f'DESCRIBE full_{table}').fetchall()
                datasets[table]=dict(path=str(path),sha256=inc.file_hash(path),row_count=con.execute(f'SELECT count(*) FROM full_{table}').fetchone()[0],schema=[list(r[:2]) for r in columns])
            con.execute(f'CREATE TEMP VIEW changes_{domain} AS {document_changes(con,domain)}')
            path=destination/f'{domain}_document_changes.parquet'
            con.execute(f'COPY (SELECT * FROM changes_{domain} ORDER BY doc_entry) TO {sql_literal(path)} (FORMAT PARQUET,COMPRESSION ZSTD)')
            with path.open('rb') as stream: os.fsync(stream.fileno())
            stats[domain]['whole_document_states']=query_rows(con,f'SELECT state,canceled,count(*) AS documents FROM changes_{domain} GROUP BY state,canceled ORDER BY state,canceled')
            stats[domain]['document_change_evidence']=dict(path=str(path),sha256=inc.file_hash(path))
        dependency=demand_proof(con,access)
        physical=validate_physical_files(access.manifest['components'])
        material_revalidation=None
        if not dependency['unchanged']:
            from .sales_material_revalidation import replay
            try:
                material_revalidation=replay(con,access,destination,start=dependency['start'],end=dependency['end'])
            except (FileNotFoundError,RuntimeError,ValueError) as exc:
                material_revalidation=dict(status='REPLAY_BLOCKED',reason=type(exc).__name__,detail=str(exc))
        missing={}
        for dataset,table,key,reference_key in [('customers','sales_document','card_code','code'),('products','sales_line','item_code','item_code'),
                                                  ('credit_customers','credit_memo_document','card_code','code'),('credit_products','credit_memo_line','item_code','item_code')]:
            ref='customers' if 'customers' in dataset else 'products'
            missing[dataset]=query_rows(con,f'''SELECT DISTINCT n.{key} AS source_key FROM incoming_{table} n
WHERE n.{key} IS NOT NULL AND NOT EXISTS(SELECT 1 FROM read_parquet(?) r WHERE r.source_system='SAP_HANA' AND r.{reference_key}=n.{key}) ORDER BY source_key''',[str(access.reference(ref))])
        report=dict(contract=CONTRACT,status='OFFLINE_RECONCILED_NOT_FOUNDATION_CANDIDATE',
                    base_publication=access.foundation_publication_id,base_snapshot=access.ducklake_snapshot_id,
                    derivation_snapshot=access.manifest_base_snapshot_id,reference_version=base.reference_version,
                    capture_plan_sha256=inc.file_hash(root/'plan.json'),coverage=p['windows'],counts=totals,
                    canonical_delta=stats,integrity=checks,raw_money=monetary,datasets=datasets,
                    material_supply=dependency,material_revalidation=material_revalidation,sealed_files=physical,reference_missing=missing,
                    components_preserved=sorted(base.manifest['components']),
                    receivables='Historical source_as_of/snapshot preserved; no October payment/settlement revalidation claimed',
                    publication_authorized=False,current_unchanged=True,global_change_watermark=None,
                    blockers=[])
        if not dependency['unchanged'] and (not material_revalidation or material_revalidation['status']!='REPLAY_PASS'):
            report['blockers'].append('MATERIAL_SUPPLY_HISTORICAL_INPUTS_CHANGED_REBUILD_REPLAY_REQUIRED')
        if any(missing.values()):
            report['blockers'].append('REFERENCE_KEYS_UNRESOLVED_NO_REFERENCE_REFRESH_AUTHORIZED')
        if incremental:
            report['incremental_plan']=p
            from .sales_refresh_cycle import verify_cycle_money
            verify_cycle_money(con,report)
        report['commercial_answers']=commercial_answers(con,destination.name)
        if store.current_pointer()!=base.foundation_publication_id:
            raise RuntimeError('CURRENT_CHANGED_DURING_OFFLINE_BUILD')
        inc.seal(destination/'reconciliation.json',report)
        inc.sync_dir(destination)
        return report


def prepare_isolated_foundation(capture_root, destination):
    """Real files and pinned sources; pointer fault matrix in isolated metadata.

    The metadata catalog is in memory, not a production DuckLake publication.
    Its snapshot resolver is explicitly fixture-bound to the proven source
    snapshot: no new production commit snapshot is claimed or manufactured.
    """
    from copy import deepcopy
    from . import sales_facts_transition as transition
    from .foundation_publication import READY_TO_COMMIT, SUPERSEDED, CommitFaultPoint
    from .material_supply_candidate import resolve_current_material_supply
    from .receivables_collections_foundation import resolve_current as resolve_receivables
    report_path=destination/'reconciliation.json'
    report=inc.read_json(report_path)
    if report['blockers']:
        result=dict(status='BLOCKED',blockers=report['blockers'],candidate=None,current_unchanged=True)
        inc.seal(destination/'foundation-gate.json',result)
        return result
    guard=ResourceGuard(temp_directory=destination.resolve())
    if not guard.assess().allowed:
        raise RuntimeError('RESOURCE_BLOCKED_ISOLATED_GATE')
    connector=DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=1');con.execute("SET memory_limit='512MB'")
        access=FoundationReader(connector).resolve_on(con)
        if access.foundation_publication_id!=report['base_publication'] or access.ducklake_snapshot_id!=report['base_snapshot']:
            raise RuntimeError('CURRENT_CHANGED_SINCE_RECONCILIATION')
        @contextmanager
        def same(): yield con
        live=FoundationPublicationStore(same)
        base=live.get(access.foundation_publication_id)
        candidate=transition.make_candidate(base,report_path,capture_root)
        validate_manifest(live,candidate);transition.verify_files(candidate.manifest)
        con.execute("ATTACH ':memory:' AS sales_continuity_isolation")
        isolated=FoundationPublicationStore(same,catalog='sales_continuity_isolation')
        isolated.ensure_schema()
        # Preserve exact ancestor manifests. Only the fixture's metadata lifecycle
        # is bootstrapped; no source record or source pointer is ever modified.
        ancestors=[];ancestor=base
        while ancestor:
            ancestors.append(ancestor)
            manifest=ancestor.manifest
            parent=manifest.get('purchasing_base_publication_id') if manifest.get('candidate_kind')=='PURCHASING_FOUNDATION_V1' else manifest.get('base_foundation_publication_id')
            ancestor=live.get(parent) if parent else None
            if len(ancestors)>32:
                raise ValueError('cyclic ancestor provenance')
        for ancestor in reversed(ancestors):
            copy=deepcopy(ancestor);copy.status=SUPERSEDED
            if ancestor.foundation_publication_id==base.foundation_publication_id:
                copy.status=READY_TO_COMMIT;copy.previous_foundation_publication_id=None
            isolated.create_candidate(copy)
        isolated.logical_commit(base.foundation_publication_id)
        isolated.create_candidate(candidate)
        validate_manifest(isolated,isolated.get(candidate.foundation_publication_id))
        isolated.set_status(candidate.foundation_publication_id,READY_TO_COMMIT)
        faults=[]
        for point in (CommitFaultPoint.DURING_VALIDATION,CommitFaultPoint.DURING_LOGICAL_COMMIT):
            isolated.fault_point=point
            try:
                isolated.logical_commit(candidate.foundation_publication_id)
            except Exception as exc:
                if isolated.current_pointer()!=base.foundation_publication_id:
                    raise RuntimeError('ISOLATED_POINTER_ATOMICITY_FAILURE') from exc
                faults.append(dict(point=point,result='PREVIOUS_POINTER_PRESERVED'))
            else:
                raise RuntimeError('FAULT_NOT_TRIGGERED')
        isolated.fault_point=None
        isolated.logical_commit(candidate.foundation_publication_id)
        # Default component verifier checks independent Atomic publication records
        # against the real pinned DuckLake source; new facts pass real file hashes.
        reader=FoundationReader(connector,metadata_catalog='sales_continuity_isolation',
                                snapshot_resolver=lambda *_:report['base_snapshot'])
        current=reader.resolve_on(con)
        for domain,tables in TABLES.items():
            current.require_sales_coverage(domain,'2026-09-01','2026-10-30')
            for table in tables:
                count=con.execute('SELECT count(*) FROM '+current.relation(domain,table)).fetchone()[0]
                if count!=report['datasets'][table]['row_count']:
                    raise ValueError('ISOLATED_READER_DATASET_COUNT_MISMATCH')
        for domain,tables in TABLES.items():
            for table in tables:
                con.execute(f'CREATE TEMP VIEW full_{table} AS SELECT * FROM {current.relation(domain,table)}')
        answers=commercial_answers(con,candidate.foundation_publication_id)
        for key,value in report['commercial_answers'].items():
            if key!='metadata' and inc.digest(answers[key])!=inc.digest(value):
                raise ValueError('CANONICAL_CANDIDATE_COMMERCIAL_RECONCILIATION_MISMATCH: '+key)
        inc.seal(destination/'candidate-business-answers.json',answers)
        noop=isolated.logical_commit(candidate.foundation_publication_id)
        if noop['status']!='ALREADY_CURRENT':
            raise ValueError('ISOLATED_PUBLICATION_NOOP_FAILED')
        material=resolve_current_material_supply(isolated)
        receivables=resolve_receivables(isolated)
        if material.snapshot_id!=report['derivation_snapshot'] or receivables.snapshot_id!=report['derivation_snapshot']:
            raise ValueError('HISTORICAL_DERIVATION_PIN_CHANGED')
        isolated.logical_rollback(base.foundation_publication_id,
            expected_current_foundation_publication_id=candidate.foundation_publication_id,reason='Sales continuity isolated rollback gate')
        if reader.resolve_on(con).foundation_publication_id!=base.foundation_publication_id:
            raise ValueError('ISOLATED_ROLLBACK_READER_MISMATCH')
        if live.current_pointer()!=base.foundation_publication_id:
            raise RuntimeError('LIVE_CURRENT_CHANGED_DURING_GATE')
        inc.seal(destination/'foundation-candidate.json',candidate.as_row())
        result=dict(status='CANDIDATE_PASS',candidate=candidate.foundation_publication_id,
                    manifest_sha256=inc.digest(candidate.manifest),components=sorted(candidate.manifest['components']),
                    physical_integrity='PASS',coverage='118/118 daily source windows',
                    isolated_canonical_reader='PASS_WITH_REAL_FILES_AND_PINNED_SOURCE_CATALOG',
                    metadata_catalog='EPHEMERAL_IN_MEMORY_NOT_PRODUCTION',
                    snapshot_resolution='INJECTED_SOURCE_PIN; no new production commit snapshot claimed',
                    sealed_readers='Material Supply and Receivables metadata PASS; original derivation snapshot preserved',
                    faults=faults,rollback='PASS_ISOLATED',noop='ALREADY_CURRENT',
                    business_acceptance='PASS_REAL_FILES_ISOLATED_CANONICAL_READER_NOT_LIVE',
                    business_answers_sha256=inc.file_hash(destination/'candidate-business-answers.json'),
                    live_current_unchanged=True,
                    promotion_authorization='NOT_ESTABLISHED; candidate retained, no live metadata writes',
                    activation_procedure=['Obtain explicit operational Foundation promotion entitlement for this exact candidate and its retained historical component cutoffs.',
                        'Run resource preflight; re-resolve and require exact base CURRENT and source snapshot; validate manifest and physical files again.',
                        'Acquire existing FoundationPublicationStore run lock exclusively. Deserialize foundation-candidate.json through existing publication row contract.',
                        'Use FoundationPublicationStore.create_candidate, validate_manifest, set_status(READY_TO_COMMIT), then logical_commit (existing atomic CAS). Never write a pointer manually.',
                        'Re-resolve canonical reader without snapshot injection, require daily sales coverage, verify monetary outputs and component pins; on failed postcommit gate use logical_rollback with exact expected-current candidate id.'])
        inc.seal(destination/'foundation-gate.json',result)
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-root',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    report=build(args.capture_root,args.destination.resolve())
    foundation=prepare_isolated_foundation(args.capture_root,args.destination.resolve())
    print(json.dumps(dict(reconciliation=report,foundation=foundation),default=str),flush=True)
    return 0


if __name__=='__main__': raise SystemExit(main())
