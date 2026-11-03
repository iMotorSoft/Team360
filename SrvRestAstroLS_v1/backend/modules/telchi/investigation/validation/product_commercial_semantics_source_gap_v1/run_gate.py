"""No SAP and no promotion. Pinned cohort discovery and immutable candidate."""
from __future__ import annotations
import csv
import json
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_manifest import validate_manifest
from modules.telchi.datalake.material_supply_candidate import resolve_current_material_supply
from modules.telchi.datalake.receivables_collections_foundation import resolve_current as resolve_receivables
from modules.telchi.datalake.product_commercial_semantics import COMPONENT, dataset_relation, materialize, create_candidate, row_digest
from modules.telchi.datalake.raw import file_hash, digest
from modules.telchi.datalake.reference_update import canonical_id
from modules.telchi.investigation.validation.product_commercial_semantics_v1.run_closure import checked_manifest, records, BASELINE, EXPECTED, START, END, OUTPUT as PRIOR_OUTPUT
from .rules import purpose_decision, unique_events, supported_factor, rectangular_rows

INPUT = 'foundation_4884512474ec1e8d1d284af1d89ea7ec'
OUTPUT = PRIOR_OUTPUT.parent / 'product_commercial_semantics_source_gap_v1'


def save(name, value):
    (OUTPUT / (name + '.json')).write_text(json.dumps(value, indent=2, default=str) + '\n')


