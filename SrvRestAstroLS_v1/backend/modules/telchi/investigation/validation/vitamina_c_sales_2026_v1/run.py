"""Read-only 2026 vitamin C analysis; no SAP access or Foundation changes."""
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake import category_line_amount_query as category

OUT = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/data/reports/telchi/vitamina-c-2026-v1')
PATTERN = r'VIT[ .-]*((AMIN[A]?|A)[ .-]*)?C([^A-Z]|$)|ASC[OÓ]RB|CEBION|REDOXON|LEMOVIT C|NEOVIT C|VITAXON C|PARAVIT C'


def classification(name):
    n = name.upper()
    if any(x in n for x in ('ETIQUETA', 'COLAG', 'COLLAGEN', 'SERUM', 'FACIAL', 'CORPORAL', 'NIVEA', 'POND', 'MEMORY', 'PEDIAVIT', 'KIT AMA TUS HUESOS')):
        return 'EXCLUIDO: otro producto'
    if 'ASCORB' in n:
        return 'Acido ascorbico'
    if any(x in n for x in ('ZINC', 'TRIPLE', 'CALCIO', 'MAGNES', 'MAGNATIL', 'FERROSO', 'D3', 'PROPOLEO', 'POLEN', 'ECHINACEA')):
        return 'Combinada'
    return 'Vitamina C'


def main():
    c = DuckLakeConnector()
    with c.session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        assert con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() == (True,)
        a = FoundationReader(c).resolve_on(con)
        assert (a.foundation_publication_id, a.ducklake_snapshot_id) == (category.PUBLICATION, category.SNAPSHOT)
        catalog = str(a.reference('products'))
        products = con.execute("SELECT item_code,coalesce(sap_item_name,product_name,canonical_name) FROM read_parquet(?) WHERE source_system='SAP_HANA' AND regexp_matches(upper(coalesce(sap_item_name,product_name,canonical_name)), ?)", [catalog, PATTERN]).fetchall()
        assert len(products) == len({p[0] for p in products})
        selected = [(code, name, classification(name)) for code, name in products if not classification(name).startswith('EXCLUIDO')]
        con.execute('CREATE TEMP TABLE selected(item_code VARCHAR, description VARCHAR, family VARCHAR)')
        con.executemany('INSERT INTO selected VALUES (?,?,?)', selected)
        x = DATA_ROOT / 'crosswalk/_versions' / a.foundation.reference_version / 'product_business_type/part-00000.parquet'
        assert hashlib.sha256(x.read_bytes()).hexdigest() == category.CROSSWALK_SHA256
        base = dict(date_from='2026-01-01', date_to_exclusive='2027-01-01')
        cte, args = category.scoped_source(con, a.sales('sales_document'), a.sales('sales_line'), f"read_parquet('{x}')", base)
        # Reuse published key/lineage guards; no category restriction is requested.
        exceptions = []
        category.scoped_aggregate(con, a.sales('sales_document'), a.sales('sales_line'), f"read_parquet('{x}')", base, exceptions=exceptions, require_category=False, source=(cte,args))
        scoped = cte + ', chosen AS (SELECT j.*,s.description,s.family FROM joined j JOIN selected s USING(item_code))'
        bad = con.execute(scoped + " SELECT count(*) FROM chosen WHERE doc_currency IS DISTINCT FROM 'BS' OR currency IS DISTINCT FROM 'BS' OR try_cast(quantity AS DECIMAL(38,6)) IS NULL OR NOT isfinite(try_cast(quantity AS DOUBLE))", args).fetchone()[0]
        assert bad == 0, 'Selected rows have incompatible currency/quantity'
        fields = ['mes','codigo','producto','familia','cantidad_documental','importe_bs','lineas','facturas']
        rows = con.execute(scoped + " SELECT substr(doc_date,1,7),item_code,description,family,sum(cast(quantity AS DECIMAL(38,6))),sum(cast(line_total AS DECIMAL(38,6))),count(*),count(distinct doc_entry) FROM chosen GROUP BY 1,2,3,4 ORDER BY 1,4,3", args).fetchall()
        annual = con.execute(scoped + " SELECT item_code,description,family,sum(cast(quantity AS DECIMAL(38,6))),sum(cast(line_total AS DECIMAL(38,6))),count(*) FROM chosen GROUP BY 1,2,3 ORDER BY 3,5 DESC,1", args).fetchall()
        total = con.execute(scoped + " SELECT sum(cast(line_total AS DECIMAL(38,6))),count(*),min(doc_date),max(doc_date) FROM chosen", args).fetchone()
        assert sum((r[5] for r in rows), Decimal(0)) == total[0] == sum((r[4] for r in annual), Decimal(0))
        assert sum(r[6] for r in rows) == total[1]
        assert sum((r[4] for r in rows), Decimal(0)) == sum((r[3] for r in annual), Decimal(0))
        coverage = con.execute('SELECT min(doc_date),max(doc_date),max(source_as_of) FROM '+a.sales('sales_document')+" WHERE source_system='SAP_B1_HANA' AND source_table='OINV' AND canceled='N' AND doc_date >= '2026-01-01' AND doc_date < '2027-01-01'").fetchone()
        result = dict(publication=a.foundation_publication_id,snapshot=a.ducklake_snapshot_id,as_of=str(a.foundation_data_as_of),coverage=coverage,selected_product_count=len(selected),sold_product_count=len(annual),total_bs=str(total[0]),line_count=total[1],product_sales_dates=total[2:],annual=annual,monthly=rows,excluded=[(code,name) for code,name in products if classification(name).startswith('EXCLUIDO')],selected_without_sales=[(code,name,family) for code,name,family in selected if code not in {r[0] for r in annual}],reconciliation='EXACT',currency_exceptions_selected=bad,read_only=True,sap_accessed=False)
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'mensual.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f,delimiter=';'); w.writerow(fields); w.writerows(rows)
    with (OUT/'anual.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f,delimiter=';'); w.writerow(['codigo','producto','familia','cantidad_documental','importe_bs','lineas']); w.writerows(annual)
    (OUT/'resultado.json').write_text(json.dumps(result,default=str,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,default=str,ensure_ascii=False))


if __name__ == '__main__':
    main()
