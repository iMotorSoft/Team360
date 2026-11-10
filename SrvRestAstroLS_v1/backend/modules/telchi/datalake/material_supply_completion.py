"""Independent October lead-time observation; no historical open-quantity claim.

Reuses captured PO/AP/receipt lineage. Quantities and physical conversions are
not inputs to elapsed calendar days. Negative dates and unlinked receipts stay
in an explicit anomaly dataset, never clamped or silently discarded.
"""
from pathlib import Path

from . import operational_domains as obs
from . import sales_incremental as durable
from .full_refresh_capture import verify_capture
from .independent_facts_succession import checked_path
from .material_supply_derivation import build_lead_time_profiles
from .material_supply_purchasing_lineage import (
    AP_INVOICE_DATASETS, index_by_key, lineage_coverage,
    receipt_lead_time_samples, resolve_receipt_lineage,
)
from .material_supply_fact_capture import DEFAULT_DATASETS, build_select

CONTRACT = 'OBSERVED_PURCHASING_LEAD_TIME_V1'
OUTPUTS = ('observed_material_lead_time_profile', 'observed_material_lead_time_anomaly')


def derive(receipts, ap, po):
    """Exact native identities; profiles are explicitly nonnegative samples only."""
    for rows in (receipts, ap, po):
        keys = [(str(r['DocEntry']), str(r['LineNum'])) for r in rows]
        if len(keys) != len(set(keys)):
            obs.fail('duplicate purchasing completion native key')
    paths = resolve_receipt_lineage(receipts, ap, po)
    index = index_by_key(po)
    samples = receipt_lead_time_samples(paths, index)
    anomalies = []
    eligible = []
    for sample in samples:
        line = index[(sample['po_docentry'], sample['po_linenum'])]
        sample['origin_code'] = line.get('U_TIPOCOMPRA')
        if sample['order_to_receipt_days'] < 0:
            reason = 'NEGATIVE_LEAD_TIME'
        elif sample['itemcode'] != line.get('ItemCode'):
            reason = 'LINKED_ITEM_MISMATCH'
        else:
            eligible.append(sample)
            continue
        anomalies.append((sample['receipt_docentry'], sample['receipt_linenum'], reason,
                          sample['order_to_receipt_days']))
    sampled = {(s['receipt_docentry'], s['receipt_linenum']) for s in samples}
    for path in paths:
        if (path['receipt_docentry'], path['receipt_linenum']) not in sampled:
            anomalies.append((path['receipt_docentry'], path['receipt_linenum'],
                              path['lineage_path_type'] if path['po_docentry'] is None else 'INVALID_DATE', None))
    if len(eligible) + len(anomalies) != len(receipts):
        obs.fail('lead-time receipt partition incomplete')
    profiles = sorted(build_lead_time_profiles(eligible), key=lambda r: (
        r['lead_time_basis'], r['item_code'], r['supplier'], r['procurement_origin']))
    return profiles, sorted(anomalies), dict(
        contract=CONTRACT, window_start='2026-01-01', window_end='2026-10-31',
        lineage=lineage_coverage(paths), eligible_receipt_lines=len(eligible),
        anomaly_receipt_lines=len(anomalies), profile_rows=len(profiles),
        semantics='NONNEGATIVE_CALENDAR_DAYS_PER_RECEIPT_LINE_AS_CAPTURED; NOT_QUANTITY_WEIGHTED',
        historical_open_orders_accredited=False, historical_cancellation_state_accredited=False,
        current_origin_metadata='SOURCE_OBSERVED_NOT_HISTORICAL_ORIGIN_EFFECTIVITY',
        physical_unit_conversion_required=False)


def replay(con, stable):
    """Source-bound deterministic replay for the existing atomic publisher."""
    marker = stable['overlap'].get('material_lead_time')
    if marker != {'contract': CONTRACT}:
        obs.fail('unsupported material lead-time contract')
    root = Path(stable['capture_root'])
    recovery = checked_path(stable['overlap']['recovery_root'],
        durable.DATA_ROOT / 'raw/sap/full-data-lake-refresh-capture-v1')
    # Original purchasing views were already loaded by checked_captures.
    for name in ('purchase_order_line', 'ap_invoice_line'):
        directory = recovery / 'purchase-links' / name
        receipt = verify_capture(directory)
        plan = durable.read_json(directory / 'intent.json')['plan']
        spec = next(s for s in (*DEFAULT_DATASETS, *AP_INVOICE_DATASETS) if s.name == name)
        available = {table: {r['COLUMN_NAME']: r for r in durable.read_json(
            root / 'purchasing' / (table + '-columns.json'))} for table in spec.tables}
        sql, absent = build_select(spec, available)
        keys = plan['semantic_scope'].get('line_keys')
        if not keys or keys != sorted(keys) or len({tuple(k) for k in keys}) != len(keys):
            obs.fail('invalid recovered purchasing key set')
        predicate = '(' + ' OR '.join('(H."DocEntry"=? AND L."LineNum"=?)' for _ in keys) + ')'
        sql = sql.replace('H."DocDate" >= ? AND H."DocDate" < ?', predicate)
        if (plan['sql'] != sql or plan['params'] != [v for key in keys for v in key]
                or plan['keys'] != list(spec.key_fields)
                or plan['sums'] != ([spec.quantity_field] if spec.quantity_field else [])
                or plan['semantic_scope'].get('kind') != 'EXACT_MISSING_RECEIPT_REFERENCES'
                or plan['semantic_scope'].get('absent_optional_fields') != absent
                or plan['nullable_keys'] is not False or plan['ordered_keys'] is not True
                or (directory / 'failure.json').exists()):
            obs.fail('recovered purchasing projection mismatch')
        relation = obs.files_relation([p['path'] for p in receipt['pages']])
        con.execute('CREATE TEMP VIEW completion_' + name + ' AS SELECT * FROM ' + name
                    + ' UNION ALL SELECT * FROM ' + relation)
    receipts = obs.records(con, '''SELECT L.* FROM purchase_receipt_line L
        JOIN purchase_receipt H ON H."DocEntry"=L."DocEntry"
        WHERE H."CANCELED"='N' AND cast(H."DocDate" AS DATE)>=DATE '2026-01-01'
        AND cast(H."DocDate" AS DATE)<DATE '2026-11-01' ''')
    po = obs.records(con, 'SELECT * FROM completion_purchase_order_line')
    ap = obs.records(con, 'SELECT * FROM completion_ap_invoice_line')
    profiles, anomalies, coverage = derive(receipts, ap, po)
    con.execute('''CREATE TEMP TABLE observed_material_lead_time_profile(
        lead_time_basis VARCHAR,item_code VARCHAR,supplier VARCHAR,procurement_origin VARCHAR,
        sample_count BIGINT,p50_days BIGINT,p90_days BIGINT,lineage_coverage VARCHAR,confidence VARCHAR)''')
    if profiles:
        con.executemany('INSERT INTO observed_material_lead_time_profile VALUES (?,?,?,?,?,?,?,?,?)',
            [[r[k] for k in ('lead_time_basis','item_code','supplier','procurement_origin',
                'sample_count','p50_days','p90_days','lineage_coverage','confidence')] for r in profiles])
    con.execute('''CREATE TEMP TABLE observed_material_lead_time_anomaly(
        receipt_docentry VARCHAR,receipt_linenum VARCHAR,reason VARCHAR,order_to_receipt_days BIGINT)''')
    if anomalies:
        con.executemany('INSERT INTO observed_material_lead_time_anomaly VALUES (?,?,?,?)', anomalies)
    return coverage
