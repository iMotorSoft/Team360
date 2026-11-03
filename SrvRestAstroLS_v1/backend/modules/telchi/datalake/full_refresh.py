"""Manual sequential refresh capture of existing contracts, no scheduler/publisher.

This adapter does not bypass Foundation's compatibility gates. Captured facts
are not published merely because extraction succeeded. No new SAP tables.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, timedelta
import json
from pathlib import Path

from . import sales_incremental as durable
from . import reference_update as reference
from . import receivables_collections_atomic as rc
from .ducklake import DATA_ROOT
from .full_refresh_capture import CaptureSession, DomainBudget, CLOCK_SQL, CONTRACT
from .material_supply_fact_capture import DEFAULT_DATASETS, build_select, COLUMN_DISCOVERY_SQL
from .material_supply_purchasing_lineage import AP_INVOICE_DATASETS
from .source import HanaReadOnlySource
from .sql import OINM_FIELD_CANDIDATES, OINM_REQUIRED_FIELDS, oinm_extract_sql
from modules.telchi.runtime.resource_guard import ResourceGuard, SafeAbort

BUDGETS = {
    # OITW volume measured 2026-11-01: 1,385,179 rows. One server cursor;
    # no historical inventory rebuilt. Limits include controls and closure.
    'inventory': DomainBudget(40, 2400, 1600000, operation_seconds=1800),
    'movements': DomainBudget(100, 2400, 2000000, operation_seconds=1800),
    'production': DomainBudget(80, 2400, 300000),
    'purchasing': DomainBudget(100, 2400, 300000),
    'collections': DomainBudget(100, 3600, 500000, operation_seconds=1800),
    'reference': DomainBudget(40, 1800, 100000),
}


def session(root, name):
    budget = BUDGETS[name]
    return CaptureSession(root/name, HanaReadOnlySource(limits=budget.transport()), budget)


def facts(s, specs, start, end):
    schema = {}
    results = {}
    for spec in specs:
        try:
            for table in spec.tables:
                if table not in schema:
                    cache = s.root / (table + '-columns.json')
                    if cache.exists():
                        columns = durable.read_json(cache)
                    else:
                        columns = s.query('columns_' + table, COLUMN_DISCOVERY_SQL, ('TELCHI', table))
                        durable.seal(cache, columns)
                    schema[table] = {r['COLUMN_NAME']: r for r in columns}
            sql, absent = build_select(spec, schema)
            scope = dict(kind='CURRENT_MASTER_SNAPSHOT' if spec.kind == 'full' else 'BOUNDED_YEAR_DOCUMENT_STATE',
                         start=None if spec.kind == 'full' else start, end_exclusive=None if spec.kind == 'full' else end,
                         absent_optional_fields=absent,
                         limitation='No claim of modifications outside this business-date scope; no CDC')
            params = () if spec.kind == 'full' else (start, end)
            sums = [spec.quantity_field] if spec.quantity_field and spec.quantity_field not in absent else []
            results[spec.name] = s.capture(spec.name, sql, params, keys=spec.key_fields, sums=sums, semantic_scope=scope)
            print(json.dumps(dict(dataset=spec.name, status=results[spec.name]['status'], rows=results[spec.name]['row_count'])), flush=True)
        except Exception as exc:
            results[spec.name] = dict(status='CAPTURE_BLOCKED', error_type=type(exc).__name__, code=str(exc)[:200])
            print(json.dumps(dict(dataset=spec.name, **results[spec.name])), flush=True)
    return results


def inventory(s):
    # Same source projection as INVENTORY_EXTRACT_SQL, without artificial key
    # bounds: the entire current state is a single statement-consistent cursor.
    sql = 'SELECT W."ItemCode", W."WhsCode", W."OnHand", W."IsCommited", W."OnOrder" FROM "TELCHI"."OITW" W ORDER BY W."ItemCode", W."WhsCode"'
    return {'stock': s.capture('stock', sql, keys=['ItemCode', 'WhsCode'],
        sums=['OnHand', 'IsCommited', 'OnOrder'], semantic_scope=dict(kind='CURRENT_STOCK_STATEMENT_SNAPSHOT',
        history_rebuilt=False, branch='ONLY_ACCREDITED_REFERENCE_CROSSWALKS',
        limitation='SAP statement observation; not simultaneous with other domains'))}


def movements(s, start, end):
    cache = s.root/'oinm-columns.json'
    if cache.exists():
        available = durable.read_json(cache)
    else:
        available = {}
        for canonical, candidates in OINM_FIELD_CANDIDATES:
            for column in candidates:
                try:
                    s.query('probe_oinm_' + canonical + '_' + column,
                        f'SELECT TOP 0 M."{column}" FROM "TELCHI"."OINM" M')
                    available[canonical] = column
                    break
                except Exception as exc:
                    # Only HANA invalid-column error means ABSENT. Network,
                    # auth and timeout failures never become optional fields.
                    if not exc.args or exc.args[0] != 260:
                        raise
        durable.seal(cache, available)
    if not OINM_REQUIRED_FIELDS.issubset(available) or 'TransSeq' not in available:
        raise ValueError('ACCREDITED_OINM_SCHEMA_OR_SEQUENCE_MISSING')
    sql = oinm_extract_sql(available)
    sql = sql.replace(' AND M."TransNum" >= ? AND M."TransNum" < ?', '')
    return {'inventory_movement': s.capture('inventory_movement', sql, (start, end),
        keys=['TransNum', 'TransSeq'], sums=['InQty', 'OutQty'],
        semantic_scope=dict(kind='BOUNDED_OVERLAP_PLUS_GAP', start=start, end_exclusive=end,
            limitation='No CDC or corrections outside this explicit business-date overlap',
            native_identity='TransNum+TransSeq', source_columns=available))}


RC_KEYS = {
    'receivable_document': ['source_doc_entry', 'installment_id'],
    'collection_payment': ['source_doc_entry'],
    'collection_allocation': ['payment_doc_entry', 'target_object_type', 'target_doc_entry', 'invoice_id',
        'target_document_line', 'installment_id', 'link_date', 'allocated_amount', 'allocated_amount_foreign',
        'allocated_amount_system', 'document_rate', 'paid_amount'],
    'reconciliation_event': ['reconciliation_id'],
    'reconciliation_participant': ['reconciliation_id', 'source_line_id'],
    'payment_method_component': ['payment_doc_entry', 'method_code', 'component_source_table', 'source_line_id'],
    'payment_term': ['payment_term_code'],
}


def collections(s, start, end):
    results = {}
    for entity in rc.ENTITY_ORDER:
        try:
            sql = rc.SQL[entity]
            # Four UNION arms use the same business window; all source fields
            # and grouping are exactly those of the existing extraction.
            params = () if entity == 'payment_term' else (start, end) * (4 if entity == 'payment_method_component' else 1)
            results[entity] = s.capture(entity, sql, params, keys=RC_KEYS[entity], nullable_keys=True,
                ordered_keys=False, semantic_scope=dict(kind='BOUNDED_OVERLAP_PLUS_GAP',
                start=start if params else None, end_exclusive=end if params else None,
                limitation='Historical balances/payments before overlap NOT refreshed; aging not accredited by this capture'))
            print(json.dumps(dict(dataset=entity, status=results[entity]['status'], rows=results[entity]['row_count'])), flush=True)
        except Exception as exc:
            results[entity] = dict(status='CAPTURE_BLOCKED', error_type=type(exc).__name__, code=str(exc)[:200])
            print(json.dumps(dict(dataset=entity, **results[entity])), flush=True)
    return results


def masters(s):
    results = {}
    for table, key in [('OITM', 'ItemCode'), ('OCRD', 'CardCode'), ('OWHS', 'WhsCode'), ('OSLP', 'SlpCode')]:
        sql = getattr(reference, table + '_SQL').strip() + ' ORDER BY ' + ('S.' if table == 'OSLP' else '') + '"' + key + '"'
        try:
            results[table] = s.capture(table.lower(), sql, keys=[key], semantic_scope=dict(kind='CURRENT_MASTER_SNAPSHOT',
                identity='SOURCE_NATIVE; canonical merge not yet performed',
                classification='OBSERVED_U_FormaFarmac; missing never inferred'))
            print(json.dumps(dict(dataset=table, status=results[table]['status'], rows=results[table]['row_count'])), flush=True)
        except Exception as exc:
            results[table] = dict(status='CAPTURE_BLOCKED', error_type=type(exc).__name__, code=str(exc)[:200])
            print(json.dumps(dict(dataset=table, **results[table])), flush=True)
    return results


def run(root, *, domains=tuple(BUDGETS)):
    root = Path(root).resolve()
    if root.parent != (DATA_ROOT/'raw/sap'/CONTRACT).resolve():
        raise ValueError('ROOT_OUTSIDE_CAPTURE_CONTRACT')
    root.mkdir(parents=True, exist_ok=True)
    guard = ResourceGuard()
    guard.preflight()
    from .sales_controlled_block import extraction_lock, CONTRACT as EXTRACTION_LOCK_CONTRACT
    shared = DATA_ROOT/'raw/sap'/EXTRACTION_LOCK_CONTRACT
    shared.mkdir(parents=True, exist_ok=True)
    with extraction_lock(shared), durable.locked(root):
        plan_path = root/'cycle-plan.json'
        if not plan_path.exists():
            clock_source = HanaReadOnlySource(limits=BUDGETS['reference'].transport())
            clock = clock_source.query_read_only('cycle_cutoff', CLOCK_SQL)[0]
            durable.seal(root/'cycle-clock-query.json', clock_source.query_log)
            durable.seal(plan_path, dict(contract=CONTRACT, started_at=durable.now(), source_clock=clock,
                end_exclusive=(date.fromisoformat(clock['source_date'])+timedelta(days=1)).isoformat(),
                year_start=clock['source_date'][:4]+'-01-01', collections_start='2026-09-21',
                budgets={k:asdict(v) for k,v in BUDGETS.items()}, scheduler_enabled=False,
                sap_write_count=0, foundation_publication='NOT_PERFORMED_BY_CAPTURE',
                source_timezone='Observed source-local/UTC offset only; IANA timezone not accredited'))
        plan = durable.read_json(plan_path)
        results = {}
        for name in domains:
            print('DOMAIN_START ' + name, flush=True)
            try:
                s = session(root, name)
                if name == 'inventory':
                    result = inventory(s)
                elif name == 'movements':
                    result = movements(s, '2026-09-17', plan['end_exclusive'])
                elif name == 'production':
                    result = facts(s, DEFAULT_DATASETS[:4], plan['year_start'], plan['end_exclusive'])
                elif name == 'purchasing':
                    result = facts(s, DEFAULT_DATASETS[4:]+AP_INVOICE_DATASETS, plan['year_start'], plan['end_exclusive'])
                elif name == 'collections':
                    result = collections(s, plan['collections_start'], plan['end_exclusive'])
                else:
                    result = masters(s)
                results[name] = result
            except Exception as exc:
                results[name] = dict(status='DOMAIN_BLOCKED', error_type=type(exc).__name__, code=str(exc)[:200])
                print(json.dumps(dict(domain=name, **results[name])), flush=True)
                if isinstance(exc, SafeAbort):
                    break
            result_path = root/(name+'-result.json')
            if not result_path.exists():
                durable.seal(result_path, results[name])
        return dict(status='PARTIAL', plan=plan, results=results, root=str(root),
                    foundation_promoted=False, scheduler_enabled=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--domains', nargs='+', choices=tuple(BUDGETS), default=list(BUDGETS))
    args = parser.parse_args()
    if not args.run_id.replace('-', '').replace('_', '').isalnum():
        parser.error('invalid run id')
    result = run(DATA_ROOT/'raw/sap'/CONTRACT/args.run_id, domains=args.domains)
    print(json.dumps(dict(status=result['status'], root=result['root'], foundation_promoted=False)), flush=True)
    # Capture success is not completion of the requested published universe.
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
