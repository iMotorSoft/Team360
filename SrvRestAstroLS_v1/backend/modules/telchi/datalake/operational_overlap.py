"""Explicit, source-replayed overlap for captured operational observations.

Does not replace historical metric components. Each revision preserves its
ancestor and records bounded document-state coverage, not CDC or BOM validity.
"""
from copy import deepcopy
import os

from . import operational_domains as obs
from . import sales_incremental as durable
from .full_refresh_capture import verify_capture
from .foundation_publication import FoundationPublication
from .independent_facts_succession import checked_path, literal, KIND

CONTRACT = 'BOUNDED_OPERATIONAL_OVERLAP_V1'
EXTRA = {'production': ('production_receipt',), 'stock': ('historical_inventory_balance',)}


def groups(stable):
    result = dict(obs.GROUPS)
    for domain, names in EXTRA.items():
        if domain in stable.get('overlap', {}).get('domains', []):
            result[domain] = result.get(domain, ()) + names
    if stable.get('overlap', {}).get('material_lead_time'):
        from .material_supply_completion import OUTPUTS
        result['material_supply'] = result['material_supply'] + OUTPUTS
    return result


def capture(directory, *, sql, params, keys, sums, kind):
    directory = checked_path(directory, durable.DATA_ROOT / 'raw/sap/full-data-lake-refresh-capture-v1')
    receipt = verify_capture(directory)
    intent = durable.read_json(directory / 'intent.json')
    plan = intent['plan']
    if (plan['sql'] != sql or plan['params'] != params or plan['keys'] != keys
            or plan['sums'] != sums or plan['semantic_scope'].get('kind') != kind
            or plan['nullable_keys'] is not False or plan['ordered_keys'] is not True
            or (directory / 'failure.json').exists()):
        obs.fail('overlap source projection/scope mismatch: ' + directory.name)
    return obs.files_relation([p['path'] for p in receipt['pages']])


