"""Independent evidence, not a business capability or certified geographic mapping."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from modules.telchi.datalake.foundation_reader import FoundationReader

PRIMARY_CODES = ('L03332', 'L03432', 'L03612', 'M07010')
# Explicit description candidates only, no automatic mapping to original intent.
RELATED_CODES = ('L03618', 'L03651', 'L03652', 'L03653', 'L03659', 'L03756',
                 'M07871', 'M08237', 'M08239', 'M08657')
LEGACY = Path('/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing overwrite')
    out = dict(timestamp=datetime.now(timezone.utc).isoformat(), sap_accessed=False,
               read_only=True, queries=[], source_fingerprints=[], threads=2,
               limits=['No geographic assignment from warehouse', 'No physical unit or conversion factor on lines',
                       'LineTotal is raw documentary observation, not approved net invoicing',
                       'L&S account candidate is not proof of exclusive Cochabamba distribution',
                       'No sell-out, inventory or returns ledger from L&S was supplied'])
    def save():
        args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str) + '\n')
    r = FoundationReader()
    with r.connector.session(read_only=True) as c:
        c.execute('SET threads=2')
        c.execute("SET memory_limit='768MB'")
        c.execute("SET max_temp_directory_size='0B'")
        a = r.resolve_on(c)
        out['foundation'] = a.as_dict()
        def q(name, sql):
            item = dict(name=name, sql=sql)
            out['queries'].append(item)
            try:
                cur = c.execute(sql)
                item['rows'] = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
            except Exception as exc:
                item['error'] = str(exc)
            save()
            return item.get('rows', [])
        def ref(name):
            return "read_parquet('" + str(a.reference(name)).replace("'", "''") + "')"
        q('uom_dictionary', f"SELECT canonical_uom_code,canonical_uom_label,physical_dimension,status,mapping_source FROM {ref('units_of_measure')}")
        q('LS_alias_candidates', f"SELECT entity_type,canonical_id,alias,normalized_alias,alias_source,resolution_status FROM {ref('entity_alias')} WHERE upper(alias) LIKE '%L&S%' OR upper(alias) LIKE '%L & S%' OR alias='LYS'")
        for dataset in ('business_locations','operating_model'):
            # These dictionaries have no timestamp-with-time-zone columns.
            q(dataset + '_dictionary', f'SELECT * FROM {ref(dataset)}')
        q('warehouse_metadata', f"SELECT source_system,code,name,sap_branch_office_id,sap_warehouse_dms FROM {ref('warehouses')} WHERE source_system='SAP_HANA'")
        q('customer_branch_completeness', f"SELECT source_system,COUNT(*) row_count,COUNT(branch_id) with_branch FROM {ref('customers')} GROUP BY 1")
        for folder in ('DS','DS0'):
            for filename in ('clientSB1.parq','productSB1.parq'):
                path = LEGACY / folder / filename
                if not path.is_file():
                    continue
                out['source_fingerprints'].append(dict(path=str(path), size=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(), mtime=path.stat().st_mtime))
                schema = q(folder + '_' + filename + '_schema', f"DESCRIBE SELECT * FROM read_parquet('{path}')")
                cols = [s['column_name'] for s in schema]
                if filename == 'productSB1.parq':
                    q(folder + '_product_historical_metadata', f"SELECT ItemCode,ItemName,InvntryUom,FirmCode,Linea,Grupo,U_FormaFarmac,FFName FROM read_parquet('{path}') WHERE ItemCode IN ('L03332','L03432','L03612','M07010')")
                if filename == 'clientSB1.parq' and 'ClientCode' in cols:
                    selected = [col for col in cols if any(s in col.lower() for s in ('code','name','city','office','branch','zone','prov','depart','region','country')) and not any(s in col.lower() for s in ('phone','contact','email','address','tax','nit'))]
                    q(folder + '_LS_legacy_candidate', 'SELECT ' + ','.join('"'+col+'"' for col in selected) + f" FROM read_parquet('{path}') WHERE ClientCode='C010264'")
        allcodes = PRIMARY_CODES + RELATED_CODES
        codes = ','.join("'" + x + "'" for x in allcodes)
        for component, doc, line in [('sales','sales_document','sales_line'), ('credit_memo','credit_memo_document','credit_memo_line')]:
            d, l = a.relation(component, doc), a.relation(component, line)
            joined = f'''FROM {l} l JOIN {d} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
                WHERE l.source_system='SAP_B1_HANA' AND l.item_code IN ({codes})
                AND d.doc_date>='2026-01-01' AND d.doc_date<'2027-01-01' AND d.canceled='N' '''
            q(component + '_duplicate_documents', f"SELECT source_system,doc_entry,COUNT(*) n FROM {d} GROUP BY ALL HAVING COUNT(*)>1 LIMIT 5")
            q(component + '_duplicate_target_lines', f"SELECT source_system,doc_entry,line_num,COUNT(*) n FROM {l} WHERE item_code IN ({codes}) GROUP BY ALL HAVING COUNT(*)>1 LIMIT 5")
            q(component + '_orphan_target_lines', f"SELECT COUNT(*) orphans FROM {l} l LEFT JOIN {d} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry WHERE l.item_code IN ({codes}) AND d.doc_entry IS NULL")
            q(component + '_target_profile', f'''SELECT l.item_code,COUNT(*) line_count,COUNT(DISTINCT d.doc_entry) documents,
                COUNT(DISTINCT d.card_code) buyers,MIN(d.doc_date) first_date,MAX(d.doc_date) last_date,
                d.currency document_currency,l.currency line_currency,
                SUM(TRY_CAST(l.quantity AS DECIMAL(38,6))) documentary_quantity,
                COUNT(*) FILTER(WHERE TRY_CAST(l.quantity AS DECIMAL(38,6)) IS NULL) invalid_quantity,
                SUM(TRY_CAST(l.line_total AS DECIMAL(38,6))) raw_line_total,
                COUNT(*) FILTER(WHERE TRY_CAST(l.line_total AS DECIMAL(38,6)) IS NULL) invalid_line_total,
                COUNT(*) FILTER(WHERE TRY_CAST(l.line_total AS DECIMAL(38,6))<>0) nonzero_line_total
                {joined} GROUP BY ALL ORDER BY l.item_code''')
            q(component + '_LS_monthly', f'''SELECT SUBSTR(d.doc_date,1,7) period_month,l.item_code,
                COUNT(*) line_count,COUNT(DISTINCT d.doc_entry) documents,COUNT(DISTINCT d.card_code) buyers,
                MIN(d.doc_date) first_date,MAX(d.doc_date) last_date,d.currency document_currency,l.currency line_currency,
                SUM(TRY_CAST(l.quantity AS DECIMAL(38,6))) documentary_quantity,
                SUM(TRY_CAST(l.line_total AS DECIMAL(38,6))) raw_line_total
                {joined} AND d.card_code='C010264' GROUP BY ALL ORDER BY period_month,l.item_code''')
            q(component + '_warehouse_profile_not_destination', f'''SELECT l.item_code,l.whs_code,COUNT(*) lines,
                COUNT(DISTINCT d.card_code) buyer_codes,MAX(d.doc_date) last_date {joined}
                GROUP BY ALL ORDER BY l.item_code,l.whs_code''')
            legacy_clients = LEGACY / 'DS/clientSB1.parq'
            q(component + '_historical_city_mapping_quality', f'''SELECT COUNT(*) lines,
                COUNT(*) FILTER(WHERE m.ClientCode IS NULL) missing_historical_customer,
                COUNT(*) FILTER(WHERE upper(trim(m.ClientCity))='LA PAZ') historical_la_paz_lines
                FROM {l} l JOIN {d} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
                LEFT JOIN read_parquet('{legacy_clients}') m ON m.ClientCode=d.card_code
                WHERE l.item_code IN ({codes}) AND d.canceled='N'
                AND d.doc_date>='2026-01-01' AND d.doc_date<'2027-01-01' ''')
            q(component + '_historical_la_paz_monthly_NOT_CURRENT_DESTINATION', f'''SELECT
                SUBSTR(d.doc_date,1,7) period_month,l.item_code,COUNT(*) lines,
                COUNT(DISTINCT d.card_code) buyer_codes,MIN(d.doc_date) first_date,MAX(d.doc_date) last_date,
                d.currency document_currency,l.currency line_currency,
                SUM(TRY_CAST(l.quantity AS DECIMAL(38,6))) documentary_quantity,
                SUM(TRY_CAST(l.line_total AS DECIMAL(38,6))) raw_line_total
                FROM {l} l JOIN {d} d ON d.source_system=l.source_system AND d.doc_entry=l.doc_entry
                JOIN read_parquet('{legacy_clients}') m ON m.ClientCode=d.card_code
                WHERE l.item_code IN ({codes}) AND d.canceled='N' AND upper(trim(m.ClientCity))='LA PAZ'
                AND d.doc_date>='2026-01-01' AND d.doc_date<'2027-01-01'
                GROUP BY ALL ORDER BY period_month,l.item_code''')
            if component == 'credit_memo':
                q('LS_credit_base_link_profile', f'''SELECT l.item_code,l.base_type,COUNT(*) lines,
                    COUNT(l.base_entry) with_base_entry,COUNT(l.base_line) with_base_line {joined}
                    AND d.card_code='C010264' GROUP BY ALL''')
        legacy_clients = LEGACY / 'DS/clientSB1.parq'
        q('legacy_customer_uniqueness', f"SELECT COUNT(*) row_count,COUNT(DISTINCT ClientCode) codes FROM read_parquet('{legacy_clients}')")
        rawroot = r.connector.data_path.parents[1] / 'raw/sap/table_extract'
        for path in rawroot.rglob('OITM.parquet'):
            schema = q('raw_OITM_schema:' + str(path), f"DESCRIBE SELECT * FROM read_parquet('{path}')")
            cols = {s['column_name'] for s in schema}
            selected = [col for col in ('ItemCode','ItemName','InvntryUom','SalUnitMsr','NumInSale','FirmCode','ManBtchNum','ItmsGrpCod') if col in cols]
            q('raw_OITM_candidates:' + str(path), 'SELECT ' + ','.join('"'+col+'"' for col in selected) + f" FROM read_parquet('{path}') WHERE ItemCode IN ({codes})")
        q('LS_all_product_document_coverage', f'''SELECT MIN(doc_date) first_date,MAX(doc_date) last_date,
            COUNT(*) active_documents,COUNT(DISTINCT card_code) buyer_codes FROM {a.sales('sales_document')}
            WHERE card_code='C010264' AND canceled='N' AND doc_date>='2026-01-01' AND doc_date<'2027-01-01' ''')
        out['publication_unchanged'] = r.resolve_on(c).foundation_publication_id == a.foundation_publication_id
    save()
    for item in out['queries']:
        if 'error' in item or 'target_profile' in item['name'] or '_LS_' in item['name'] or 'LS_all' in item['name']:
            print(json.dumps(item, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