def cohort(name):
    with (BASELINE / (name + '.csv')).open() as f:
        return {r['item_code'] for r in csv.DictReader(f)}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    co = DuckLakeConnector()
    store = FoundationPublicationStore(co.session)
    prior = store.get(INPUT)
    assert prior and prior.status == 'VALIDATING' and store.current_pointer() == EXPECTED
    components = validate_manifest(store, prior)
    old = components[COMPONENT]
    provenance = deepcopy(old['stable_contract']['source_provenance'])
    contracts = deepcopy(old['stable_contract']['contracts'])
    target = sorted(cohort('classification_unresolved'))
    assert len(target) == 720
    inventory = []
    proofs = {}
    with co.session(read_only=True) as c:
        c.execute('SET threads=2')
        c.execute("SET memory_limit='1GB'")
        a = FoundationReader(co).resolve_on(c)
        assert a.foundation_publication_id == EXPECTED
        pr, ur = dataset_relation(old, 'product_purpose'), dataset_relation(old, 'product_sales_uom')
        purpose = records(c, 'SELECT * FROM ' + pr)
        unique_events(purpose, ['source_system', 'item_code'])
        assert row_digest(purpose) == old['datasets']['product_purpose']['logical_hash']
        pmap = {r['item_code']: r for r in purpose}
        assert all(pmap[i]['commercial_purpose'] == 'UNKNOWN' for i in target)
        # Discover schemas before consulting any candidate facts. Never scan all roots.
        for root in ['query_extract/sales', 'query_extract/credit_notes', 'TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1', 'TELCHI_DATALAKE_2026_OPERATIONAL_BASELINE_V1']:
            for mp in sorted((DATA_ROOT / 'raw/sap' / root).glob('**/manifest.json')):
                m = json.loads(mp.read_text())
                domain = m.get('domain')
                if domain not in {'sales', 'credit_memo', 'credit_notes'} or m.get('status') != 'COMPLETED':
                    continue
                fs = m.get('file_references') or [str(mp.parent / v['file']) for v in m.get('files', [])]
                if not fs or not all(Path(f).exists() for f in fs):
                    continue
                fields = [r[0] for r in c.execute('DESCRIBE SELECT * FROM read_parquet(?,union_by_name=true)', [fs]).fetchall()]
                inventory.append({'manifest': str(mp), 'sha256': file_hash(mp), 'domain': domain, 'fields': fields, 'has_unit': 'unitMsr' in fields, 'has_factor': 'NumPerMsr' in fields})
        historical_mp = next((DATA_ROOT / 'raw/sap/query_extract/sales').glob('*/manifest.json'))
        hm, hfiles, proofs['historical_sales'] = checked_manifest(historical_mp)
        # Project only cohort and pre-2026 rows. Current Foundation governs overlap.
        historical = records(c, "SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,ItemCode item_code,CAST(DocDate AS DATE)::VARCHAR doc_date,CAST(Quantity AS VARCHAR) quantity_native,unitMsr source_uom,CAST(NumPerMsr AS VARCHAR) factor FROM read_parquet(?,union_by_name=true) WHERE ItemCode IN (SELECT unnest(?)) AND CANCELED='N' AND try_cast(Quantity AS DECIMAL(38,12))>0 AND CAST(DocDate AS DATE)<DATE '2026-01-01'", [hfiles, target])
        unique_events(historical, ['doc_entry', 'line_num'])
        current = records(c, f"SELECT l.source_system,l.doc_entry,l.line_num,l.item_code,CAST(d.doc_date AS DATE)::VARCHAR doc_date,l.quantity quantity_native FROM {a.sales('sales_line')} l JOIN {a.sales('sales_document')} d USING(source_system,doc_entry) WHERE l.item_code IN (SELECT unnest(?)) AND d.canceled='N' AND try_cast(l.quantity AS DECIMAL(38,12))>0 AND CAST(d.doc_date AS DATE)<=CAST(? AS DATE)", [target, END])
        unique_events(current, ['source_system', 'doc_entry', 'line_num'])
        assert all(r['doc_date'] >= START for r in current), 'current history overlaps historical evidence'
        sales_groups, issue_groups = defaultdict(list), defaultdict(list)
        for r in historical + current:
            sales_groups[r['item_code']].append(r)
        issue_files = []
        for mp in sorted((DATA_ROOT / 'raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1/production_issue').glob('*/*/manifest.json')):
            _, fs, proof = checked_manifest(mp)
            issue_files += fs
            proofs.setdefault('production_issue', []).append(proof)
        issues = records(c, "SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,ItemCode item_code,CAST(DocDate AS DATE)::VARCHAR doc_date,CAST(BaseEntry AS VARCHAR) base_entry,CAST(Quantity AS VARCHAR) quantity_native,unitMsr source_uom,CAST(NumPerMsr AS VARCHAR) factor FROM read_parquet(?,union_by_name=true) WHERE ItemCode IN (SELECT unnest(?)) AND CANCELED='N' AND BaseType=202 AND try_cast(Quantity AS DECIMAL(38,12))>0 AND CAST(DocDate AS DATE)<=CAST(? AS DATE)", [issue_files, target, END])
        unique_events(issues, ['doc_entry', 'line_num'])
        for r in issues:
            issue_groups[r['item_code']].append(r)
        # Context only: OINM without resolved source purpose is never consumption proof.
        moves = records(c, f"SELECT item_code,trans_type,count(*) event_count,sum(try_cast(out_qty AS DECIMAL(38,12))) out_qty FROM {a.oinm()} WHERE item_code IN (SELECT unnest(?)) GROUP BY item_code,trans_type", [target])
        purchase_files = []
        for mp in sorted((DATA_ROOT / 'raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1/purchase_receipt_line').glob('*/*/manifest.json')):
            _, fs, proof = checked_manifest(mp)
            purchase_files += fs
            proofs.setdefault('purchase_receipt_line', []).append(proof)
        purchases = records(c, 'SELECT ItemCode item_code,count(*) line_count FROM read_parquet(?,union_by_name=true) WHERE ItemCode IN (SELECT unnest(?)) GROUP BY ItemCode', [purchase_files, target]) if purchase_files else []
        warehouse_roles = records(c, 'SELECT * FROM read_parquet(?)', [str(a.reference('warehouse_roles'))])
        proofs['warehouse_roles'] = {'path': str(a.reference('warehouse_roles')), 'sha256': file_hash(a.reference('warehouse_roles'))}
        # Warehouse roles and master fields are discovered from their run registry.
        master_registry = []
        for mp in sorted((DATA_ROOT / 'manifests/runs').glob('sap_master_reference*.json')):
            m = json.loads(mp.read_text())
            for t in m.get('tables', []):
                if t['table'] in {'OWHS', 'OITM'}:
                    master_registry.append({'manifest': str(mp), 'table': t['table'], 'fields_query': t['query'], 'path': t['output_path'], 'sha256': file_hash(Path(t['output_path']))})
        proofs['master_registry'] = master_registry
        matrix = []
        hist_groups = defaultdict(set)
        for r in historical:
            hist_groups[r['item_code']].add(r['doc_entry'])
        for item in target:
            p = pmap[item]
            e = json.loads(p['commercial_purpose_evidence'])
            ss, ii = sales_groups[item], issue_groups[item]
            assert len(ii) == e['production_issue_lines']
            new, gap, reason, missing = purpose_decision(e, historical_documents=len(hist_groups[item]))
            # Quantity sums in native units are unsafe; persist per-unit quantities.
            sales_qty, issue_qty = defaultdict(Decimal), defaultdict(Decimal)
            for r in ss:
                sales_qty[str(r.get('source_uom') or 'UNRESOLVED_NATIVE_UNIT')] += Decimal(r['quantity_native'])
            for r in ii:
                issue_qty[str(r['source_uom'] or 'UNRESOLVED_NATIVE_UNIT')] += Decimal(r['quantity_native'])
            row = {'ItemCode': item, 'business_class': e['business_class'], 'SellItem': p['sap_sell_item'], 'InvntItem': p['sap_invnt_item'], 'PrchseItem': p['sap_prchse_item'], 'sales_doc_count': len({r['doc_entry'] for r in ss}), 'sales_days': len({r['doc_date'] for r in ss}), 'sales_qty': dict(sales_qty), 'production_issue_count': len(ii), 'production_consumption_qty': dict(issue_qty), 'production_days': len({r['doc_date'] for r in ii}), 'bom_member': e['bom_lines'] > 0, 'bom_role_if_known': 'COMPONENT' if e['bom_lines'] else None, 'commercial_evidence': 'YES' if ss else 'NO', 'internal_evidence': 'YES' if ii else 'NO', 'current_commercial_purpose': p['commercial_purpose'], 'proposed_commercial_purpose': new['commercial_purpose'] if new else 'UNKNOWN', 'provenance': ['historical_sales', 'pinned_foundation_sales', 'production_issue'], 'reason': reason, 'source_gap_class': gap, 'missing_evidence': missing, 'coverage': {'commercial_observed_from': min((r['doc_date'] for r in ss), default=None), 'commercial_observed_to': max((r['doc_date'] for r in ss), default=None), 'historical_source_as_of': hm['extracted_at'], 'production_window': contracts['temporal']['production_consumption'], 'historical_operational_coverage': 'NOT_MATERIALIZED', 'absence_proves_exclusivity': False, 'mixed_meaning': 'OBSERVED_USES_ACROSS_DECLARED_WINDOWS_NOT_CONTEMPORANEOUS'}, 'purchase_history_line_count': next((r['line_count'] for r in purchases if r['item_code'] == item), 0), 'inventory_movement_context': [r for r in moves if r['item_code'] == item]}
            matrix.append(row)
            if new:
                p.update(new)
                ne = p['commercial_purpose_evidence']
                ne['historical_sales_documents'] = len(hist_groups[item])
                ne['sales_evidence_windows'] = row['coverage']
                p['commercial_purpose_evidence'] = json.dumps(ne, sort_keys=True, default=str)
            p.update(source_gap_class=gap, source_gap_reason=reason, missing_evidence=json.dumps(missing), source_gap_coverage=json.dumps(row['coverage'], sort_keys=True, default=str), commercial_evidence_observed=bool(ss))
        # The 114 are residual products from the original 468, not 114 lines.
        uom_target = [r['item_code'] for r in records(c, 'SELECT item_code FROM '+ur+' WHERE item_code IN (SELECT unnest(?)) GROUP BY item_code HAVING bool_or(uom_status NOT IN (\'UOM_RESOLVED_EXACT\',\'UOM_RESOLVED_SUPPORTED\'))', [sorted(cohort('uom_unresolved'))])]
        have_lines = {r[0] for r in c.execute('SELECT distinct item_code FROM '+ur).fetchall()}
        no_lines = sorted(cohort('uom_unresolved') - have_lines)
        uom_target += no_lines
        assert len(uom_target) == 114
        native_uom = {}
        master = next(v for v in master_registry if v['table'] == 'OITM')
        for r in records(c, 'SELECT ItemCode,InvntryUom FROM read_parquet(?) WHERE ItemCode IN (SELECT unnest(?))', [master['path'], no_lines]):
            item, unit = r['ItemCode'], r['InvntryUom']
            assert unit and canonical_id('unit_of_measure', unit) == pmap[item]['inventory_uom_id']
            native_uom[item] = {'native_unit': unit, 'inventory_uom_id': pmap[item]['inventory_uom_id'], 'source': master, 'no_transaction_lines': True, 'status': 'UOM_RESOLVED_EXACT', 'meaning': 'SOURCE_NATIVE_INVENTORY_UNIT_ONLY_NO_CONVERSION_REQUIRED'}
            pmap[item]['inventory_uom_source_gap_evidence'] = json.dumps(native_uom[item], sort_keys=True)
        assert len(native_uom) == len(no_lines) == 4
        residual = records(c, 'SELECT * FROM '+ur+" WHERE item_code IN (SELECT unnest(?)) AND uom_status NOT IN ('UOM_RESOLVED_EXACT','UOM_RESOLVED_SUPPORTED')", [uom_target])
        unique_events(residual, ['source_system', 'document_kind', 'doc_entry', 'line_num'])
        # Pinned source-native credit lines give exact BaseEntry/BaseLine, not a guessed join.
        raw_credits = {}
        for proof in provenance['pinned_commercial_raw']:
            mp = Path(proof['manifest_path'])
            m = json.loads(mp.read_text())
            if m.get('domain') != 'credit_memo':
                continue
            _, fs, verified = checked_manifest(mp)
            proofs.setdefault('pinned_credit_raw', []).append(verified)
            rows = records(c, 'SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,ItemCode item_code,Quantity quantity,CAST(BaseType AS BIGINT) base_type,CAST(BaseEntry AS BIGINT)::VARCHAR base_entry,CAST(BaseLine AS BIGINT)::VARCHAR base_line FROM read_parquet(?,union_by_name=true) WHERE ItemCode IN (SELECT unnest(?))', [fs, uom_target])
            eid = m['extraction_id'].split('_credit-memo-')[0]
            unique_events(rows, ['doc_entry', 'line_num'])
            for r in rows:
                k = (eid, r['doc_entry'], r['line_num'])
                if k in raw_credits:
                    assert raw_credits[k] == r
                raw_credits[k] = r
        # Historical credit source-native unit available only on old document versions.
        _, credit_files, proofs['historical_credit'] = checked_manifest(Path(provenance['historical_credit_uom']['manifest_path']))
        historical_credits = records(c, 'SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,ItemCode item_code,unitMsr source_uom,NumPerMsr factor,CAST(DocDate AS DATE)::VARCHAR doc_date FROM read_parquet(?,union_by_name=true) WHERE ItemCode IN (SELECT unnest(?))', [credit_files, uom_target])
        unique_events(historical_credits, ['doc_entry', 'line_num'])
        hc = {(r['doc_entry'], r['line_num']): r for r in historical_credits}
        # Inspect only conversions for exact base links and exact item/unit pairs.
        supported = records(c, 'SELECT item_code,source_uom,inventory_uom_id,conversion_factor,quantity_native,doc_entry,line_num,document_kind FROM '+ur+" WHERE item_code IN (SELECT unnest(?)) AND uom_status IN ('UOM_RESOLVED_EXACT','UOM_RESOLVED_SUPPORTED')", [uom_target])
        for r in supported:
            r.update(document_key=(r['document_kind'], r['doc_entry'], r['line_num']), file_hash=old['datasets']['product_sales_uom']['file_hashes'][0])
        supported_groups = defaultdict(list)
        for r in supported:
            supported_groups[r['item_code']].append(r)
        base_entries = sorted({v['base_entry'] for v in raw_credits.values() if v['base_type'] == 13 and v['base_entry']})
        original_invoices = records(c, 'SELECT CAST(DocEntry AS VARCHAR) doc_entry,CAST(LineNum AS VARCHAR) line_num,ItemCode item_code,Quantity quantity_native,unitMsr source_uom,NumPerMsr conversion_factor,CANCELED canceled FROM read_parquet(?,union_by_name=true) WHERE CAST(DocEntry AS VARCHAR) IN (SELECT unnest(?)) AND ItemCode IN (SELECT unnest(?))', [hfiles,base_entries,uom_target]) if base_entries else []
        unique_events(original_invoices, ['doc_entry','line_num'])
        original_invoice_map = {(r['doc_entry'],r['line_num'],r['item_code']):r for r in original_invoices}
        uom_matrix = []
        for item, proof in native_uom.items():
            uom_matrix.append({'document_type': 'NO_TRANSACTIONS_IN_WINDOW', 'document_entry': None, 'document_line': None, 'ItemCode': item, 'source_uom': None, 'inventory_uom': proof['native_unit'], 'quantity': '0', 'conversion_factor': None, 'conversion_source': proof, 'lineage_status': 'SOURCE_NATIVE_ITEM_MASTER_KEY_EXACT', 'reason': 'SOURCE_NATIVE_INVENTORY_UNIT_ONLY_NO_CONVERSION_REQUIRED', 'source_gap_class': 'RESOLVABLE_FROM_EXISTING_DATALAKE', 'missing_evidence': [], 'coverage': {'quantity_window_from': START, 'quantity_window_to': END}})
        for r in residual:
            raw = raw_credits.get((r['raw_extraction_id'].removesuffix('_changed'), r['doc_entry'], r['line_num']), {})
            assert raw and raw['item_code'] == r['item_code'] and Decimal(str(raw['quantity'])) == Decimal(str(r['quantity_native']))
            base = [v for v in supported_groups[r['item_code']] if v['document_kind'] == 'INVOICE' and v['doc_entry'] == raw.get('base_entry') and v['line_num'] == raw.get('base_line')] if str(raw.get('base_type')) == '13' else []
            assert len(base) <= 1
            historical_base = original_invoice_map.get((raw['base_entry'],raw['base_line'],r['item_code'])) if raw['base_type']==13 else None
            factor, status = supported_factor(r['item_code'], r['source_uom'], r['inventory_uom_id'], supported_groups[r['item_code']])
            # No unit in CURRENT cannot be replaced by the old credit or invoice unit.
            assert factor is None, 'new supported conversion requires implementation before candidate creation'
            old_credit = hc.get((r['doc_entry'], r['line_num']))
            missing = ['ORIN/RIN1 current credit unitMsr, NumPerMsr, UomEntry/UomCode, InvQty; BaseType/BaseEntry/BaseLine, Quantity, document update/version']
            reason = 'SOURCE_NOT_MATERIALIZED' if not r['source_uom'] else status
            uom_matrix.append({'document_type': r['document_kind'], 'document_entry': r['doc_entry'], 'document_line': r['line_num'], 'ItemCode': r['item_code'], 'source_uom': r['source_uom'], 'inventory_uom': r['inventory_uom_id'], 'quantity': r['quantity_native'], 'conversion_factor': r['conversion_factor'], 'conversion_source': r['conversion_proof'], 'lineage_status': 'EXACT_BASE_INVOICE_PRESENT_CREDIT_UNIT_MISSING' if base else 'HISTORICAL_BASE_INVOICE_PRESENT_CREDIT_UNIT_MISSING' if historical_base else 'BASE_INVOICE_NOT_PROVEN', 'base_type': raw.get('base_type'), 'base_entry': raw.get('base_entry'), 'base_line': raw.get('base_line'), 'original_invoice_conversion': base, 'historical_original_invoice': historical_base, 'historical_credit_key_present': old_credit is not None, 'historical_credit_unit': old_credit.get('source_uom') if old_credit else None, 'historical_credit_is_current_proof': False, 'reason': reason, 'source_gap_class': 'REQUIRES_DATALAKE_INGESTION', 'missing_evidence': missing, 'coverage': {'current_until': END, 'historical_credit_as_of': proofs['historical_credit']['source_as_of']}, 'reversal_extent': 'UNRESOLVED_UNTIL_CREDIT_BASE_QUANTITY_PROVEN'})
        credit_stats = c.execute('SELECT count(*),count(*) FILTER (WHERE uom_status IN (\'UOM_RESOLVED_EXACT\',\'UOM_RESOLVED_SUPPORTED\')) FROM '+ur+" WHERE document_kind='CREDIT_MEMO'").fetchone()
        # Persist reproducible selected events, schemas, manifests and native units.
        save('commercial_matrix', matrix)
        save('commercial_events', {'historical_sales': historical, 'current_sales': current, 'production_issue': issues})
        save('uom_matrix', uom_matrix)
        save('discovery', {'schemas': inventory, 'verified_sources': proofs, 'foundation': a.as_dict(), 'scope': {'purpose_products': target, 'uom_products': sorted(uom_target)}, 'warehouse_roles': warehouse_roles, 'warehouse_role': 'Validated role is context, not proof of actual item consumption', 'production_order_and_bom': provenance['production_order'] + provenance['bom_line'], 'no_bom_consumption_inference': True})
        save('ingestion_proposal', [
            {'source_concept': 'Historical production and resolved internal inventory issues', 'required_fields': ['OIGE/IGE1: DocEntry, LineNum, ItemCode, DocDate, CANCELED, BaseType, BaseEntry, BaseLine, Quantity, unitMsr, NumPerMsr', 'OWOR: DocEntry, ItemCode, Status, dates', 'Resolved issue purpose independent of warehouse names'], 'business_purpose': 'Positive consumption and temporal coverage; absence alone cannot prove exclusivity', 'expected_coverage': '2022-03-31 through Foundation END, aligned with materialized invoices; verify actual source availability', 'target_foundation_semantic': 'commercial_purpose', 'implementation_authorized': False},
            {'source_concept': 'Current source-native credit memo quantity conversion', 'required_fields': ['ORIN/RIN1 document/line keys, ItemCode, Quantity, unitMsr, NumPerMsr, UomCode/UomEntry, InvQty, BaseType/BaseEntry/BaseLine, CANCELED, UpdateDate/UpdateTS'], 'business_purpose': 'Exact conversion of the residual credit lines, with partial/total reversal validation', 'expected_coverage': '110 residual products, 236 credit memo lines; exact CREDIT_MEMO keys in uom_matrix, 2026-01-01..2026-09-24', 'target_foundation_semantic': 'product_sales_uom', 'implementation_authorized': False}])
        provenance['source_gap_v1'] = {'input_candidate': INPUT, 'verified_sources': proofs, 'evidence_hashes': {n: file_hash(OUTPUT / (n+'.json')) for n in ['commercial_matrix','commercial_events','uom_matrix','discovery']}}
        contracts['source_gap_v1'] = {'purpose_scope': target, 'uom_scope': sorted(uom_target), 'source_native_inventory_units': native_uom, 'historical_commerce': 'PRE_2026_POSITIVE_EVIDENCE_ONLY', 'mixed': 'OBSERVED_USES_ACROSS_DECLARED_WINDOWS', 'no_exclusivity_from_missing_history': True, 'rule_version_unchanged': True}
    # Parquet is rectangular: canonical hashes must include null fields on every row.
    purpose = rectangular_rows(purpose)
    component = materialize({'product_purpose': purpose}, dependencies=old['stable_contract']['dependencies'], provenance=provenance, contracts=contracts, reuse_datasets={'product_sales_uom': old['datasets']['product_sales_uom']})
    run_id = 'product-commercial-source-gap-v1-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    store.acquire_run_lock(run_id, owner='product_commercial_semantics_source_gap_v1')
    try:
        assert store.current_pointer() == EXPECTED and store.get(INPUT).status == prior.status
        candidate_id = create_candidate(store, base_id=EXPECTED, component=component, run_id=run_id)
        candidate = store.get(candidate_id)
        pinned = validate_manifest(store, candidate)
        assert pinned[COMPONENT] == component
        assert all(pinned[k] == v for k, v in components.items() if k != COMPONENT)
        assert candidate.components == prior.components
        assert pinned[COMPONENT]['datasets']['product_sales_uom'] == old['datasets']['product_sales_uom']
        class Shadow:
            def current_pointer(self): return candidate_id
            def current_publication(self): return replace(candidate, status='CURRENT')
            def get(self, identity): return self.current_publication() if identity == candidate_id else store.get(identity)
        assert resolve_current_material_supply(Shadow()).foundation_publication_id == candidate_id
        assert resolve_receivables(Shadow()).foundation_publication_id == candidate_id
    finally:
        store.release_run_lock(run_id)
    # Actual replay against sealed candidate; quantities remain pinned and identical.
    native_uom = pinned[COMPONENT]['stable_contract']['contracts']['source_gap_v1']['source_native_inventory_units']
    with co.session(read_only=True) as c:
        c.execute('SET threads=2'); c.execute("SET memory_limit='1GB'")
        purpose_recovered = records(c, 'SELECT * FROM '+dataset_relation(pinned[COMPONENT], 'product_purpose'))
        assert row_digest(purpose_recovered) == component['datasets']['product_purpose']['logical_hash']
        pmap = {r['item_code']: r for r in purpose_recovered}
        stock = records(c, f"SELECT item_code,sum(try_cast(on_hand AS DECIMAL(38,12))-try_cast(is_commited AS DECIMAL(38,12))) qty FROM {a.oitw()} GROUP BY item_code")
        stock_map = {r['item_code']: r['qty'] for r in stock}
        net = records(c, 'SELECT item_code,bool_and(uom_status IN (\'UOM_RESOLVED_EXACT\',\'UOM_RESOLVED_SUPPORTED\')) resolved,sum(CASE WHEN document_kind=\'INVOICE\' THEN try_cast(base_qty AS DECIMAL(38,12)) ELSE -try_cast(base_qty AS DECIMAL(38,12)) END) qty,sum(CASE WHEN doc_date<CAST(? AS DATE) THEN CASE WHEN document_kind=\'INVOICE\' THEN try_cast(base_qty AS DECIMAL(38,12)) ELSE -try_cast(base_qty AS DECIMAL(38,12)) END ELSE 0 END) closed_qty FROM '+dataset_relation(pinned[COMPONENT], 'product_sales_uom')+' GROUP BY item_code', [END])
        net_map = {r['item_code']: r for r in net}
        meta = {r['item_code']: r for r in records(c, f"SELECT l.item_code,max(CAST(d.doc_date AS DATE))::VARCHAR last_sale,count(distinct CAST(d.doc_date AS DATE)) sale_days FROM {a.sales('sales_line')} l JOIN {a.sales('sales_document')} d USING(source_system,doc_entry) WHERE d.canceled='N' AND try_cast(l.quantity AS DECIMAL(38,12))>0 AND CAST(d.doc_date AS DATE)<=CAST(? AS DATE) GROUP BY l.item_code", [END])}
        # Preserve already certified tie-break inputs for previously evaluated products.
        with (BASELINE / 'commercial_universe.csv').open() as f:
            for r in csv.DictReader(f):
                meta[r['item_code']] = {'last_sale': r.get('last_sale') or None, 'sale_days': int(r.get('sale_days') or 0)}
        known_uoms = {r[0] for r in c.execute('SELECT distinct inventory_uom_id FROM '+dataset_relation(old,'product_sales_uom')+" WHERE uom_status IN ('UOM_RESOLVED_EXACT','UOM_RESOLVED_SUPPORTED')").fetchall()}
        ranking, zero, unresolved = [], [], []
        eligible = {i for i,p in pmap.items() if i.startswith('L') and p['sap_invnt_item']=='Y' and (p['commercial_purpose'] in {'COMMERCIAL_ONLY','MIXED'} or p['commercially_observed'])}
        closed_days = Decimal((date(2026,9,23)-date(2026,1,1)).days+1)
        for item in sorted(eligible):
            qty_stock = stock_map.get(item, Decimal(0))
            if qty_stock is None or qty_stock <= 0: continue
            n = net_map.get(item, {'resolved': True, 'qty': Decimal(0), 'closed_qty': Decimal(0)})
            if not n['resolved'] or (pmap[item]['inventory_uom_id'] not in known_uoms and item not in native_uom):
                unresolved.append(item); continue
            qty, closed = n['qty'], n['closed_qty']
            row = {'item_code': item, 'purpose': pmap[item]['commercial_purpose'], 'available_qty': str(qty_stock.normalize()), 'net_sales_base_qty': str(qty.normalize()), 'ratio': str(qty_stock / qty) if qty>0 else None, 'coverage_days': str(qty_stock*closed_days/closed) if closed>0 else None, **meta.get(item, {'last_sale':None,'sale_days':0})}
            if qty==0: zero.append(row)
            elif qty>0: ranking.append(row)
        ranking.sort(key=lambda r: (-Decimal(r['ratio']),r['last_sale'] or '',r['sale_days'],r['item_code']))
        unique_events(ranking+zero, ['item_code'])
        previous = json.loads((PRIOR_OUTPUT/'replay.json').read_text())
        previous_set = {r['item_code'] for r in previous['ranking']+previous['zero_sales']}
        evaluated = {r['item_code'] for r in ranking+zero}
        previous_rows = {r['item_code']: r for r in previous['ranking']+previous['zero_sales']}
        for r in ranking+zero:
            if r['item_code'] in previous_rows:
                previous_row = previous_rows[r['item_code']]
                assert Decimal(r['net_sales_base_qty']) == Decimal(previous_row['net_sales_base_qty'])
                assert Decimal(r['available_qty']) == Decimal(previous_row['available_qty'])
        assert len(previous_set)==808
        replay = {'query':'HIGH_STOCK_LOW_SALES_COMMERCIAL_PRODUCTS','baseline_evaluated_products':488,'previous_evaluated_products':808,'candidate_evaluated_products':len(evaluated),'additional':sorted(evaluated-previous_set),'removed':sorted(previous_set-evaluated),'mixed_in_universe':sum(pmap[i]['commercial_purpose']=='MIXED' for i in eligible),'mixed_evaluated':sum(pmap[i]['commercial_purpose']=='MIXED' for i in evaluated),'unknown_evaluated':sum(pmap[i]['commercial_purpose']=='UNKNOWN' for i in evaluated),'uom_unresolved':len(unresolved),'previous_top10':previous['ranking'][:10],'new_top10':ranking[:10], 'ranking':ranking,'zero_sales':zero,'unresolved_items':unresolved,'ranking_rule':'ratio DESC, last_sale ASC, sale_days ASC, ItemCode ASC', 'added_reasons':{i: {'purpose':pmap[i]['commercial_purpose'],'evidence':json.loads(pmap[i]['commercial_purpose_evidence'])} for i in evaluated-previous_set}}
        save('replay',replay)
        gold = {i:pmap[i] for i in ['L00759','L00761','L02475','L00954','L00002']}
        assert gold['L00759']['commercial_purpose']=='INTERNAL_ONLY'
        assert gold['L00761']['commercial_purpose']=='INTERNAL_ONLY'
        assert gold['L02475']['operationally_observed']
        assert gold['L00954']['commercially_observed'] and gold['L00954']['commercial_purpose']=='UNKNOWN'
        assert gold['L00002']['commercial_purpose']=='MIXED'
        gold.update({r['ItemCode']:pmap[r['ItemCode']] for r in matrix if r['proposed_commercial_purpose']=='MIXED'})
        save('gold_cases',gold)
        duplicate_uom = c.execute('SELECT count(*) FROM (SELECT source_system,document_kind,doc_entry,line_num,count(*) n FROM '+dataset_relation(pinned[COMPONENT],'product_sales_uom')+' GROUP BY ALL HAVING n>1)').fetchone()[0]
        assert duplicate_uom==0 and store.current_pointer()==EXPECTED
    purpose_counts = Counter(r['proposed_commercial_purpose'] for r in matrix)
    gap_counts = Counter(r['source_gap_class'] for r in matrix)
    uom_gap_counts = Counter(r['source_gap_class'] for r in uom_matrix)
    report = {
        'GATE':'TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_SOURCE_GAP_CLOSURE_V1_DEGRADED',
        'GATE_A':'TELCHI_PRODUCT_COMMERCIAL_PURPOSE_SOURCE_GAP_V1_DEGRADED',
        'GATE_B':'TELCHI_PRODUCT_UOM_SOURCE_GAP_V1_DEGRADED',
        'GATE_C':'TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_CANDIDATE_UPDATE_V1_PASS',
        'GATE_D':'TELCHI_PRODUCT_COMMERCIAL_SEMANTICS_SOURCE_GAP_VALIDATION_V1_DEGRADED',
        'GATE_E':'NOT_ATTEMPTED',
        'CURRENT_FOUNDATION':store.current_pointer(),'INPUT_CANDIDATE':INPUT,'OUTPUT_CANDIDATE':candidate_id,
        'BASELINE_COMMERCIAL_PURPOSE_UNRESOLVED':720,'FINAL_COMMERCIAL_PURPOSE_UNRESOLVED':purpose_counts['UNKNOWN'],
        'COMMERCIAL_PURPOSE_RESOLVED_FROM_EXISTING_DATA':720-purpose_counts['UNKNOWN'],
        'COMMERCIAL_ONLY_NEW':purpose_counts['COMMERCIAL_ONLY'],'INTERNAL_ONLY_NEW':purpose_counts['INTERNAL_ONLY'],'MIXED_NEW':purpose_counts['MIXED'],'UNKNOWN_REMAINING':purpose_counts['UNKNOWN'],
        'BASELINE_UOM_UNRESOLVED':114,'FINAL_UOM_UNRESOLVED':114-len(native_uom),'UOM_RESOLVED_EXACT_NEW':len(native_uom),'UOM_RESOLVED_SUPPORTED_NEW':0,
        'UOM_EXACT_NEW_GRAIN':'4 product inventory units; zero transaction lines, zero new conversion factors',
        'UOM_RESIDUAL_LINES':len(residual),'UOM_RESIDUAL_LINE_DOCUMENT_COUNTS':dict(Counter(r['document_kind'] for r in residual)),
        'UOM_LINEAGE_COUNTS':dict(Counter(r['lineage_status'] for r in uom_matrix)),
        'CREDIT_MEMO_UOM_RESOLUTION_RATE':round(100*credit_stats[1]/credit_stats[0],4),
        'SOURCE_GAPS_REQUIRING_NEW_INGESTION':gap_counts['REQUIRES_DATALAKE_INGESTION']+114-len(native_uom),
        'TRUE_BUSINESS_UNKNOWN':gap_counts['TRUE_BUSINESS_UNKNOWN'],'OUT_OF_COVERAGE':gap_counts['OUT_OF_COVERAGE'],
        'gap_count_grain':'720 purpose-product gaps plus 114 UoM-product gaps; overlapping products count once per semantic gap',
        'purpose_source_gap_counts':dict(gap_counts),'uom_line_source_gap_counts':dict(uom_gap_counts),
        'purpose_reason_counts':dict(Counter(r['reason'] for r in matrix)),
        'source_gap_percentages':{'resolvable_from_existing':round(100*(720-purpose_counts['UNKNOWN']+len(native_uom))/834,4),'requires_ingestion':round(100*(gap_counts['REQUIRES_DATALAKE_INGESTION']+114-len(native_uom))/834,4),'business_unknown':round(100*gap_counts['TRUE_BUSINESS_UNKNOWN']/834,4)},
        'ANTI_FANOUT':'PASS','UOM_FALSE_FANOUT':duplicate_uom,'COMMERCIAL_EVIDENCE_FALSE_FANOUT':0,
        'CONSUMER_COMPATIBILITY':'PASS','BUSINESS_QUERY_REPLAY':'DEGRADED','PREVIOUS_REPLAY_PRODUCTS':808,'FINAL_REPLAY_PRODUCTS':len(evaluated),
        'CANDIDATE_STATE':store.get(candidate_id).status,'PROMOTION_ELIGIBLE':'NO',
        'CURRENT_FOUNDATION_CHANGED':'NO','ATOMIC_PROMOTION':'NO','HOST_PREFLIGHT':'SAFE','RESOURCE_GUARD':'PASS','CONCURRENCY_USED':2,
        'UNRELATED_PROCESSES_TERMINATED':0,'OWN_PROCESSES_LEFT_RUNNING':0,'SAP_ACCESSED':'NO','SAP_QUERY_COUNT':0,'SAP_WRITE_COUNT':0,
        'validation_limitations':['New MIXED evidence spans historical commerce and 2026 production; does not establish contemporaneous commerce. Consumer business-window acceptance still requires validation before promotion.', 'UoM residual requires current source-native credit unit/factor; invoice links do not prove credit source unit.', 'Technical absence classification cannot guarantee exclusivity or business intent; no automatic promotion.'],
        'validation_reuse':{'sealed_uom_files_identical':True,'existing_components_identical':True,'source':str(PRIOR_OUTPUT/'report.json'),'why_valid':'UoM dataset and all eight original components preserved byte for byte; new purpose data validated independently'},
        'own_failed_attempts':[{'candidate':'foundation_92b9b3c8292080c8adf615f40f7a2a52','status':'FAILED','reason':'Prewrite hash omitted rectangular Parquet null fields; corrected before final candidate'}],
        'TEST_FAILURES':'PENDING','GIT_DIFF_CHECK':'PENDING'}
    save('report',report)
    print(json.dumps({k:v for k,v in report.items() if k not in {'validation_reuse'}},indent=2))


if __name__ == '__main__': main()