def replay(con, stable):
    """Rebuild from original durable receipts plus exact, bounded supplements."""
    from .material_supply_fact_capture import DEFAULT_DATASETS, build_select
    from .sql import oinm_extract_sql
    from .production_receipt_capture import SPEC
    overlap = stable['overlap']
    if overlap.get('contract') != CONTRACT:
        obs.fail('unsupported overlap contract')
    root, captures = obs.checked_captures(stable['capture_root'])
    obs.load_views(con, captures)
    recovery = checked_path(overlap['recovery_root'], durable.DATA_ROOT / 'raw/sap/full-data-lake-refresh-capture-v1')
    selected = overlap['domains']
    if not selected or len(selected) != len(set(selected)) or set(selected) - {'movements', 'production', 'stock', 'material_supply'}:
        obs.fail('unsupported overlap domains')
    coverage = {}
    if 'movements' in selected:
        directory = root / 'movements/inventory_movement'
        prefix = durable.read_json(directory / 'prefix-reconciliation.json')
        plan = durable.read_json(directory / 'intent.json')['plan']
        body = oinm_extract_sql(durable.read_json(root / 'movements/oinm-columns.json')).replace(
            ' AND M."TransNum" >= ? AND M."TransNum" < ?', '').rsplit(' ORDER BY ', 1)[0]
        tail = capture(recovery / 'movements/inventory_movement_tail',
            sql=body + ' AND M."TransNum" > ? ORDER BY M."TransNum", M."TransSeq"',
            params=[*plan['params'], prefix['upper_native_key']], keys=['TransNum','TransSeq'],
            sums=['InQty','OutQty'], kind='BOUNDED_NATIVE_KEY_TAIL')
        tail_plan = durable.read_json(recovery / 'movements/inventory_movement_tail/intent.json')['plan']
        if tail_plan['semantic_scope']['prefix_receipt_sha256'] != durable.file_hash(directory / 'prefix-reconciliation.json'):
            obs.fail('tail prefix binding mismatch')
        original = obs.files_relation([p['path'] for p in captures['captured_datasets']['inventory_movement']['file_hashes']])
        con.execute('CREATE OR REPLACE TEMP VIEW inventory_movement AS SELECT * FROM ' + original + ' UNION ALL SELECT * FROM ' + tail)
        control = con.execute('''SELECT count(*),count(DISTINCT ("TransNum","TransSeq")),
            sum(cast("InQty" AS DECIMAL(38,12))),sum(cast("OutQty" AS DECIMAL(38,12))) FROM inventory_movement''').fetchone()
        evidence_path = checked_path(overlap['movement_evidence']['path'], durable.DATA_ROOT / 'staging')
        if durable.file_hash(evidence_path) != overlap['movement_evidence']['sha256']:
            obs.fail('movement control evidence bytes changed')
        recovery_report = durable.read_json(evidence_path)
        evidence = recovery_report['full_window_control']
        if (recovery_report.get('root') != str(recovery) or not recovery_report.get('movement_control_reconciled')
                or recovery_report['prefix_current_control']['control'] != prefix['source_control']
                or recovery_report['prefix_current_control']['expected'] != prefix['source_control']):
            obs.fail('movement full-window or prefix evidence mismatch')
        import hashlib
        logs = {r['query_id']:r for r in recovery_report['source_query_logs']['movements']}
        control_select = 'SELECT COUNT(*) AS "rows", SUM(Q."InQty") AS "sum_InQty", SUM(Q."OutQty") AS "sum_OutQty" FROM ('
        for query_id, query in (
                ('validate_frozen_prefix', control_select + body + ' AND M."TransNum" <= ?) Q'),
                ('full_window_after_tail', control_select + body + ') Q')):
            log = logs[query_id]
            if (log['query_hash'] != hashlib.sha256(query.encode()).hexdigest() or log['status'] != 'FETCHED'
                    or not log['cursor_closed'] or not log['connection_closed'] or log['sap_write_count'] != 0):
                obs.fail('movement source control query binding mismatch')
        from decimal import Decimal
        if (control[0] != control[1] or any(Decimal(str(value)) != Decimal(str(evidence[key]))
                for key,value in zip(('rows','sum_InQty','sum_OutQty'), (control[0],control[2],control[3])))):
            obs.fail('complete movement union controls mismatch')
        coverage['movements'] = dict(start=plan['params'][0], end_exclusive=plan['params'][1], rows=control[0],
            semantics='RECONCILED_DATED_STATEMENT_UNION; NOT_CDC_OR_CROSS_STATEMENT_SNAPSHOT',
            october_rows=con.execute('''SELECT count(*) FROM inventory_movement WHERE cast("DocDate" AS DATE)
                >=DATE '2026-10-01' AND cast("DocDate" AS DATE)<DATE '2026-11-01' ''').fetchone()[0])
    if 'production' in selected:
        spec = next(s for s in DEFAULT_DATASETS if s.name == 'production_order')
        available = {'OWOR':{r['COLUMN_NAME']:r for r in durable.read_json(root / 'production/OWOR-columns.json')}}
        sql, absent = build_select(spec, available)
        supplemental = recovery / 'production/referenced_production_orders'
        plan = durable.read_json(supplemental / 'intent.json')['plan']
        entries = plan['semantic_scope']['doc_entries']
        missing = [int(r[0]) for r in con.execute('''SELECT DISTINCT I."BaseEntry" FROM production_issue I ANTI JOIN production_order O
            ON I."BaseEntry"=O."DocEntry" WHERE try_cast(I."BaseType" AS INTEGER)=202 ORDER BY I."BaseEntry"''').fetchall()]
        if entries != sorted(missing) or plan['semantic_scope']['absent_optional_fields'] != absent:
            obs.fail('supplement is not exact missing order set')
        sql = sql.replace('H."PostDate" >= ? AND H."PostDate" < ?', 'H."DocEntry" IN (' + ','.join('?' for _ in entries) + ')')
        supplement = capture(supplemental, sql=sql,params=entries,keys=['DocEntry'],sums=['PlannedQty'],kind='EXACT_REFERENCED_NATIVE_KEYS')
        original = obs.files_relation([p['path'] for p in captures['captured_datasets']['production_order']['file_hashes']])
        con.execute('CREATE OR REPLACE TEMP VIEW production_order AS SELECT * FROM ' + original + ' UNION ALL SELECT * FROM ' + supplement)
        receipt_root = recovery / 'production-output'
        available = {t:{r['COLUMN_NAME']:r for r in durable.read_json(receipt_root / (t+'-columns.json'))} for t in SPEC.tables}
        sql, absent = build_select(SPEC, available)
        required = {'DocEntry','LineNum','DocDate','CANCELED','ItemCode','Quantity','WhsCode','BaseType','BaseEntry','unitMsr','UomCode'}
        receipt_plan = durable.read_json(receipt_root / 'production_receipt/intent.json')['plan']
        if required.intersection(absent) or receipt_plan['semantic_scope']['absent_optional_fields'] != absent:
            obs.fail('required production receipt source fields missing')
        sql = sql.replace(' ORDER BY ', ' AND L."BaseType" = 202 ORDER BY ')
        source = capture(receipt_root / 'production_receipt',sql=sql,params=['2026-01-01','2026-11-01'],
            keys=['DocEntry','LineNum'],sums=['Quantity'],kind='BOUNDED_ACTUAL_PRODUCTION_RECEIPT')
        con.execute('CREATE TEMP VIEW production_receipt AS SELECT * FROM ' + source)
        if con.execute('''SELECT count(*) FROM production_receipt WHERE try_cast("Quantity" AS DECIMAL(38,12)) IS NULL
                OR try_cast("DocDate" AS DATE) IS NULL OR "CANCELED" IS NULL''').fetchone()[0]:
            obs.fail('invalid native production receipt quantity/date/state')
        for name in ('production_issue','production_receipt'):
            if con.execute(f'''SELECT count(*) FROM {name} I ANTI JOIN production_order O
                    ON I."BaseEntry"=O."DocEntry" WHERE try_cast(I."BaseType" AS INTEGER)=202''').fetchone()[0]:
                obs.fail('unresolved native production order: ' + name)
        if con.execute('''SELECT count(*) FROM production_receipt R ANTI JOIN oitm P ON R."ItemCode"=P."ItemCode"''').fetchone()[0]:
            obs.fail('receipt item identity unresolved')
        coverage['production'] = dict(start='2026-01-01',end_exclusive='2026-11-01',
            receipt_rows=con.execute('SELECT count(*) FROM production_receipt').fetchone()[0],
            october_receipt_rows=con.execute('''SELECT count(*) FROM production_receipt WHERE cast("DocDate" AS DATE)>=DATE '2026-10-01' ''').fetchone()[0],
            semantics='ACTUAL_NATIVE_RECEIPTS; CANCELLATIONS_AND_NATIVE_UNITS_RETAINED; NOT_ORDER_COMPLETED_QUANTITY',
            historical_bom_effectivity=False)
    if 'stock' in selected:
        from .historical_stock import load
        coverage['stock'] = load(con, recovery, overlap['stock_evidence'])
    consumption_root = recovery if 'material_supply' in selected else root
    if 'material_supply' in selected:
        cycle = durable.read_json(recovery / 'cycle-plan.json')
        if (cycle.get('kind') != 'OCTOBER_GAP_RECOVERY_NOT_GLOBAL_REFRESH'
                or cycle.get('year_start') != '2026-01-01' or cycle.get('end_exclusive') != '2026-11-01'):
            obs.fail('actual-consumption recovery cutoff not accredited')
    consumption = obs.build_observed_consumption(con, consumption_root)
    if 'material_supply' in selected:
        coverage['material_supply'] = dict(observed_material_actual_consumption=consumption,
            historical_five_outputs_complete=False, historical_bom_effectivity_required_for_this_output=False,
            native_inventory_item_units_only=True, raw_material_classification_accredited=False,
            document_state='AS_CAPTURED_NOT_FROZEN_HISTORICAL_CANCELLATION_STATE')
    if overlap.get('material_lead_time'):
        from .material_supply_completion import replay as replay_lead_time
        coverage['material_supply_lead_time'] = replay_lead_time(con, stable)
    return coverage


