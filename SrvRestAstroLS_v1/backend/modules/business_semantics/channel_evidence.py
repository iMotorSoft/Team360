"""Focalized Foundation read-only probe. No SAP access, reingestion or classification execution."""
import argparse
import json
from pathlib import Path
import duckdb
from modules.telchi.datalake.foundation_reader import FoundationReader


def probe():
    reader=FoundationReader();access=reader.get_current_foundation()
    result={'foundation_publication_id':access.foundation_publication_id,'snapshot':access.ducklake_snapshot_id,
            'reference_version':access.foundation.reference_version,'sap_accessed':False,'foundation_writes':0}
    conn=duckdb.connect()
    try:
        conn.execute('SET threads=2');conn.execute("SET memory_limit='512MB'")
        for dataset in ['salespersons','customers','channels']:
            try:
                path=str(access.reference(dataset)).replace("'","''")
                relation="read_parquet('"+path+"')"
                cols=conn.execute('DESCRIBE SELECT * FROM '+relation).fetchall()
                result[dataset+'_columns']=[x[0] for x in cols]
                if dataset=='salespersons':
                    # JSON avoids importing optional pandas/pytz when materializing timestamps.
                    result['seller_matches']=[json.loads(row[0]) for row in conn.execute(
                        'SELECT to_json(t) FROM '+relation+' t').fetchall()
                        if any(n in row[0].lower() for n in ['selva','luz'])]
            except Exception as exc:
                result[dataset+'_blocked']=type(exc).__name__
    finally:
        conn.close()
    with reader.open_component('sales') as session:
        session.connection.execute('SET threads=2')
        session.connection.execute("SET memory_limit='512MB'")
        relation=session.relation('sales_document')
        result['sales_document_columns']=[r[0] for r in session.connection.execute(
            'DESCRIBE SELECT * FROM '+relation).fetchall()]
        result['document_relationship_samples']=[json.loads(r[0]) for r in session.connection.execute(
            "SELECT to_json(t) FROM (SELECT source_system,source_table,doc_entry,card_code,slp_code,doc_date::VARCHAR AS doc_date,"
            "sales_channel_code,sales_channel_name,sales_channel_semantic_status FROM "+relation+
            " WHERE slp_code IN ('11','13') AND TRY_CAST(doc_date AS DATE)>=DATE '2026-09-01' AND TRY_CAST(doc_date AS DATE)<DATE '2026-10-01'"
            " ORDER BY doc_date DESC,doc_entry DESC LIMIT 4) t").fetchall()]
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    path=parser.parse_args().output;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(probe(),ensure_ascii=False,indent=2));print('Evidence written:',path)


if __name__=='__main__':
    main()
