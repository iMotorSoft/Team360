"""Explicit independent-facts successors in the existing Foundation chain.

V1 implements full observed OITW positions, not additive quantities or OINM.
Other replacements fail closed until their domain replay adapter exists. Old
Material Supply/receivables retain their exact historical datasets/snapshot;
they are deliberately NOT rederived or relabelled by a stock observation.
No source queries and no publication writes: use canonical Promotion.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import os
import json

from . import sales_incremental as inc
from .create_initial import SCHEMA_VERSION, TRANSFORMATION_VERSION
from .foundation_publication import ComponentReference, FoundationPublication, FoundationReaderError
from .full_refresh_capture import CONTRACT as CAPTURE_CONTRACT, verify_capture
from .raw import digest
from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb

KIND = 'FOUNDATION_INDEPENDENT_FACTS_SUCCESSION_V1'
CONTRACT = 'OBSERVED_STOCK_FULL_REPLACEMENT_V1'
STOCK_SQL = 'SELECT W."ItemCode", W."WhsCode", W."OnHand", W."IsCommited", W."OnOrder" FROM "TELCHI"."OITW" W ORDER BY W."ItemCode", W."WhsCode"'
COLUMNS = ('atomic_id', 'source_system', 'source_table', 'item_code', 'whs_code',
           'on_hand', 'is_commited', 'on_order', 'source_as_of', 'raw_extraction_id',
           'reference_version', 'reference_manifest_hash', 'transformation_version', 'schema_version')
MUTABLE = {'foundation_publication_id', 'update_run_id', 'candidate_kind',
           'manifest_schema_version', 'base_foundation_publication_id', 'components',
           'independent_facts_succession', 'source_as_of'}


def fail(message):
    raise FoundationReaderError('Independent facts succession: ' + message)


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def checked_path(value, parent):
    path, parent = Path(value), Path(parent).resolve()
    if (not path.is_absolute() or parent not in path.resolve().parents
            or any(p.is_symlink() for p in (path, *path.parents))):
        fail('immutable physical path invalid')
    return path


def stock_contract(manifest):
    stable = manifest.get('components', {}).get('oitw', {}).get('independent_facts_contract')
    if stable is not None:
        from .reference_compatibility import KIND as REFERENCE_KIND
        from .sales_facts_transition import KIND as SALES_KIND
        if (manifest.get('candidate_kind') not in {KIND,REFERENCE_KIND,SALES_KIND}
                or not isinstance(manifest.get('sales_facts_revalidation'),dict)
                or not isinstance(manifest.get('independent_facts_succession'),dict)):
            fail('stock dispatch requires canonical validated succession ancestry')
    return stable


def relation(manifest):
    stable = stock_contract(manifest)
    if not isinstance(stable, dict) or stable.get('contract') != CONTRACT:
        fail('stock relation is not accredited')
    return '(SELECT * FROM read_parquet(' + literal(stable['dataset']['path']) + '))'


def previous_relation(base):
    if stock_contract(base.manifest):
        return relation(base.manifest)
    snapshot = base.manifest.get('facts_base_snapshot_id', base.manifest.get('reference_data_snapshot_id'))
    if type(snapshot) is not int:
        fail('independent snapshot missing')
    from .foundation_reader import pinned_atomic_relation
    return pinned_atomic_relation('oitw', 'inventory_balance', snapshot)


def capture_evidence(directory):
    directory = checked_path(directory, inc.DATA_ROOT/'raw/sap'/CAPTURE_CONTRACT)
    if directory.name != 'stock' or directory.parent.name != 'inventory':
        fail('stock capture identity mismatch')
    result = verify_capture(directory)
    intent = inc.read_json(directory/'intent.json')
    scope = result.get('semantic_scope', {})
    plan = intent['plan']
    if (result.get('status') != 'CAPTURE_RECONCILED_NOT_PUBLISHED'
            or result.get('keys') != ['ItemCode', 'WhsCode']
            or plan.get('contract') != CAPTURE_CONTRACT or plan.get('sql') != STOCK_SQL
            or plan.get('params') != [] or plan.get('keys') != result['keys']
            or plan.get('sums') != ['OnHand', 'IsCommited', 'OnOrder']
            or plan.get('nullable_keys') is not False or plan.get('ordered_keys') is not True
            or plan.get('semantic_scope') != scope
            or scope.get('kind') != 'CURRENT_STOCK_STATEMENT_SNAPSHOT'
            or scope.get('history_rebuilt') is not False
            or (directory/'failure.json').exists()
            or intent.get('source_before') != result.get('source_before')
            or type(result.get('row_count')) is not int or result['row_count'] <= 0):
        fail('complete stock statement semantics not accredited')
    start, end = [datetime.fromisoformat(result[k]['utc']) for k in ('source_before', 'source_after')]
    if end < start:
        fail('observation interval regressed')
    if len(list(directory.glob('checkpoint-*.json'))) != len(result['pages']):
        fail('capture checkpoint set incomplete')
    for page in result['pages']:
        checked_path(page['path'], directory)
        checked_path(page['manifest_path'], directory)
        raw = inc.read_json(Path(page['manifest_path']))
        if (raw.get('contract') != CAPTURE_CONTRACT or raw.get('dataset') != 'stock'
                or raw.get('plan_sha256') != result['plan_sha256']
                or raw.get('source_as_of') != result['source_before']['utc']
                or raw.get('source_as_of_window') != [] or raw.get('semantic_scope') != scope
                or raw.get('file_references') != [page['path']]
                or raw.get('file_hashes') != [page['sha256']]):
            fail('capture manifest source/observation binding mismatch')
    evidence = dict(capture_directory=str(directory), receipt_sha256=inc.file_hash(directory/'complete.json'),
        intent_sha256=inc.file_hash(directory/'intent.json'), row_count=result['row_count'],
        observation_start=start.isoformat()+'+00:00', observation_end=end.isoformat()+'+00:00',
        extracted_at=result['captured_at'], business_date_coverage=None,
        watermark=None, complete_statement=True, historical_stock_available=False,
        absent_position_semantics='NO_ZERO_INFERENCE; old keys must be retained',
        source_snapshot='SINGLE_STATEMENT_CURSOR_NOT_CROSS_DOMAIN_TRANSACTION')
    return result, evidence


def projection(con, result, evidence, reference_version):
    # Encode each distinct native token once, using the original Python JSON
    # escaping (including non-ASCII). SHA256 is vectorized over the exact same
    # bytes, not DuckDB's potentially different JSON representation.
    con.create_function('stock_json_token_v1', lambda value: json.dumps(value),
                        ['VARCHAR'], 'VARCHAR')
    con.execute('''CREATE MACRO stock_native_id_v1(item, whs) AS
        'inventory_balance_' || substr(sha256('["SAP_B1_HANA","OITW",' ||
        item || ',' || whs || ']'), 1, 32)''')
    source = 'read_parquet([' + ','.join(literal(p['path']) for p in result['pages']) + '])'
    con.execute('CREATE TEMP VIEW captured_stock AS SELECT * FROM ' + source)
    for table, column in [('stock_items', 'ItemCode'), ('stock_warehouses', 'WhsCode')]:
        con.execute(f'''CREATE TEMP TABLE {table} AS SELECT key,
            stock_json_token_v1(key) AS token FROM
            (SELECT DISTINCT "{column}" AS key FROM captured_stock)''')
    fields = [
        'stock_native_id_v1(i.token,w.token) AS atomic_id',
        "'SAP_B1_HANA' AS source_system", "'OITW' AS source_table",
        '"ItemCode" AS item_code', '"WhsCode" AS whs_code',
        '"OnHand" AS on_hand', '"IsCommited" AS is_commited', '"OnOrder" AS on_order',
        literal(evidence['observation_start'])+' AS source_as_of',
        literal(result['plan_sha256'])+' AS raw_extraction_id',
        literal(reference_version)+' AS reference_version',
        literal(str(inc.DATA_ROOT/'reference/_versions'/reference_version))+' AS reference_manifest_hash',
        literal(TRANSFORMATION_VERSION)+' AS transformation_version', literal(SCHEMA_VERSION)+' AS schema_version']
    con.execute('CREATE TEMP VIEW expected_stock AS SELECT '+','.join(fields)+''' FROM captured_stock
        LEFT JOIN stock_items i ON i.key="ItemCode"
        LEFT JOIN stock_warehouses w ON w.key="WhsCode"''')


@contextmanager
def replay_db():
    con = open_safe_duckdb(profile=DuckDBSafetyProfile(threads=2, memory_limit='512MB'))
    try:
        yield con
    finally:
        con.close()


def verify_files(manifest):
    """Reproduce every output cell from hash-verified immutable source receipts."""
    stable = stock_contract(manifest)
    if not isinstance(stable, dict) or stable.get('contract') != CONTRACT:
        fail('unsupported domain contract')
    result, evidence = capture_evidence(stable['evidence']['capture_directory'])
    if stable['evidence'] != evidence:
        fail('capture evidence binding mismatch')
    metadata = stable['dataset']
    path = checked_path(metadata['path'], inc.DATA_ROOT/'staging')
    if inc.file_hash(path) != metadata['sha256']:
        fail('physical hash mismatch')
    with replay_db() as con:
        projection(con, result, evidence, stable['reference_version'])
        con.execute('CREATE TEMP VIEW actual_stock AS SELECT * FROM read_parquet('+literal(path)+')')
        schema = [[r[0], r[1]] for r in con.execute('DESCRIBE actual_stock').fetchall()]
        if schema != [[c, 'VARCHAR'] for c in COLUMNS] or schema != metadata['schema']:
            fail('stock schema incompatible')
        count, keys = con.execute('SELECT count(*),count(DISTINCT (item_code,whs_code)) FROM actual_stock').fetchone()
        if count != keys or count != evidence['row_count'] or count != metadata['row_count']:
            fail('duplicate keys or row count mismatch')
        invalid = con.execute('''SELECT count(*) FROM actual_stock WHERE
            item_code IS NULL OR trim(item_code)='' OR whs_code IS NULL OR trim(whs_code)=''
            OR try_cast(on_hand AS DECIMAL(38,12)) IS NULL
            OR try_cast(is_commited AS DECIMAL(38,12)) IS NULL
            OR try_cast(on_order AS DECIMAL(38,12)) IS NULL''').fetchone()[0]
        if invalid:
            fail('null identity or invalid quantity')
        from decimal import Decimal
        intent = inc.read_json(Path(evidence['capture_directory'])/'intent.json')
        for field, native in [('on_hand','OnHand'),('is_commited','IsCommited'),('on_order','OnOrder')]:
            total = con.execute(f'SELECT sum(cast({field} AS DECIMAL(38,12))) FROM actual_stock').fetchone()[0]
            if any(total != Decimal(str(control['sum_'+native])) for control in (result['control'], intent['control_before'])):
                fail('source quantity control mismatch')
        # Unique native keys + exact cardinality + a total keyed equality join
        # prove the same multiset as a wide EXCEPT ALL, without sorting/spilling
        # 1.4M fourteen-column rows on the shared HDD. No hash-only surrogate.
        raw_count, raw_keys = con.execute('SELECT count(*),count(DISTINCT ("ItemCode","WhsCode")) FROM captured_stock').fetchone()
        if raw_count != count or raw_count != raw_keys:
            fail('source replay key/cardinality mismatch')
        differences = con.execute('''SELECT count(*) FROM captured_stock r LEFT JOIN actual_stock n
            ON n.item_code=r."ItemCode" AND n.whs_code=r."WhsCode"
            WHERE n.atomic_id IS NULL OR n.on_hand IS DISTINCT FROM r."OnHand"
            OR n.is_commited IS DISTINCT FROM r."IsCommited" OR n.on_order IS DISTINCT FROM r."OnOrder"''').fetchone()[0]
        constants = dict(source_system='SAP_B1_HANA',source_table='OITW',
            source_as_of=evidence['observation_start'],raw_extraction_id=result['plan_sha256'],
            reference_version=stable['reference_version'],
            reference_manifest_hash=str(inc.DATA_ROOT/'reference/_versions'/stable['reference_version']),
            transformation_version=TRANSFORMATION_VERSION,schema_version=SCHEMA_VERSION)
        predicate = ' OR '.join(c+' IS DISTINCT FROM '+literal(v) for c,v in constants.items())
        invalid_metadata = con.execute('''SELECT count(*) FROM actual_stock
            LEFT JOIN stock_items i ON i.key=item_code
            LEFT JOIN stock_warehouses w ON w.key=whs_code
            WHERE atomic_id IS DISTINCT FROM stock_native_id_v1(i.token,w.token) OR '''+predicate).fetchone()[0]
        if differences or invalid_metadata:
            fail('source replay mismatch')
        # Direct native identities, never a name/fuzzy match or new grant.
        for dataset, column, native in [('products', 'item_code', 'item_code'), ('warehouses', 'code', 'whs_code')]:
            reference = inc.DATA_ROOT/'reference/_versions'/stable['reference_version']/dataset/'part-00000.parquet'
            if con.execute(f'''SELECT EXISTS(SELECT 1 FROM actual_stock s ANTI JOIN read_parquet(?) p
                ON p.source_system='SAP_HANA' AND p."{column}"=s."{native}")''', [str(reference)]).fetchone()[0]:
                fail('unresolved Reference identity: '+dataset)
    return evidence


def validate_transition(store, publication, base, base_components):
    m, old = publication.manifest, base.manifest
    proof = m.get('independent_facts_succession')
    from .operational_domains import CONTRACT as OBSERVATIONS, validate_transition as validate_observations
    if isinstance(proof, dict) and proof.get('contract') == OBSERVATIONS:
        return validate_observations(publication, base, base_components, store.connection_factory)
    if (set(m['components']) != set(base_components)
            or publication.previous_foundation_publication_id != base.foundation_publication_id
            or publication.reference_version != base.reference_version
            or m.get('base_foundation_publication_id') != base.foundation_publication_id
            or {k:v for k,v in m.items() if k not in MUTABLE} != {k:v for k,v in old.items() if k not in MUTABLE}
            or not isinstance(proof, dict) or proof.get('contract') != CONTRACT
            or proof.get('base_manifest_sha256') != inc.digest(old)
            or proof.get('replaced_components') != ['oitw']
            or proof.get('retained_derivations') != {n:inc.digest(base_components[n]) for n in ('material_supply', 'receivables_collections')}):
        fail('lineage, snapshot, permission or inherited business contract mismatch')
    for name, entry in base_components.items():
        if name != 'oitw' and (m['components'][name] != entry or publication.component(name) != base.component(name)):
            fail('unaffected sealed component changed: '+name)
    entry = m['components']['oitw']
    stable = stock_contract(m)
    if (not isinstance(stable, dict) or stable.get('contract') != CONTRACT
            or set(stable) != {'contract','base_manifest_sha256','previous_component','reference_version','evidence','dataset'}
            or stable.get('base_manifest_sha256') != inc.digest(old)
            or stable.get('previous_component') != base_components['oitw']['publication_id']
            or stable.get('reference_version') != publication.reference_version):
        fail('stock dependency binding mismatch')
    identity = inc.digest(stable)
    expected = ComponentReference('oitw', 'oitw_'+identity[:24], content_identity=identity,
        source_as_of=stable['evidence']['observation_start'], row_count=stable['dataset']['row_count'])
    if (entry != dict(expected.as_dict(), independent_facts_contract=stable)
            or publication.component('oitw').publication_id != expected.publication_id
            or publication.component('oitw').source_as_of != expected.source_as_of
            or publication.foundation_publication_id != 'foundation_'+inc.digest(dict(base=base.foundation_publication_id, components=m['components'], proof=proof))[:32]):
        fail('publication identity/fingerprint mismatch')
    previous_time = datetime.fromisoformat(base_components['oitw']['source_as_of'])
    if datetime.fromisoformat(stable['evidence']['observation_start']) <= previous_time:
        fail('stock observation did not advance')
    verify_files(m)
    with store.connection_factory() as con:
        before, after = previous_relation(base), relation(m)
        schema = [[r[0], r[1]] for r in con.execute('DESCRIBE SELECT * FROM '+before).fetchall()]
        if schema != stable['dataset']['schema']:
            fail('previous stock schema incompatible')
        if con.execute(f'''SELECT EXISTS(SELECT 1 FROM {before} p ANTI JOIN {after} n
            ON p.item_code=n.item_code AND p.whs_code=n.whs_code AND p.atomic_id=n.atomic_id)''').fetchone()[0]:
            fail('loss of historical position identity requires explicit transition')
    return m['components']


def verify_reader(con, access):
    """Reconcile live pinned reader aggregates to native captures, not metadata."""
    stable = stock_contract(access.manifest)
    result, evidence = capture_evidence(stable['evidence']['capture_directory'])
    source = 'read_parquet([' + ','.join(literal(p['path']) for p in result['pages']) + '])'
    live = access.oitw()
    row_count, first, last = con.execute(f'SELECT count(*),min(source_as_of),max(source_as_of) FROM {live}').fetchone()
    if row_count != result['row_count'] or first != evidence['observation_start'] or last != first:
        fail('live reader count/observation mismatch')
    counts = {}
    for native, field in [('ItemCode','item_code'),('WhsCode','whs_code')]:
        raw = f'''SELECT "{native}" AS key,count(*) AS positions,
            sum(cast("OnHand" AS DECIMAL(38,12))) AS on_hand,
            sum(cast("IsCommited" AS DECIMAL(38,12))) AS committed,
            sum(cast("OnOrder" AS DECIMAL(38,12))) AS on_order FROM {source} GROUP BY "{native}"'''
        actual = f'''SELECT {field} AS key,count(*) AS positions,
            sum(cast(on_hand AS DECIMAL(38,12))) AS on_hand,
            sum(cast(is_commited AS DECIMAL(38,12))) AS committed,
            sum(cast(on_order AS DECIMAL(38,12))) AS on_order FROM {live} GROUP BY {field}'''
        for left,right in [(raw,actual),(actual,raw)]:
            if con.execute(f'SELECT EXISTS(({left}) EXCEPT ALL ({right}))').fetchone()[0]:
                fail('live reader native aggregate mismatch: '+field)
        counts[field] = con.execute('SELECT count(*) FROM ('+actual+')').fetchone()[0]
    totals = con.execute(f'''SELECT sum(cast(on_hand AS DECIMAL(38,12))),
        sum(cast(is_commited AS DECIMAL(38,12))),sum(cast(on_order AS DECIMAL(38,12))) FROM {live}''').fetchone()
    availability = access.stock_availability()
    units = con.execute(f'SELECT count(*) FILTER (WHERE inventory_uom_id IS NULL) FROM {availability}').fetchone()[0]
    return dict(status='LIVE_READER_RAW_AGGREGATES_EXACT',rows=row_count,groups=counts,
        observation_start=first,observation_end=evidence['observation_end'],
        on_hand=str(totals[0]),committed=str(totals[1]),on_order=str(totals[2]),
        quantities_across_items_are_not_a_single_unit_metric=True,unknown_inventory_uom_rows=units,
        movement_refresh=False,historical_stock_claim=False)


def make_candidate(base, capture_directory, destination):
    """Isolated deterministic candidate, with durable dataset then sealed row."""
    from .sales_facts_transition import NAMES
    if set(base.manifest['components']) != NAMES:
        fail('eight-component accredited base required')
    destination = checked_path(destination, inc.DATA_ROOT/'staging')
    result, evidence = capture_evidence(capture_directory)
    destination.mkdir(parents=True, exist_ok=False)
    path = destination/'inventory_balance.parquet'
    with replay_db() as con:
        projection(con, result, evidence, base.reference_version)
        con.execute('COPY expected_stock TO '+literal(path)+' (FORMAT PARQUET, COMPRESSION ZSTD)')
    with path.open('rb') as stream:
        os.fsync(stream.fileno())
    inc.sync_dir(destination)
    metadata = dict(path=str(path), sha256=inc.file_hash(path), row_count=result['row_count'], schema=[[c,'VARCHAR'] for c in COLUMNS])
    stable = dict(contract=CONTRACT, base_manifest_sha256=inc.digest(base.manifest),
        previous_component=base.manifest['components']['oitw']['publication_id'], reference_version=base.reference_version,
        evidence=evidence, dataset=metadata)
    identity = inc.digest(stable)
    component = ComponentReference('oitw', 'oitw_'+identity[:24], content_identity=identity,
        source_as_of=evidence['observation_start'], row_count=result['row_count'])
    manifest, catalog = deepcopy(base.manifest), deepcopy(base.components)
    manifest['components']['oitw'] = dict(component.as_dict(), independent_facts_contract=stable)
    catalog['oitw'] = component
    proof = dict(contract=CONTRACT, base_manifest_sha256=inc.digest(base.manifest), replaced_components=['oitw'],
        retained_derivations={n:inc.digest(base.manifest['components'][n]) for n in ('material_supply','receivables_collections')})
    fid = 'foundation_'+inc.digest(dict(base=base.foundation_publication_id, components=manifest['components'], proof=proof))[:32]
    source_as_of = max(v['source_as_of'] for v in manifest['components'].values() if v.get('source_as_of'))
    manifest.update(foundation_publication_id=fid, update_run_id=destination.name, candidate_kind=KIND,
        manifest_schema_version='1.0.0', base_foundation_publication_id=base.foundation_publication_id,
        independent_facts_succession=proof, source_as_of=source_as_of)
    candidate = FoundationPublication(fid, destination.name, previous_foundation_publication_id=base.foundation_publication_id,
        reference_version=base.reference_version, components=catalog, manifest=manifest,
        source_as_of=source_as_of, validation_status='PASS')
    inc.seal(destination/'foundation-candidate.json', candidate.as_row())
    return candidate