def verify(stable, *, reader=None, con=None):
    with obs.database() as db:
        coverage = replay(db, stable)
        if coverage != stable['overlap']['coverage']:
            obs.fail('overlap coverage differs from source replay')
        result = {}
        for domain,names in groups(stable).items():
            result[domain] = {}
            for name in names:
                metadata = stable['datasets'][name]
                path = checked_path(metadata['path'], durable.DATA_ROOT / 'staging')
                if durable.file_hash(path) != metadata['sha256']:
                    obs.fail('overlap output bytes mismatch: '+name)
                db.execute('CREATE OR REPLACE TEMP VIEW actual AS SELECT * FROM read_parquet('+literal(path)+')')
                schema = [[r[0],r[1]] for r in db.execute('DESCRIBE actual').fetchall()]
                if schema != metadata['schema'] or db.execute('SELECT count(*) FROM actual').fetchone()[0] != metadata['row_count']:
                    obs.fail('overlap output schema/count mismatch: '+name)
                for left,right in ((name,'actual'),('actual',name)):
                    if db.execute(f'SELECT EXISTS((SELECT * FROM {left}) EXCEPT ALL (SELECT * FROM {right}))').fetchone()[0]:
                        obs.fail('overlap exact replay mismatch: '+name)
                keys = {'inventory_movement':['TransNum','TransSeq'], 'production_order':['DocEntry'], 'production_receipt':['DocEntry','LineNum'], 'historical_inventory_balance':['ItemCode','WhsCode']}.get(name)
                if keys:
                    columns=','.join('"'+k+'"' for k in keys)
                    nulls=' OR '.join('"'+k+'" IS NULL' for k in keys)
                    if db.execute(f'SELECT EXISTS(SELECT {columns} FROM actual GROUP BY {columns} HAVING count(*)>1)').fetchone()[0] or db.execute('SELECT EXISTS(SELECT 1 FROM actual WHERE '+nulls+')').fetchone()[0]:
                        obs.fail('invalid overlap native identities: '+name)
                if reader is not None:
                    relation=reader.operational_observation(domain,name)
                    if con.execute('SELECT count(*) FROM '+relation).fetchone()[0] != metadata['row_count']:
                        obs.fail('live overlap reader row count mismatch')
                    expected = '(SELECT * FROM read_parquet(' + literal(path) + '))'
                    for left, right in ((relation, expected), (expected, relation)):
                        if con.execute('SELECT EXISTS((SELECT * FROM ' + left + ') EXCEPT ALL (SELECT * FROM ' + right + '))').fetchone()[0]:
                            obs.fail('live overlap reader exact replay mismatch: ' + name)
                result[domain][name]=metadata['row_count']
        if set(stable['datasets']) != {n for names in groups(stable).values() for n in names}:
            obs.fail('overlap registry mismatch')
        return result


