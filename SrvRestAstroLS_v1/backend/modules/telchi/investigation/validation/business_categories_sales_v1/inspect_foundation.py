"""READ ONLY pinned Foundation schema evidence; no source/catalog writes."""
import argparse
import hashlib
import json
from pathlib import Path

from modules.telchi.datalake.ducklake import DuckLakeConnector, DATA_ROOT
from modules.telchi.datalake.foundation_reader import FoundationReader


def inspect(output):
    evidence = dict(read_only=True, sap_accessed=False, foundation_modified=False, queries=[])
    with DuckLakeConnector().session(read_only=True) as con:
        con.execute('SET threads=1')
        con.execute("SET memory_limit='256MB'")
        con.execute("SET max_temp_directory_size='0B'")
        assert con.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone()[0] is True
        access = FoundationReader().resolve_on(con)
        evidence['lineage'] = access.as_dict()
        relations = {'invoices': access.sales('sales_document'), 'invoice_lines': access.sales('sales_line'),
                     'credits': access.credit_memo('credit_memo_document'), 'credit_lines': access.credit_memo('credit_memo_line')}
        for name, rel in relations.items():
            sql = 'DESCRIBE SELECT * FROM ' + rel
            evidence['queries'].append(dict(name=name, sql=sql, rows=con.execute(sql).fetchall()))
        version = access.foundation.reference_version
        path = DATA_ROOT / 'crosswalk/_versions' / version / 'product_business_type/part-00000.parquet'
        evidence['classification'] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        sql = 'SELECT product_business_type,status,classification_rule_id,classification_basis,COUNT(*) FROM read_parquet(?) GROUP BY ALL ORDER BY 1,2,3,4'
        evidence['queries'].append(dict(name='classification', sql=sql, parameters=[str(path)], rows=con.execute(sql,[str(path)]).fetchall()))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(evidence, stream, indent=2, default=str)
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    inspect(parser.parse_args().output)
