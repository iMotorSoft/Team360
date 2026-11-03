"""Offline, bounded operational observations in the canonical Foundation chain.

These are source-native observations, NOT replacement historical business
metrics. In particular an invoice observation is not a certified aging balance,
a BOM observation has no historical effectivity, and OINM remains a prefix.
No SAP adapter, publisher, pointer or permission management lives here.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
import os

from . import sales_incremental as durable
from .foundation_publication import FoundationPublication, FoundationReaderError
from .full_refresh_audit import audit
from .independent_facts_succession import checked_path, literal
from modules.telchi.runtime.config import DuckDBSafetyProfile, open_safe_duckdb

CONTRACT = 'CAPTURED_OPERATIONAL_OBSERVATIONS_V1'
GROUPS = {
    'production': ('bom_header', 'bom_line', 'production_order', 'production_issue'),
    'purchasing': ('purchase_order', 'purchase_order_line', 'purchase_receipt',
                   'purchase_receipt_line', 'ap_invoice', 'ap_invoice_line'),
    'collections': ('receivable_document', 'collection_payment', 'collection_allocation',
                    'reconciliation_event', 'reconciliation_participant',
                    'payment_method_component', 'payment_term'),
    'movements': ('inventory_movement',),
}
SOURCE_NAMES = {n for names in GROUPS.values() for n in names}
GROUPS['material_supply'] = ('observed_material_actual_consumption',)
NAMES = SOURCE_NAMES | {'observed_material_actual_consumption'}
LIMITS = {
    'production': 'SOURCE_FACTS_ONLY; no finished-goods receipt capture; current BOM is not historical effectivity; non-OITM issue identities are not material consumption',
    'purchasing': 'BOUNDED_DOCUMENT_OBSERVATIONS; stages separate; no purchase requests or return document capture; no certified net purchases after returns',
    'collections': 'BOUNDED_EVENTS_AND_OBSERVATIONS; invoice prefix only; no complete current aging or historical reconstructed balances; preserve on-account payments',
    'movements': 'FROZEN_NATIVE_KEY_PREFIX_ONLY; no complete-window continuity or stock derivation',
    'material_supply': 'OBSERVED_CONSUMPTION_ONLY per item/native unit, active BaseType=202 with captured order and OITM identities; historical five business datasets retained exact and not rebound; no historical BOM effectivity or full OINM window',
}


def fail(message):
    raise FoundationReaderError('Operational observations: ' + message)


@contextmanager
def database():
    con = open_safe_duckdb(profile=DuckDBSafetyProfile(threads=2, memory_limit='512MB'))
    try:
        yield con
    finally:
        con.close()


def files_relation(files):
    return 'read_parquet([' + ','.join(literal(p) for p in files) + '])'


def load_views(con, captures):
    for name, metadata in captures['captured_datasets'].items():
        if not name.replace('_', '').isalnum():
            fail('invalid source dataset name')
        con.execute('CREATE TEMP VIEW "' + name + '" AS SELECT * FROM ' +
                    files_relation([p['path'] for p in metadata['file_hashes']]))


def records(con, sql):
    cursor = con.execute(sql)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def production_reconciliation(con):
    # Current BOM classification is evidence about the observation, not a claim
    # that the recipe was valid at the historical issue timestamp.
    cases = records(con, '''SELECT I."DocEntry", I."LineNum", I."ItemCode", I."BaseEntry",
        I."BaseType", I."DocDate", I."CANCELED", I."Quantity", I."unitMsr", I."UomCode",
        CASE WHEN P."ItemCode" IS NOT NULL THEN 'INVENTORY_ITEM_IDENTITY'
             WHEN EXISTS(SELECT 1 FROM bom_line B WHERE B."Code"=I."ItemCode"
                         AND try_cast(B."Type" AS INTEGER)=290)
             THEN 'CURRENT_BOM_RESOURCE_EVIDENCE_NOT_HISTORICAL_EFFECTIVITY'
             ELSE 'UNKNOWN_NO_OITM_OR_TYPED_BOM_IDENTITY' END AS classification
        FROM production_issue I LEFT JOIN oitm P ON P."ItemCode"=I."ItemCode"
        ORDER BY I."DocEntry", I."LineNum"''')
    counts = {}
    for row in cases:
        counts[row['classification']] = counts.get(row['classification'], 0) + 1
    unresolved = [r for r in cases if r['classification'].startswith('UNKNOWN')]
    orphans = con.execute('''SELECT count(*) FROM production_issue I
        ANTI JOIN production_order O ON I."BaseEntry"=O."DocEntry"
        WHERE try_cast(I."BaseType" AS INTEGER)=202''').fetchone()[0]
    unresolved_orders = records(con, '''SELECT I."BaseEntry",count(*) AS issue_lines,
        min(I."DocDate") AS first_issue_date,max(I."DocDate") AS last_issue_date
        FROM production_issue I ANTI JOIN production_order O ON I."BaseEntry"=O."DocEntry"
        WHERE try_cast(I."BaseType" AS INTEGER)=202 GROUP BY I."BaseEntry" ORDER BY I."BaseEntry"''')
    return dict(classifications=counts, unknown_lines=unresolved, issue_order_orphans=orphans,
                unresolved_referenced_orders=unresolved_orders,
                order_link_semantics='UNRESOLVED_NOT_CAPTURED is not proof of nonexistence or pre-2026 order date',
                finished_goods_receipts_accredited=False, bom_historical_effectivity=False,
                quantity_semantics='Document quantity in its native unit; no mixed-unit sum',
                unknown_reason='No captured native entity/type evidence; names and hours are not classification')


def purchasing_reconciliation(con, previous_files):
    con.execute('CREATE TEMP VIEW previous_po_lines AS SELECT * FROM ' + files_relation(previous_files))
    missing = '''SELECT O.* FROM previous_po_lines O ANTI JOIN purchase_order_line N
        ON try_cast(O.doc_entry AS BIGINT)=N."DocEntry"
        AND try_cast(O.line_num AS BIGINT)=N."LineNum"'''
    rows = records(con, '''WITH missing AS (''' + missing + ''')
        SELECT M.doc_entry, count(*) AS missing_lines, min(M.doc_date) AS previous_date,
        min(M.canceled) AS previous_canceled, min(M.doc_status) AS previous_status,
        H."DocDate" AS observed_date, H."CANCELED" AS observed_canceled,
        H."DocStatus" AS observed_status,
        (SELECT count(*) FROM purchase_order_line L WHERE L."DocEntry"=H."DocEntry") AS observed_lines
        FROM missing M LEFT JOIN purchase_order H ON try_cast(M.doc_entry AS BIGINT)=H."DocEntry"
        GROUP BY M.doc_entry,H."DocEntry",H."DocDate",H."CANCELED",H."DocStatus"
        ORDER BY M.doc_entry''')
    for row in rows:
        if row['observed_date'] is None:
            row['finding'] = 'DOCUMENT_NOT_IN_CAPTURE; DO_NOT_INFER_DELETION'
        elif row['observed_canceled'] in ('Y', 'C'):
            row['finding'] = 'OBSERVED_CANCELLED_DOCUMENT_REVISION'
        elif row['observed_lines'] == 0:
            row['finding'] = 'OBSERVED_HEADER_WITHOUT_LINES; CAUSE_UNACCREDITED'
        else:
            row['finding'] = 'OBSERVED_WHOLE_DOCUMENT_LINE_SET_REVISION; CAUSAL_AUDIT_UNAVAILABLE'
    empty = records(con, '''SELECT H."DocEntry",H."DocDate",H."DocStatus",H."CANCELED"
        FROM purchase_order H ANTI JOIN purchase_order_line L ON H."DocEntry"=L."DocEntry"
        ORDER BY H."DocEntry"''')
    for header, line in [('purchase_order', 'purchase_order_line'),
                         ('purchase_receipt', 'purchase_receipt_line'), ('ap_invoice', 'ap_invoice_line')]:
        if con.execute(f'SELECT count(*) FROM {line} L ANTI JOIN {header} H ON L."DocEntry"=H."DocEntry"').fetchone()[0]:
            fail('orphan document line: ' + line)
    return dict(missing_previous_line_keys=sum(r['missing_lines'] for r in rows), documents=rows,
                headers_without_lines=empty, historical_lines_deleted=False,
                interpretation='Two observed revisions, not evidence of when/why SAP changed; no fabricated lines or zero receipt inference',
                metrics='Separate order/receipt/AP native facts, currency and cancellations; no cross-stage total')


def collections_reconciliation(con):
    checks = {
        'allocation_payment_orphans': '''SELECT count(*) FROM collection_allocation A ANTI JOIN
            collection_payment P ON A.payment_doc_entry=P.source_doc_entry''',
        'method_payment_orphans': '''SELECT count(*) FROM payment_method_component M ANTI JOIN
            collection_payment P ON M.payment_doc_entry=P.source_doc_entry''',
        'participant_event_orphans': '''SELECT count(*) FROM reconciliation_participant P ANTI JOIN
            reconciliation_event E ON P.reconciliation_id=E.reconciliation_id''',
    }
    result = {name: con.execute(sql).fetchone()[0] for name, sql in checks.items()}
    if any(result.values()):
        fail('collections native event link unresolved')
    result['payments_without_allocations'] = con.execute('''SELECT count(*) FROM collection_payment P
        ANTI JOIN collection_allocation A ON A.payment_doc_entry=P.source_doc_entry''').fetchone()[0]
    result['payment_groups'] = records(con, '''SELECT currency,cancelled,pay_no_document,
        count(*) AS payments,sum(try_cast(payment_total AS DECIMAL(38,12))) AS observed_total,
        sum(try_cast(on_account_amount AS DECIMAL(38,12))) AS on_account_amount
        FROM collection_payment GROUP BY ALL ORDER BY currency,cancelled,pay_no_document''')
    result['allocation_target_types'] = records(con, '''SELECT target_object_type,count(*) AS rows
        FROM collection_allocation GROUP BY ALL ORDER BY target_object_type''')
    result.update(current_global_aging_accredited=False, historical_balances_accredited=False,
                  absent_coverage_is_zero=False, on_account_payments_retained=True,
                  invoice_grain='DocEntry + installment_id; never sum repeated document totals across installments',
                  application_semantics='Exact source-native RCT2 link only; no date/amount inference')
    return result


def verify_plan(root, domain, name, plan):
    """Bind reuse to the existing source projection, not an arbitrary receipt."""
    from .material_supply_fact_capture import DEFAULT_DATASETS, build_select
    from .material_supply_purchasing_lineage import AP_INVOICE_DATASETS
    from .receivables_collections_atomic import SQL as RC_SQL
    cycle = durable.read_json(root / 'cycle-plan.json')
    scope = plan.get('semantic_scope', {})
    if domain in ('production', 'purchasing'):
        specs = {s.name:s for s in (*DEFAULT_DATASETS, *AP_INVOICE_DATASETS)}
        spec = specs[name]
        available = {}
        for table in spec.tables:
            rows = durable.read_json(root / domain / (table + '-columns.json'))
            available[table] = {r['COLUMN_NAME']:r for r in rows}
        sql, absent = build_select(spec, available)
        params = [] if spec.kind == 'full' else [cycle['year_start'], cycle['end_exclusive']]
        sums = [spec.quantity_field] if spec.quantity_field and spec.quantity_field not in absent else []
        if (plan['sql'] != sql or plan['params'] != params or plan['keys'] != list(spec.key_fields)
                or plan['sums'] != sums or scope.get('absent_optional_fields') != absent
                or scope.get('kind') != ('CURRENT_MASTER_SNAPSHOT' if spec.kind == 'full' else 'BOUNDED_YEAR_DOCUMENT_STATE')
                or scope.get('start') != (params[0] if params else None)
                or scope.get('end_exclusive') != (params[1] if params else None)
                or plan['nullable_keys'] is not False or plan['ordered_keys'] is not True):
            fail('document source projection/scope mismatch: ' + name)
    elif domain == 'collections':
        params = [] if name == 'payment_term' else [cycle['collections_start'],cycle['end_exclusive']] * (4 if name == 'payment_method_component' else 1)
        if (plan['sql'] != RC_SQL[name] or plan['params'] != params
                or scope.get('kind') != 'BOUNDED_OVERLAP_PLUS_GAP'
                or scope.get('start') != (params[0] if params else None)
                or scope.get('end_exclusive') != (params[1] if params else None)
                or plan['nullable_keys'] is not True or plan['ordered_keys'] is not False):
            fail('collections source projection/scope mismatch: ' + name)
    elif domain == 'movements':
        from .sql import oinm_extract_sql
        columns = durable.read_json(root / domain / 'oinm-columns.json')
        sql = oinm_extract_sql(columns).replace(' AND M."TransNum" >= ? AND M."TransNum" < ?', '')
        # The window is explicit in the source plan, never advanced by this adapter.
        if (plan['sql'] != sql or plan['params'] != [scope.get('start'),scope.get('end_exclusive')]
                or scope.get('end_exclusive') != cycle['end_exclusive']
                or scope.get('kind') != 'BOUNDED_OVERLAP_PLUS_GAP'
                or scope.get('source_columns') != columns
                or plan['keys'] != ['TransNum','TransSeq'] or plan['sums'] != ['InQty','OutQty']):
            fail('movement source projection/scope mismatch')


def checked_captures(root):
    root = checked_path(root, durable.DATA_ROOT / 'raw/sap/full-data-lake-refresh-capture-v1')
    result = audit(root)
    if set(result['captured_datasets']) != SOURCE_NAMES | {'stock','oitm','ocrd','owhs','oslp'}:
        fail('capture dataset registry mismatch')
    for name, value in result['relationships'].items():
        if value.get('status') == 'NOT_VERIFIED':
            fail('capture relationship was not checked: ' + name)
    from .full_refresh_capture import CONTRACT as CAPTURE_CONTRACT
    for name, metadata in result['captured_datasets'].items():
        directory = root / metadata['domain'] / name
        intent = durable.read_json(directory / 'intent.json')
        plan = intent['plan']
        if name in SOURCE_NAMES:
            verify_plan(root, metadata['domain'], name, plan)
        if plan.get('contract') != CAPTURE_CONTRACT or durable.digest(plan) != intent['plan_sha256']:
            fail('capture plan binding mismatch')
        paths = sorted(directory.glob('checkpoint-*.json'))
        pages = [durable.read_json(p) for p in paths]
        if len(pages) != metadata['file_count']:
            fail('checkpoint set mismatch')
        prefix = directory / 'prefix-reconciliation.json'
        if prefix.exists():
            proof = durable.read_json(prefix)
            if (durable.file_hash(directory / 'failure.json') != proof['original_failure_sha256']
                    or proof.get('coverage_complete') is not False
                    or proof.get('published') is not False
                    or proof.get('first_key') != plan['keys'][0]):
                fail('prefix failure or coverage binding mismatch')
        for page in pages:
            checked_path(page['path'], directory)
            checked_path(page['manifest_path'], directory)
            manifest = durable.read_json(Path(page['manifest_path']))
            unsigned = dict(manifest)
            unsigned.pop('manifest_hash', None)
            if (durable.digest(unsigned) != page['manifest_hash']
                    or manifest.get('manifest_hash') != page['manifest_hash']
                    or manifest.get('contract') != CAPTURE_CONTRACT
                    or manifest.get('dataset') != name
                    or manifest.get('plan_sha256') != intent['plan_sha256']
                    or manifest.get('semantic_scope') != plan['semantic_scope']
                    or manifest.get('source_as_of') != intent['source_before']['utc']
                    or manifest.get('file_references') != [page['path']]
                    or manifest.get('file_hashes') != [page['sha256']]):
                fail('source manifest provenance mismatch')
    return root, result


def movement_reconciliation(con, base, root, captures):
    from .foundation_reader import pinned_atomic_relation
    directory = root / 'movements/inventory_movement'
    plan = durable.read_json(directory / 'intent.json')['plan']
    prefix = durable.read_json(directory / 'prefix-reconciliation.json')
    source = files_relation([p['path'] for p in captures['captured_datasets']['inventory_movement']['file_hashes']])
    previous = pinned_atomic_relation('oinm','inventory_movement',base.manifest['facts_base_snapshot_id'])
    con.execute('CREATE OR REPLACE TEMP VIEW observed_movements AS SELECT * FROM ' + source)
    con.execute('''CREATE OR REPLACE TEMP VIEW prior_overlap AS SELECT * FROM ''' + previous + '''
        WHERE try_cast(doc_date AS DATE)>=''' + literal(plan['params'][0]) + '''::DATE
        AND try_cast(doc_date AS DATE)<''' + literal(plan['params'][1]) + '''::DATE
        AND try_cast(trans_num AS BIGINT)<=''' + str(int(prefix['upper_native_key'])))
    missing = con.execute('''SELECT count(*) FROM prior_overlap P ANTI JOIN observed_movements N
        ON try_cast(P.trans_num AS BIGINT)=N."TransNum" AND try_cast(P.trans_seq AS BIGINT)=N."TransSeq"''').fetchone()[0]
    checks = [
        'P.item_code IS DISTINCT FROM N."ItemCode"',
        'P.warehouse IS DISTINCT FROM N."Warehouse"',
        'try_cast(P.doc_date AS DATE) IS DISTINCT FROM cast(N."DocDate" AS DATE)',
        'try_cast(P.trans_type AS DECIMAL(18,6)) IS DISTINCT FROM cast(N."TransType" AS DECIMAL(18,6))',
        'try_cast(P.in_qty AS DECIMAL(38,12)) IS DISTINCT FROM try_cast(N."InQty" AS DECIMAL(38,12))',
        'try_cast(P.out_qty AS DECIMAL(38,12)) IS DISTINCT FROM try_cast(N."OutQty" AS DECIMAL(38,12))',
    ]
    changed = con.execute('''SELECT count(*) FROM prior_overlap P JOIN observed_movements N
        ON try_cast(P.trans_num AS BIGINT)=N."TransNum" AND try_cast(P.trans_seq AS BIGINT)=N."TransSeq"
        WHERE ''' + ' OR '.join(checks)).fetchone()[0]
    quality = records(con, '''SELECT count(*) AS rows,count(DISTINCT ("TransNum","TransSeq")) AS native_keys,
        min("DocDate") AS first_date,max("DocDate") AS last_date,
        count(*) FILTER(WHERE try_cast("InQty" AS DECIMAL(38,12)) IS NULL
            OR try_cast("OutQty" AS DECIMAL(38,12)) IS NULL) AS invalid_quantities,
        count(*) FILTER(WHERE try_cast("InQty" AS DECIMAL(38,12))<0
            OR try_cast("OutQty" AS DECIMAL(38,12))<0) AS negative_native_quantities
        FROM observed_movements''')[0]
    return dict(continuity_accredited=False,historical_component_retained=True,
        prefix_upper_native_key=prefix['upper_native_key'],quality=quality,
        previous_overlap_rows=con.execute('SELECT count(*) FROM prior_overlap').fetchone()[0],
        previous_overlap_missing_native_keys=missing,previous_overlap_changed_core_rows=changed,
        signed_quantity_semantics='InQty-OutQty, no movement inferred from stock snapshots',
        reason='Frozen native-key prefix is not full-window coverage; unchanged overlap cannot prove the missing tail')


def reconcile(root, base, connection_factory=None):
    root, captures = checked_captures(root)
    previous = base.manifest['components']['purchasing']['datasets']['purchase_order_line']
    paths = previous['file_references']
    if [durable.file_hash(Path(p)) for p in paths] != previous['file_hashes']:
        fail('previous purchasing bytes changed')
    with database() as con:
        load_views(con, captures)
        production = production_reconciliation(con)
        purchasing = purchasing_reconciliation(con, paths)
        collections = collections_reconciliation(con)
        consumption = build_observed_consumption(con, root)
    if connection_factory is None:
        from .ducklake import DuckLakeConnector
        connector = DuckLakeConnector()
        connection_factory = lambda: connector.session(read_only=True)
    with connection_factory() as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        movements = movement_reconciliation(con, base, root, captures)
    return dict(contract=CONTRACT, base=base.foundation_publication_id,
                base_manifest_sha256=durable.digest(base.manifest), capture_root=str(root),
                capture_count=len(captures['captured_datasets']),
                captured_rows=sum(d['rows'] for d in captures['captured_datasets'].values()),
                captures=captures, production=production, purchasing=purchasing,
                collections=collections, limits=LIMITS,
                movements=movements,
                material_supply=dict(recalculated='OBSERVED_NATIVE_UNIT_CONSUMPTION_ONLY',
                    observed_material_actual_consumption=consumption, historical_component_retained=True,
                    dependency_manifest_sha256=durable.digest(base.manifest['components']['material_supply']),
                    datasets=base.manifest['components']['material_supply']['datasets']))


def observation_contract(manifest):
    value = manifest.get('operational_observations')
    if value is None:
        return None
    from .independent_facts_succession import KIND, CONTRACT as STOCK_CONTRACT
    from .reference_compatibility import KIND as REFERENCE_KIND
    from .sales_facts_transition import KIND as SALES_KIND
    proof = manifest.get('independent_facts_succession', {})
    if (manifest.get('candidate_kind') not in {KIND, REFERENCE_KIND, SALES_KIND}
            or not isinstance(value, dict) or value.get('contract') != CONTRACT
            or not isinstance(proof, dict) or proof.get('contract') not in {CONTRACT, STOCK_CONTRACT}
            or (proof.get('contract') != CONTRACT and not isinstance(manifest.get('sales_facts_revalidation'), dict))):
        fail('unvalidated operational dispatch')
    # Canonical successor validation preserves this complete envelope verbatim
    # when stock, sales or Reference changes. Like sealed sales, observations
    # retain their own cuts and dependencies; they are not silently refreshed.
    return value


def relation(manifest, domain, dataset):
    stable = observation_contract(manifest)
    if stable is None or domain not in GROUPS or dataset not in GROUPS[domain]:
        fail('observation dataset is not in the declared domain')
    metadata = stable['datasets'][dataset]
    path = checked_path(metadata['path'], durable.DATA_ROOT / 'staging')
    if durable.file_hash(path) != metadata['sha256']:
        fail('observation bytes changed before exposure')
    return '(SELECT * FROM read_parquet(' + literal(path) + '))'


def build_observed_consumption(con, root):
    """Reuse the canonical kernel, split by native unit; no BOM conversion.

    Exclude cancelled/unknown states, noninventory identities, unresolved order
    references and unitless rows from this derivative, NOT from source facts.
    Kernel six-decimal quantities must reconcile to exact decimal source sums.
    """
    from datetime import date, timedelta
    from decimal import Decimal, ROUND_HALF_EVEN
    from .material_supply_derivation import build_actual_consumption
    cycle = durable.read_json(Path(root) / 'cycle-plan.json')
    first, last = date.fromisoformat(cycle['year_start']), date.fromisoformat(cycle['end_exclusive']) - timedelta(days=1)
    rows = records(con, '''SELECT I.* FROM production_issue I JOIN oitm P ON I."ItemCode"=P."ItemCode"
        JOIN production_order O ON I."BaseEntry"=O."DocEntry"
        WHERE try_cast(I."BaseType" AS DECIMAL(18,6))=202 AND I."CANCELED"='N'
        AND (nullif(trim(I."unitMsr"),'') IS NOT NULL OR nullif(trim(I."UomCode"),'') IS NOT NULL)
        ORDER BY I."DocEntry",I."LineNum"''')
    groups = {}
    for row in rows:
        key = tuple(row.get(k) for k in ('ItemCode','unitMsr','UomCode','NumPerMsr'))
        groups.setdefault(key, []).append(row)
    con.execute('''CREATE TEMP TABLE observed_material_actual_consumption(
        item_code VARCHAR,native_unit_msr VARCHAR,native_uom_code VARCHAR,native_num_per_msr VARCHAR,
        actual_consumption_qty VARCHAR,window_start VARCHAR,window_end VARCHAR,issue_lines BIGINT,
        consumption_basis VARCHAR)''')
    for key, issues in sorted(groups.items(),key=lambda pair:repr(pair[0])):
        output = build_actual_consumption(issues,window_start=first,window_end=last)
        if len(output) != 1:
            fail('canonical consumption kernel did not return one native item group')
        quantity = sum((Decimal(str(row['Quantity'])) for row in issues),Decimal(0)).quantize(Decimal('.000001'),rounding=ROUND_HALF_EVEN)
        if Decimal(str(output[0]['actual_consumption_qty'])) != quantity:
            fail('consumption kernel differs from exact native quantity control')
        con.execute('INSERT INTO observed_material_actual_consumption VALUES (?,?,?,?,?,?,?,?,?)',
            [*key,str(quantity),first.isoformat(),last.isoformat(),len(issues),'ACTIVE_INVENTORY_ITEM_ISSUE_TO_CAPTURED_PRODUCTION_ORDER'])
    return dict(rows=len(groups),included_issue_lines=len(rows),
                excluded_issue_lines=con.execute('SELECT count(*) FROM production_issue').fetchone()[0]-len(rows),
                output_semantics='Source document quantity, split by item/unit/factor; no physical conversion or raw-material classification',
                kernel='material_supply_derivation.build_actual_consumption',
                window_start=first.isoformat(),window_end=last.isoformat())


def verify_datasets(stable, captures):
    if set(stable['datasets']) != NAMES or stable.get('limits') != LIMITS:
        fail('observation registry or limitations mismatch')
    with database() as con:
        load_views(con, captures)
        build_observed_consumption(con, stable['capture_root'])
        for domain, names in GROUPS.items():
            for name in names:
                metadata = stable['datasets'][name]
                path = checked_path(metadata['path'], durable.DATA_ROOT / 'staging')
                if durable.file_hash(path) != metadata['sha256']:
                    fail('output bytes mismatch: ' + name)
                con.execute('CREATE OR REPLACE TEMP VIEW actual AS SELECT * FROM read_parquet(' + literal(path) + ')')
                schema = [[r[0], r[1]] for r in con.execute('DESCRIBE actual').fetchall()]
                if schema != metadata['schema']:
                    fail('output schema mismatch: ' + name)
                count = con.execute('SELECT count(*) FROM actual').fetchone()[0]
                expected_count = con.execute('SELECT count(*) FROM ' + name).fetchone()[0]
                if count != metadata['row_count'] or count != expected_count:
                    fail('output row count mismatch: ' + name)
                for left, right in [(name, 'actual'), ('actual', name)]:
                    if con.execute(f'SELECT EXISTS((SELECT * FROM {left}) EXCEPT ALL (SELECT * FROM {right}))').fetchone()[0]:
                        fail('exact source replay mismatch: ' + name)
                if name not in SOURCE_NAMES:
                    continue
                directory = Path(stable['capture_root']) / domain / name
                plan = durable.read_json(directory / 'intent.json')['plan']
                group = ','.join('"' + k + '"' for k in plan['keys'])
                if con.execute(f'SELECT EXISTS(SELECT {group} FROM actual GROUP BY {group} HAVING count(*)>1)').fetchone()[0]:
                    fail('duplicate native observation identity: ' + name)
                if not plan['nullable_keys']:
                    predicate = ' OR '.join('"' + k + '" IS NULL' for k in plan['keys'])
                    if con.execute('SELECT EXISTS(SELECT 1 FROM actual WHERE ' + predicate + ')').fetchone()[0]:
                        fail('null native observation identity: ' + name)


def canonical_json(value):
    return json.loads(json.dumps(value, default=str))


def make_candidate(base, root, destination):
    """Prepare ALL captured domains, without activating or replacing old metrics.

    Observations live in the existing independent-facts envelope like the sealed
    sales evidence. The eight legacy metric components keep their exact cuts and
    contracts: no copied September derivation is labelled as current November.
    """
    from .independent_facts_succession import KIND
    from .sales_facts_transition import NAMES as COMPONENT_NAMES
    if set(base.manifest['components']) != COMPONENT_NAMES:
        fail('eight-component base required')
    if observation_contract(base.manifest) is not None:
        fail('observation successor revisions require an explicit overlap adapter')
    destination = checked_path(destination, durable.DATA_ROOT / 'staging')
    report = canonical_json(reconcile(root, base))
    destination.mkdir(parents=True, exist_ok=False)
    stable = dict(contract=CONTRACT, capture_root=report['capture_root'], limits=LIMITS,
                  base_manifest_sha256=durable.digest(base.manifest),
                  reference_version=base.reference_version, datasets={},
                  reconciliation_path=str(destination / 'reconciliation.json'),
                  reconciliation_sha256=durable.digest(report))
    durable.seal(destination / 'reconciliation.json', report)
    with database() as con:
        load_views(con, report['captures'])
        build_observed_consumption(con, root)
        for name in sorted(NAMES):
            path = destination / (name + '.parquet')
            con.execute('COPY ' + name + ' TO ' + literal(path) + ' (FORMAT PARQUET, COMPRESSION ZSTD)')
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
            stable['datasets'][name] = dict(path=str(path),sha256=durable.file_hash(path),
                row_count=con.execute('SELECT count(*) FROM ' + name).fetchone()[0],
                schema=[[r[0],r[1]] for r in con.execute('DESCRIBE ' + name).fetchall()])
    durable.sync_dir(destination)
    manifest = deepcopy(base.manifest)
    proof = dict(contract=CONTRACT, base_manifest_sha256=durable.digest(base.manifest),
                 replaced_components=[], retained_components_sha256=durable.digest(manifest['components']),
                 observations_sha256=durable.digest(stable))
    identity = 'foundation_' + durable.digest(dict(base=base.foundation_publication_id, proof=proof))[:32]
    manifest.update(candidate_kind=KIND, manifest_schema_version='1.0.0',
                    foundation_publication_id=identity, update_run_id=destination.name,
                    base_foundation_publication_id=base.foundation_publication_id,
                    independent_facts_succession=proof, operational_observations=stable)
    candidate = FoundationPublication(identity, destination.name,
        previous_foundation_publication_id=base.foundation_publication_id,
        reference_version=base.reference_version, components=deepcopy(base.components),
        manifest=manifest, source_as_of=base.source_as_of, validation_status='PASS')
    verify_datasets(stable, report['captures'])
    durable.seal(destination / 'foundation-candidate.json', candidate.as_row())
    return candidate


def validate_transition(publication, base, base_components, connection_factory=None):
    stable = observation_contract(publication.manifest)
    if stable is None:
        fail('missing observation contract')
    mutable = {'foundation_publication_id','update_run_id','candidate_kind','manifest_schema_version',
               'base_foundation_publication_id','independent_facts_succession','operational_observations'}
    manifest, old = publication.manifest, base.manifest
    proof = dict(contract=CONTRACT, base_manifest_sha256=durable.digest(old),
                 replaced_components=[], retained_components_sha256=durable.digest(base_components),
                 observations_sha256=durable.digest(stable))
    identity = 'foundation_' + durable.digest(dict(base=base.foundation_publication_id, proof=proof))[:32]
    if (publication.foundation_publication_id != identity
            or manifest.get('base_foundation_publication_id') != base.foundation_publication_id
            or publication.previous_foundation_publication_id != base.foundation_publication_id
            or publication.reference_version != base.reference_version
            or publication.components != base.components
            or manifest['components'] != base_components
            or manifest.get('independent_facts_succession') != proof
            or stable.get('base_manifest_sha256') != durable.digest(old)
            or stable.get('reference_version') != base.reference_version
            or {k:v for k,v in manifest.items() if k not in mutable} !=
               {k:v for k,v in old.items() if k not in mutable}):
        fail('base, identity, snapshots, sealed components or permissions changed')
    report = canonical_json(reconcile(stable['capture_root'], base, connection_factory))
    path = checked_path(stable['reconciliation_path'], durable.DATA_ROOT / 'staging')
    if (durable.read_json(path) != report or durable.digest(report) != stable['reconciliation_sha256']):
        fail('independently recomputed reconciliation differs')
    verify_datasets(stable, report['captures'])
    return base_components


def verify_reader(con, access):
    stable = observation_contract(access.manifest)
    if stable is None:
        fail('reader lacks operational observations')
    _, captures = checked_captures(stable['capture_root'])
    result = {}
    with database() as derived:
        load_views(derived, captures)
        build_observed_consumption(derived, stable['capture_root'])
        expected_consumption = derived.execute('SELECT * FROM observed_material_actual_consumption').fetchall()
    # An independent connection replays the same canonical kernel; native source
    # readers below are compared to raw, not to candidate counts/aggregates.
    for domain, names in GROUPS.items():
        result[domain] = {}
        for name in names:
            actual = access.operational_observation(domain, name)
            if name not in SOURCE_NAMES:
                observed = con.execute('SELECT * FROM ' + actual).fetchall()
                if sorted(observed,key=repr) != sorted(expected_consumption,key=repr):
                    fail('live derived consumption differs')
                result[domain][name] = len(observed)
                continue
            source = files_relation([p['path'] for p in captures['captured_datasets'][name]['file_hashes']])
            for left, right in [(source,actual),(actual,source)]:
                if con.execute(f'SELECT EXISTS((SELECT * FROM {left}) EXCEPT ALL (SELECT * FROM {right}))').fetchone()[0]:
                    fail('live native reader replay differs: ' + name)
            result[domain][name] = con.execute('SELECT count(*) FROM ' + actual).fetchone()[0]
    return dict(status='SOURCE_OBSERVATION_READERS_EXACT',datasets=result,limits=LIMITS,
                historical_business_metrics_refreshed=False)