def make_candidate(base, recovery_root, destination, *, domains, movement_evidence=None, stock_evidence=None,
                   material_lead_time=False):
    old = obs.observation_contract(base.manifest)
    if old is None:
        obs.fail('an observation ancestor is required')
    previous = old.get('overlap', {})
    if previous and previous['recovery_root'] != str(recovery_root):
        obs.fail('a different recovery cycle requires its own source overlap proof')
    selected = sorted(set(domains) | set(previous.get('domains', [])))
    destination = checked_path(destination, durable.DATA_ROOT / 'staging')
    stable=deepcopy(old)
    stable.update(base_manifest_sha256=durable.digest(base.manifest),
        overlap=dict(contract=CONTRACT, recovery_root=str(recovery_root), domains=selected,
            ancestor_sha256=durable.digest(old),
            movement_evidence=movement_evidence or previous.get('movement_evidence')))
    if 'stock' in selected:
        stable['overlap']['stock_evidence'] = stock_evidence or previous.get('stock_evidence')
    if material_lead_time or previous.get('material_lead_time'):
        from .material_supply_completion import CONTRACT as LEAD_TIME_CONTRACT
        if 'material_supply' not in selected:
            obs.fail('lead time requires explicit material supply observation domain')
        stable['overlap']['material_lead_time'] = {'contract': LEAD_TIME_CONTRACT}
    with obs.database() as con:
        stable['overlap']['coverage']=replay(con,stable)
        destination.mkdir(parents=True,exist_ok=False)
        for domain in domains:
            names=list(groups(stable)[domain])
            if domain == 'material_supply' and material_lead_time:
                from .material_supply_completion import OUTPUTS
                names = list(OUTPUTS)
            if domain=='production': names += ['observed_material_actual_consumption']
            for name in names:
                path=destination/(name+'.parquet')
                con.execute('COPY '+name+' TO '+literal(path)+' (FORMAT PARQUET, COMPRESSION ZSTD)')
                with path.open('rb') as stream: os.fsync(stream.fileno())
                stable['datasets'][name]=dict(path=str(path),sha256=durable.file_hash(path),
                    row_count=con.execute('SELECT count(*) FROM '+name).fetchone()[0],
                    schema=[[r[0],r[1]] for r in con.execute('DESCRIBE '+name).fetchall()])
    durable.sync_dir(destination)
    manifest=deepcopy(base.manifest)
    proof=dict(contract=obs.CONTRACT,base_manifest_sha256=durable.digest(base.manifest),replaced_components=[],
        retained_components_sha256=durable.digest(manifest['components']),observations_sha256=durable.digest(stable))
    identity='foundation_'+durable.digest(dict(base=base.foundation_publication_id,proof=proof))[:32]
    manifest.update(candidate_kind=KIND,manifest_schema_version='1.0.0',foundation_publication_id=identity,
        update_run_id=destination.name,base_foundation_publication_id=base.foundation_publication_id,
        independent_facts_succession=proof,operational_observations=stable)
    candidate=FoundationPublication(identity,destination.name,previous_foundation_publication_id=base.foundation_publication_id,
        reference_version=base.reference_version,components=deepcopy(base.components),manifest=manifest,
        source_as_of=base.source_as_of,validation_status='PASS')
    verify(stable)
    durable.seal(destination/'foundation-candidate.json',candidate.as_row())
    return candidate


