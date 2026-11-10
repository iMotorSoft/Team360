"""Independent, non-LLM SQL controls on pinned Foundation CURRENT, read only.

Does not reuse Luna SQL, returned rows, claims, or ranking implementation.
Names delimit observed catalog concepts, not an official family taxonomy.
"""
import argparse
import json
import os
from time import perf_counter
from pathlib import Path


def run(args):
    os.environ.update(json.loads(args.control.read_text())['env'])
    from modules.telchi.datalake.ducklake import DuckLakeConnector
    from modules.telchi.datalake.foundation_reader import FoundationReader
    from modules.telchi.exploratory_sql.foundation import host_read_preflight
    report = {'host_preflight': host_read_preflight(), 'controls': [],
              'method': 'independently authored SQL; no Luna SQL or answers as inputs; pinned CURRENT read only'}
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as db:
        db.execute('SET threads=2')
        db.execute("SET memory_limit='1GB'")
        access = FoundationReader(connector).resolve_on(db)
        report['foundation'] = access.as_dict()
        def query(name, sql, parameters=()):
            started = perf_counter()
            result = db.execute(sql, parameters)
            columns = [c[0] for c in result.description]
            rows = [dict(zip(columns, r)) for r in result.fetchall()]
            report['controls'].append(dict(name=name, sql=sql, parameters=parameters,
                rows=rows, elapsed_seconds=round(perf_counter()-started, 3)))
            return rows
        docs, lines = access.sales('sales_document'), access.sales('sales_line')
        products, customers = str(access.reference('products')), str(access.reference('customers'))
        # Enforce dimension keys independently before joining, never multiply money.
        for name, relation, key, predicate in (
            ('docs', docs, 'doc_entry', "source_system='SAP_B1_HANA' AND source_table='OINV'"),
            ('products', f"read_parquet('{products}')", 'item_code', "source_system='SAP_HANA'"),
            ('customers', f"read_parquet('{customers}')", 'code', "source_system='SAP_HANA'")):
            duplicates = query(name+'_nonunique_keys', f'SELECT {key},count(*) AS n FROM {relation} WHERE {predicate} GROUP BY {key} HAVING count(*)>1')
            if duplicates:
                raise RuntimeError('independent_dimension_not_unique:'+name)
        db.execute(f'''CREATE TEMP VIEW independent_sales AS
            SELECT l.item_code,p.sap_item_name AS product_name,d.card_code,c.name AS customer_name,
                   d.doc_date,l.currency,d.canceled,
                   CAST(l.line_total AS DECIMAL(38,6)) AS amount,
                   CAST(l.quantity AS DECIMAL(38,6)) AS quantity
            FROM {lines} l
            JOIN {docs} d ON l.doc_entry=d.doc_entry AND l.source_system=d.source_system
              AND d.source_table='OINV'
            LEFT JOIN read_parquet('{products}') p ON p.item_code=l.item_code AND p.source_system='SAP_HANA'
            LEFT JOIN read_parquet('{customers}') c ON c.code=d.card_code AND c.source_system='SAP_HANA'
            WHERE l.source_system='SAP_B1_HANA' AND l.source_table='INV1' ''')
        query('coverage', "SELECT min(doc_date) AS first_date,max(doc_date) AS last_date,count(*) AS lines FROM independent_sales WHERE canceled='N' AND currency='BS'")
        # Deliberately independent selection: normalized names plus explicit mass,
        # not a copy of the model's contains predicates or selected SKU lists.
        sets = [
            ('nitric', '2026-08-01', '2026-11-01', "lower(product_name) LIKE '%acido nitrico%'"),
            ('sulfate25', '2026-09-01', '2026-10-01', "lower(product_name) LIKE '%sulfato de cobre%' AND regexp_matches(lower(product_name),'(^|[^0-9])25\\s*kg')"),
            ('soda', '2026-10-01', '2026-11-01', "lower(product_name) LIKE '%soda caustica%'"),
            ('soda1_heldout', '2026-08-01', '2026-09-01', "lower(product_name) LIKE '%soda caustica%' AND regexp_matches(lower(product_name),'(^|[^0-9])1\\s*kg')"),
        ]
        for name, start, end, concept in sets:
            where = "canceled='N' AND currency='BS' AND doc_date>=? AND doc_date<? AND ("+concept+")"
            sku = query(name+'_universe', 'SELECT item_code,product_name,count(*) AS lines FROM independent_sales WHERE '+where+' GROUP BY item_code,product_name ORDER BY item_code', (start,end))
            query(name+'_sku_count', 'SELECT count(DISTINCT item_code) AS sku_count FROM independent_sales WHERE '+where, (start,end))
            query(name+'_ranking', 'SELECT card_code,customer_name,sum(amount) AS amount,min(doc_date) AS first_date,max(doc_date) AS last_date FROM independent_sales WHERE '+where+' GROUP BY card_code,customer_name ORDER BY amount DESC,card_code', (start,end))
            if name == 'soda':
                for item in sku:
                    query('quantity_'+item['item_code'], "SELECT card_code,customer_name,sum(quantity) AS quantity FROM independent_sales WHERE canceled='N' AND currency='BS' AND doc_date>=? AND doc_date<? AND item_code=? GROUP BY card_code,customer_name ORDER BY quantity DESC,card_code", (start,end,item['item_code']))
        query('nitric_october_accounts', "SELECT card_code,customer_name,sum(amount) AS amount FROM independent_sales WHERE canceled='N' AND currency='BS' AND doc_date>='2026-10-01' AND doc_date<'2026-11-01' AND lower(product_name) LIKE '%acido nitrico%' GROUP BY card_code,customer_name ORDER BY card_code")
        # Anti-join, unlike Luna's conditional counts: both populations have the
        # same exact presentation universe and document/currency conditions.
        for name, family, mass, include, exclude in (
            ('soda25_exclusion', 'soda caustica', '25', '2026-10', '2026-09'),
            ('sulfate25_exclusion_heldout', 'sulfato de cobre', '25', '2026-09', '2026-10')):
            sql = '''WITH scope AS (SELECT * FROM independent_sales WHERE canceled='N' AND currency='BS'
                AND lower(product_name) LIKE ? AND regexp_matches(lower(product_name),?)),
                included AS (SELECT card_code,customer_name,sum(amount) AS amount FROM scope WHERE substr(doc_date,1,7)=?
                GROUP BY card_code,customer_name), excluded AS (SELECT DISTINCT card_code FROM scope WHERE substr(doc_date,1,7)=?)
                SELECT i.* FROM included i WHERE NOT EXISTS(SELECT 1 FROM excluded e WHERE e.card_code=i.card_code)
                ORDER BY amount,card_code'''
            query(name, sql, ('%'+family+'%', '(^|[^0-9])'+mass+r'\s*kg', include, exclude))
        query('sulfate_october_zero_amount_buyers', "SELECT card_code,customer_name,count(*) AS purchase_lines FROM independent_sales WHERE canceled='N' AND currency='BS' AND doc_date>='2026-10-01' AND doc_date<'2026-11-01' AND item_code='L01772' GROUP BY card_code,customer_name HAVING sum(amount)=0")
        query('customer_products_two_months', "SELECT item_code,product_name,sum(amount) AS amount FROM independent_sales WHERE canceled='N' AND currency='BS' AND card_code='C000143' AND doc_date>='2026-09-01' AND doc_date<'2026-11-01' GROUP BY item_code,product_name ORDER BY amount DESC,item_code")
        query('october_products', "SELECT item_code,product_name,sum(amount) AS amount FROM independent_sales WHERE canceled='N' AND currency='BS' AND doc_date>='2026-10-01' AND doc_date<'2026-11-01' GROUP BY item_code,product_name ORDER BY amount DESC,item_code LIMIT 10")
        for month in ('2026-10', '2026-09'):
            query('global_products_'+month, "SELECT item_code,product_name,sum(amount) AS amount FROM independent_sales WHERE canceled='N' AND currency='BS' AND substr(doc_date,1,7)=? GROUP BY item_code,product_name ORDER BY amount DESC,item_code", (month,))
            query('customer_products_'+month, "SELECT item_code,product_name,sum(amount) AS amount FROM independent_sales WHERE canceled='N' AND currency='BS' AND card_code='C000143' AND substr(doc_date,1,7)=? GROUP BY item_code,product_name ORDER BY amount DESC,item_code", (month,))
    report['status'] = 'EXECUTED_REQUIRES_SAME_SCOPE_BUSINESS_REVIEW'
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('output_must_be_new')
    run(args)
