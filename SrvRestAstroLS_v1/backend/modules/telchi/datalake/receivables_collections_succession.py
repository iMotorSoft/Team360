"""CxC-only adapter for the existing independent Foundation succession protocol.

No SAP calls, CURRENT selection or catalog publication. Source receipts are
replayed at update time; productive reads use the accredited component snapshot.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb
from modules.telchi.runtime.resource_guard import ResourceGuard, SafeAbort
from . import receivables_collections_atomic as atomic
from . import receivables_collections_business as business
from . import receivables_collections_foundation as foundation
from . import receivables_collections_history as history
from .foundation_publication import FoundationPublication, FoundationReaderError
from .raw import digest, file_hash

CONTRACT = 'RECEIVABLES_COLLECTIONS_HISTORY_REPLACEMENT_V1'
NAME = foundation.COMPONENT_NAME


def require(value, message):
    if not value:
        raise FoundationReaderError('CxC succession: ' + message)


def snapshot_for(manifest):
    entry = manifest.get('components', {}).get(NAME, {})
    proof = entry.get('history_succession')
    if proof is None:
        return manifest.get('base_snapshot_id')
    require(isinstance(proof, dict) and proof.get('contract') == CONTRACT,
            'unsupported history contract')
    snapshot = proof.get('business_snapshot_id')
    require(type(snapshot) is int and snapshot >= 0, 'invalid component snapshot')
    return snapshot


@contextmanager
def scratch():
    profile = DuckDBSafetyProfile.from_runtime_config()
    profile.temp_directory.mkdir(parents=True, exist_ok=True)
    # Base tables are durable only within this disposable workspace. Keeping
    # millions of replay rows in an in-memory catalog exhausts the bounded spill
    # allowance; a disk-backed scratch catalog keeps the same RAM/spill limits.
    with TemporaryDirectory(prefix='cxc-replay-', dir=profile.temp_directory) as directory:
        con = open_safe_duckdb(profile=profile)
        try:
            path = str(Path(directory)/'replay.duckdb').replace("'", "''")
            con.execute(f"ATTACH '{path}' AS telchi")
            con.execute('SET preserve_insertion_order=false')
            atomic.ensure_tables(con)
            yield con
        finally:
            con.close()


def _scratch_budget(con):
    path = con.execute("SELECT path FROM duckdb_databases() WHERE database_name='telchi'").fetchone()[0]
    if path:
        directory = Path(path).parent
        size = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
        if size > 4*1024**3:
            raise SafeAbort('CXC_SCRATCH_DISK_BUDGET_4GiB')


def _insert(con, entity, rows):
    columns = atomic.ENTITY_COLUMNS[entity]
    for start in range(0, len(rows), 2048):
        batch = rows[start:start+2048]
        # Bounded column batches avoid one Python/SQL round trip per source row.
        con.execute(f'INSERT INTO telchi.atomic.{entity} SELECT ' +
            ','.join('unnest(?::VARCHAR[])' for _ in columns),
            [[None if row[c] is None else str(row[c]) for row in batch] for c in columns])


def _rows(con, sql):
    cursor = con.execute(sql)
    names = [d[0] for d in cursor.description]
    while batch := cursor.fetchmany(2048):
        yield [dict(zip(names, row)) for row in batch]


def _compare(actual, expected, actual_sql, expected_sql, columns, *, bounded=False):
    """Exact cell comparison, partitioned by source month to bound wide sorts."""
    partition = next((c for c in ('document_date','payment_date','reconciliation_date') if c in columns), None)
    if partition and not bounded:
        expression = f"date_trunc('month',try_cast({partition} AS DATE))"
        left = {r[0] for r in actual.execute(f'SELECT DISTINCT {expression} FROM {actual_sql}').fetchall()}
        right = {r[0] for r in expected.execute(f'SELECT DISTINCT {expression} FROM {expected_sql}').fetchall()}
        require(left == right, 'physical source/business replay date coverage differs')
        for start in sorted(left, key=lambda value: str(value)):
            if start is None:
                predicate = f'try_cast({partition} AS DATE) IS NULL'
            else:
                start = date.fromisoformat(str(start)[:10])
                end = date(start.year+1,1,1) if start.month == 12 else date(start.year,start.month+1,1)
                predicate = f"{partition}>='{start.isoformat()}' AND {partition}<'{end.isoformat()}'"
            _compare(actual, expected, f'(SELECT * FROM {actual_sql} WHERE {predicate})',
                f'(SELECT * FROM {expected_sql} WHERE {predicate})', columns, bounded=True)
        return
    fields = ','.join('"' + c + '"' for c in columns)
    key = '"' + columns[0] + '"'
    # Atomic/business identities are unique. Sort only that identity, but still
    # compare every cell; do not sort wide duplicate VARCHAR payloads as keys.
    for con, relation in ((actual, actual_sql), (expected, expected_sql)):
        total, unique = con.execute(f'SELECT count(*),count(DISTINCT {key}) FROM {relation}').fetchone()
        require(total == unique, 'physical replay identity missing or duplicated')
    a = actual.execute(f'SELECT {fields} FROM {actual_sql} ORDER BY {key}')
    b = expected.execute(f'SELECT {fields} FROM {expected_sql} ORDER BY {key}')
    while True:
        left, right = a.fetchmany(2048), b.fetchmany(2048)
        if left != right:
            differing = []
            if len(left) == len(right):
                differing = [c for i,c in enumerate(columns) if any(a[i] != b[i] for a,b in zip(left,right))]
            require(False, 'physical source/business replay differs: ' + actual_sql
                + '; columns=' + ','.join(differing or ['row_count_or_identity']))
        if not left:
            return


def _native_replay_rows(entity, rows):
    # SYS.TABLE_COLUMNS accredits these INTEGER/SMALLINT source fields.
    # Nullable raw JSON inference can encode them as integral Parquet DOUBLEs.
    # Restore only exact, in-range native integer types; never round amounts,
    # ignore hash differences or invent a missing value/relationship. Identity
    # hashes are then reproduced from the original native tokens, not replaced.
    fields = {
        'receivable_document': {'salesperson_code':31,'branch_id':31,'payment_term_code':15},
        'collection_payment': {'branch_id':31},
        'reconciliation_participant': {'installment_id':31},
        'payment_term': {c:15 for c in ('payment_term_code','extra_months','extra_days',
            'payment_count','installment_count','tolerance_days')},
    }.get(entity, {})
    for row in rows:
        for field, bits in fields.items():
            value = row.get(field)
            if isinstance(value, float):
                require(value.is_integer() and -(2**bits) <= value < 2**bits,
                        'nonintegral native SAP INTEGER: ' + field)
                row[field] = int(value)
    return rows


def replay_sources(connection, *, snapshot, coverage, receipts, target):
    """Replay canonical Atomic completed segment receipts, including zero windows.

    Receipts are the producer's completed checkpoint entries, not business-result
    assertions. Every nonempty segment must retain its immutable raw manifest.
    Empty segments require the producer's explicit zero-row completion receipt.
    """
    source = history.snapshot_fingerprint(connection, snapshot)
    plan = coverage['plan']
    history.validate_coverage(coverage, history.plan(plan['as_of'], plan['source_end_exclusive']), source)
    require(set(receipts) == {s['id'] for s in plan['segments']}, 'source receipt gap')
    sealed = {}
    guard = ResourceGuard()
    guard.preflight()
    for segment in atomic.plan_segments(atomic.HISTORY_START, date.fromisoformat(plan['source_end_exclusive'])):
        guard.checkpoint()
        receipt = receipts[segment.segment_id]
        entity = segment.entity
        require(isinstance(receipt, dict), 'invalid segment receipt')
        expected = atomic._raw_manifest(segment, receipt.get('run_id'), [], receipt.get('source_as_of'),
            hashlib.sha256(atomic.SQL[entity].encode()).hexdigest())
        for key, value in expected.items():
            if key not in {'row_count', 'status'}:
                require(receipt.get(key) == value, 'source plan/receipt mismatch: ' + key)
        require(receipt.get('status') == 'COMPLETED' and receipt.get('sap_write_count') == 0
                and receipt.get('run_id') and receipt.get('source_as_of'), 'incomplete source receipt')
        count = receipt.get('row_count')
        require(type(count) is int and count >= 0, 'invalid raw row count')
        raw = receipt.get('raw_manifest')
        rows = []
        if count:
            require(isinstance(raw, dict), 'missing physical source receipt')
            path = Path(raw['path'])
            require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'missing raw file')
            manifest_path = path.parent / 'manifest.json'
            manifest = json.loads(manifest_path.read_text())
            unsigned = {k:v for k,v in manifest.items() if k != 'manifest_hash'}
            require(manifest.get('manifest_hash') == digest(unsigned) == raw.get('manifest_hash'),
                    'source manifest hash mismatch')
            for key, value in expected.items():
                if key not in {'row_count', 'status'}:
                    require(manifest.get(key) == value, 'physical source plan mismatch: ' + key)
            require(manifest.get('status') == 'COMPLETED' and manifest.get('row_count') == count
                    and raw.get('row_count') == count
                    and manifest.get('extraction_id') == raw.get('extraction_id')
                    and manifest.get('file_references') == [str(path)]
                    and manifest.get('file_hashes') == [file_hash(path)]
                    and manifest.get('files') == [dict(file=path.name, bytes=path.stat().st_size, sha256=file_hash(path))],
                    'physical source receipt mismatch')
            cursor = target.execute('SELECT * FROM read_parquet(?)', [str(path)])
            names = [d[0] for d in cursor.description]
            rows = [dict(zip(names, r)) for r in cursor.fetchall()]
            require(len(rows) == count, 'physical source count mismatch')
        else:
            require(raw is None, 'zero receipt contains physical rows')
        normalized = atomic.transform_rows(entity, _native_replay_rows(entity, rows), run_id=receipt['run_id'],
            source_as_of=receipt['source_as_of'], built_at='REPLAY_AUDIT_ONLY')
        require(atomic.validate_rows(entity, normalized)['status'] == 'PASS'
                and receipt.get('atomic_row_count') == len(normalized)
                and coverage['segments'][segment.segment_id]['normalized_rows'] == len(normalized),
                'normalized receipt mismatch')
        if segment.start:
            column = atomic.DATE_COLUMN[entity]
            require(all(row.get(column) and segment.start.isoformat() <= str(row[column])[:10]
                        < segment.end.isoformat() for row in normalized), 'source rows outside receipt window')
        _scratch_budget(target)
        if normalized:
            # One bounded source segment per transaction, not one disk fsync per
            # 2,048-row transport batch. No operational tables are touched here.
            target.execute('BEGIN')
            try:
                _insert(target, entity, normalized)
                target.execute('COMMIT')
            except BaseException:
                try:
                    target.execute('ROLLBACK')
                except Exception:
                    pass
                raise
        _scratch_budget(target)
        # Validate this exact source window immediately: fail fast without
        # materializing all remaining months after an already-proven mismatch.
        # Plan windows are disjoint; coverage binds their total to the entire
        # frozen Atomic snapshot. Every source cell is still compared exactly.
        predicate = ''
        if segment.start:
            predicate = f" WHERE {atomic.DATE_COLUMN[entity]}>='{segment.start.isoformat()}' AND {atomic.DATE_COLUMN[entity]}<'{segment.end.isoformat()}'"
        if normalized:
            columns = [c for c in atomic.ENTITY_COLUMNS[entity] if c not in {'built_at', 'ingested_at'}]
            _compare(connection, target,
                f'(SELECT * FROM telchi.atomic.{entity} AT (VERSION => {snapshot}){predicate})',
                f'(SELECT * FROM telchi.atomic.{entity}{predicate})', columns, bounded=True)
        # Empty windows retain explicit verified producer receipts. Exact
        # nonempty-window equality plus full frozen counts also proves that no
        # extra actual rows can hide in an empty window or outside the plan.
        sealed[segment.segment_id] = digest(receipt)
    for entity in atomic.ENTITY_ORDER:
        guard.checkpoint()
        total = target.execute(f'SELECT count(*) FROM telchi.atomic.{entity}').fetchone()[0]
        require(total == source['entities'][entity]['row_count'], 'physical replay total coverage differs')
    return dict(contract=CONTRACT, source_receipts=sealed, source_fingerprint=history.digest(source))


class _CloseProjection:
    """Reuse the business producer over exact daily-close Atomic projections."""
    def __init__(self, con, as_of, coverage=None):
        self.con, self.as_of = con, date.fromisoformat(as_of).isoformat()
        self.invoice_dates, _ = history.invoice_cancellation_dates(con, coverage or {})
        self.native = con.execute("SELECT count(*) FROM telchi.atomic.reconciliation_event WHERE cancelled='C'").fetchone()[0] > 0
        if self.native:
            history.validate_cancellations(con, {})

    def execute(self, sql, params=None):
        end = self.as_of
        for entity in atomic.ENTITY_ORDER:
            table = 'telchi.atomic.' + entity
            relation = table
            if entity in {'receivable_document', 'collection_payment', 'payment_method_component'}:
                column = atomic.DATE_COLUMN[entity]
                if entity == 'payment_method_component':
                    relation = f'(SELECT * FROM {table} WHERE try_cast({column} AS DATE)<=DATE \'{end}\')'
                else:
                    source = history.invoice_relation(table, self.invoice_dates) if entity == 'receivable_document' else table
                    relation = f'''(SELECT * REPLACE(CASE WHEN cancelled='Y' AND try_cast(cancel_date AS DATE)>DATE '{end}'
                        THEN 'N' ELSE cancelled END AS cancelled) FROM {source}
                        WHERE try_cast({column} AS DATE)<=DATE '{end}')'''
            elif entity == 'reconciliation_participant':
                active = history.active_participants('telchi.atomic.reconciliation_event', table, end, native=self.native)
                relation = f"(SELECT * FROM {active} WHERE try_cast(reconciliation_date AS DATE)<=DATE '{end}')"
            # SQL produced by the existing kernel uses these unquoted names.
            sql = sql.replace(table + ' ', relation + ' ').replace(table + '\n', relation + '\n')
        return self.con.execute(sql, params or [])


def _derive(con, as_of, contract, built_at, coverage=None):
    ResourceGuard().preflight()
    projection = _CloseProjection(con, as_of, coverage)
    business._create_business_tables(projection, contract, built_at)
    # The unchanged business producer must agree, per obligation, with the
    # existing daily-close kernel; cash/application totals never reduce debt.
    differences = projection.execute(business._asof_relation(date.fromisoformat(as_of)) + '''
        SELECT count(*) FROM classified C FULL JOIN
        telchi.business.receivable_settlement_status S ON C.document_id=S.document_id
        WHERE C.document_id IS NULL OR S.document_id IS NULL
        OR C.reduction IS DISTINCT FROM S.economic_reduction_local
        OR C.open_amount IS DISTINCT FROM
            CASE WHEN S.cancelled IN ('Y','C') THEN 0 ELSE S.open_amount_local END
        OR C.due_date IS DISTINCT FROM S.due_date''').fetchone()[0]
    require(differences == 0, 'materialized balances disagree with daily-close kernel')


def _fingerprints(con):
    result = {}
    for table in foundation.DATASET_NAMES:
        columns = [r[0] for r in con.execute('DESCRIBE telchi.business.' + table).fetchall() if r[0] != 'built_at']
        fields = ','.join('"' + c + '"' for c in columns)
        # Existing sealed business fingerprint format, with exact replay checked separately.
        row = con.execute(f'SELECT count(*), bit_xor(hash({fields})) FROM telchi.business.{table}').fetchone()
        result[table] = [row[0], str(row[1])]
    return result


def _derivation_id(contract, as_of, coverage):
    identity = dict(source=contract, as_of=as_of)
    if coverage.get('invoice_cancellation_receipt'):
        identity['invoice_cancellation_receipt'] = coverage['invoice_cancellation_receipt']
    return 'rc_business_' + digest(identity)[:32]


def materialize(connection, *, atomic_snapshot, as_of, coverage, receipts, built_at):
    """Explicit update-time producer; caller supplies an isolated/staged catalog.

    Never selects CURRENT. A failure may leave unselected business tables, which
    cannot affect the old component's time-travel snapshot.
    """
    evidence = history.historical_snapshot(connection, snapshot=atomic_snapshot, as_of=as_of, coverage=coverage)
    evidence['board'].pop('query_execution_ms', None)
    with scratch() as con:
        replay = replay_sources(connection, snapshot=atomic_snapshot, coverage=coverage, receipts=receipts, target=con)
        contract = business._source_contract(con)
        # The requested close participates in derivation identity.
        contract['derivation_id'] = _derivation_id(contract, as_of, coverage)
        _derive(con, as_of, contract, built_at, coverage)
        fingerprints = _fingerprints(con)
        connection.execute('BEGIN')
        try:
            connection.execute('CREATE SCHEMA IF NOT EXISTS telchi.business')
            for table in foundation.DATASET_NAMES:
                schema = con.execute('DESCRIBE telchi.business.' + table).fetchall()
                columns = ','.join('"' + r[0] + '" ' + r[1] for r in schema)
                connection.execute('DROP TABLE IF EXISTS telchi.business.' + table)
                connection.execute(f'CREATE TABLE telchi.business.{table} ({columns})')
                for batch in _rows(con, 'SELECT * FROM telchi.business.' + table):
                    connection.execute(f'INSERT INTO telchi.business.{table} SELECT ' +
                        ','.join('unnest(?::VARCHAR[])' for _ in schema),
                        [[None if row[column[0]] is None else str(row[column[0]]) for row in batch]
                            for column in schema])
            connection.execute('COMMIT')
        except BaseException:
            connection.execute('ROLLBACK')
            raise
    snapshot = connection.execute("SELECT id FROM ducklake_current_snapshot('telchi')").fetchone()[0]
    component = foundation.build_component(atomic_contract=dict(derivation_id=contract['derivation_id'],
        discovery_fingerprint=digest(dict(sql=atomic.SQL, columns=atomic.ENTITY_COLUMNS)),
        aging_config_version=business.AGING_CONFIG_VERSION), derivation_contract=dict(contract,
            datasets=[dict(DATASET=k, ROW_COUNT=v[0]) for k,v in fingerprints.items()]),
        reproducibility=dict(after=fingerprints), business_built_at=built_at)
    component['history_succession'] = dict(contract=CONTRACT, atomic_snapshot_id=atomic_snapshot,
        business_snapshot_id=snapshot, as_of=as_of, coverage=deepcopy(coverage),
        receipts=deepcopy(receipts), replay=replay,
        historical_evidence=json.loads(json.dumps(evidence, default=str)))
    return component


def verify_component(connection, component):
    proof = component['history_succession']
    evidence = history.historical_snapshot(connection, snapshot=proof['atomic_snapshot_id'],
        as_of=proof['as_of'], coverage=proof['coverage'])
    evidence['board'].pop('query_execution_ms', None)
    require(json.loads(json.dumps(evidence, default=str)) == proof['historical_evidence'], 'historical evidence changed')
    with scratch() as con:
        replay = replay_sources(connection, snapshot=proof['atomic_snapshot_id'], coverage=proof['coverage'],
                                receipts=proof['receipts'], target=con)
        require(replay == proof['replay'], 'source receipt binding changed')
        contract = business._source_contract(con)
        contract['derivation_id'] = _derivation_id(contract, proof['as_of'], proof['coverage'])
        require(component['derivation_id'] == contract['derivation_id']
                and component['source_as_of'] == contract['source_as_of'], 'business derivation mismatch')
        _derive(con, proof['as_of'], contract, component['business_derivation_built_at'], proof['coverage'])
        fingerprints = _fingerprints(con)
        expected = foundation.build_component(atomic_contract=dict(derivation_id=contract['derivation_id'],
            discovery_fingerprint=digest(dict(sql=atomic.SQL, columns=atomic.ENTITY_COLUMNS)),
            aging_config_version=business.AGING_CONFIG_VERSION), derivation_contract=dict(contract,
                datasets=[dict(DATASET=k, ROW_COUNT=v[0]) for k,v in fingerprints.items()]),
            reproducibility=dict(after=fingerprints), business_built_at=component['business_derivation_built_at'])
        require({k:v for k,v in component.items() if k != 'history_succession'} == expected,
                'component metadata/fingerprint mismatch')
        for table in foundation.DATASET_NAMES:
            metadata = component['datasets'][table]
            require([metadata['row_count'], metadata['logical_fingerprint']] == fingerprints[table],
                    'sealed business fingerprint mismatch')
            columns = [r[0] for r in con.execute('DESCRIBE telchi.business.' + table).fetchall()]
            _compare(connection, con,
                f'telchi.business.{table} AT (VERSION => {proof["business_snapshot_id"]})',
                f'telchi.business.{table}', columns)
    return True


def make_candidate(base, component, *, update_run_id):
    require(base.status == 'CURRENT', 'exact CURRENT CxC base required')
    return _candidate(base, component, update_run_id=update_run_id)


def _candidate(base, component, *, update_run_id):
    # Validation also reconstructs historical transitions after their base has
    # become SUPERSEDED; construction itself still requires exact CURRENT.
    from .independent_facts_succession import KIND
    manifest = deepcopy(base.manifest)
    require(NAME in manifest['components'], 'CxC base component missing')
    manifest['components'][NAME] = deepcopy(component)
    proof = dict(contract=CONTRACT, base_manifest_sha256=digest(base.manifest), replaced_components=[NAME])
    fid = 'foundation_' + digest(dict(base=base.foundation_publication_id,
        components=manifest['components'], proof=proof))[:32]
    source_as_of = max(v['source_as_of'] for v in manifest['components'].values() if v.get('source_as_of'))
    manifest.update(foundation_publication_id=fid, update_run_id=update_run_id, candidate_kind=KIND,
        manifest_schema_version='1.0.0', base_foundation_publication_id=base.foundation_publication_id,
        independent_facts_succession=proof, source_as_of=source_as_of)
    return FoundationPublication(fid, update_run_id, previous_foundation_publication_id=base.foundation_publication_id,
        reference_version=base.reference_version, components=deepcopy(base.components), manifest=manifest,
        source_as_of=source_as_of, validation_status='PASS')


def validate_transition(store, publication, base, base_components):
    from .independent_facts_succession import MUTABLE
    m, old = publication.manifest, base.manifest
    proof = m.get('independent_facts_succession')
    require(proof == dict(contract=CONTRACT, base_manifest_sha256=digest(old), replaced_components=[NAME])
        and set(m['components']) == set(base_components)
        and publication.components == base.components
        and publication.reference_version == base.reference_version
        and publication.previous_foundation_publication_id == base.foundation_publication_id
        and m.get('base_foundation_publication_id') == base.foundation_publication_id
        and {k:v for k,v in m.items() if k not in MUTABLE} == {k:v for k,v in old.items() if k not in MUTABLE},
        'lineage/snapshot/permissions changed')
    for name in base_components:
        if name != NAME:
            require(m['components'][name] == base_components[name], 'unaffected component changed: ' + name)
    entry = m['components'][NAME]
    require(datetime.fromisoformat(entry['source_as_of']) > datetime.fromisoformat(base_components[NAME]['source_as_of']),
            'source cutoff did not advance')
    snapshot = snapshot_for(m)
    require(snapshot > snapshot_for(old) and snapshot >= entry['history_succession']['atomic_snapshot_id'],
            'component snapshot did not advance')
    expected = _candidate(base, entry, update_run_id=publication.update_run_id)
    require(publication.foundation_publication_id == expected.foundation_publication_id
            and m == expected.manifest and publication.source_as_of == expected.source_as_of,
            'candidate identity mismatch')
    with store.connection_factory() as con:
        verify_component(con, entry)
        previous_source = base_components[NAME].get('history_succession', {}).get(
            'atomic_snapshot_id', snapshot_for(old))
        next_source = entry['history_succession']['atomic_snapshot_id']
        for entity in atomic.ENTITY_ORDER:
            require(not con.execute(f'''SELECT EXISTS(SELECT 1 FROM
                (SELECT * FROM telchi.atomic.{entity} AT (VERSION => {previous_source})) P ANTI JOIN
                (SELECT * FROM telchi.atomic.{entity} AT (VERSION => {next_source})) N USING(atomic_id))''').fetchone()[0],
                'historical source identity lost: ' + entity)
    return m['components']