def validate_ancestor(stable, old):
    previous=obs.observation_contract(old)
    overlap=stable['overlap']
    if (previous is None or overlap['ancestor_sha256'] != durable.digest(previous)
            or stable['capture_root'] != previous['capture_root'] or stable['limits'] != previous['limits']
            or stable['reconciliation_path'] != previous['reconciliation_path']
            or stable['reconciliation_sha256'] != previous['reconciliation_sha256']):
        obs.fail('overlap ancestor binding mismatch')
    prior_overlap = previous.get('overlap', {})
    if prior_overlap and (prior_overlap['recovery_root'] != overlap['recovery_root']
            or set(prior_overlap['domains']) - set(overlap['domains'])
            or prior_overlap.get('movement_evidence') != overlap.get('movement_evidence')
            or ('stock' in prior_overlap['domains'] and prior_overlap.get('stock_evidence') != overlap.get('stock_evidence'))):
        obs.fail('previous bounded overlap was lost or rebound')
    changed={n for domain in overlap['domains'] for n in groups(stable).get(domain,())}
    if 'production' in overlap['domains']: changed |= {'production_receipt','observed_material_actual_consumption'}
    for name,metadata in previous['datasets'].items():
        if name not in changed and stable['datasets'].get(name) != metadata:
            obs.fail('unaffected observation changed: '+name)
    verify(stable)
