from decimal import Decimal
import json
from types import SimpleNamespace

import duckdb
import pytest

from modules.telchi.datalake import sales_continuity_candidate as c
from modules.telchi.datalake import sales_incremental as inc
from .test_sales_continuity import pair, Guard


def test_sql_comparison_ignores_lineage_preserves_money():
    con=duckdb.connect()
    try:
        con.execute('CREATE TABLE old(source_system VARCHAR,doc_entry VARCHAR,doc_total VARCHAR,source_as_of VARCHAR)')
        con.execute("INSERT INTO old VALUES ('SAP','1','1.00','old'),('SAP','2','2','old')")
        con.execute('CREATE TABLE incoming AS SELECT * FROM old')
        con.execute("UPDATE incoming SET source_as_of='new',doc_total='1' WHERE doc_entry='1'")
        con.execute("UPDATE incoming SET doc_total='3.00' WHERE doc_entry='2'")
        con.execute("INSERT INTO incoming VALUES ('SAP','3','4','new')")
        assert c.comparison_sql(con,'incoming','old')==dict(new=1,modified=1,identical=1,removed=0)
    finally: con.close()


def test_whole_document_merge_removes_obsolete_lines():
    con=duckdb.connect()
    try:
        con.execute('CREATE TABLE old(source_system VARCHAR,doc_entry VARCHAR,line_num VARCHAR,quantity VARCHAR)')
        con.execute("INSERT INTO old VALUES ('SAP','1','0','2'),('SAP','1','1','3'),('SAP','2','0','9')")
        con.execute("CREATE TABLE incoming AS SELECT * FROM old WHERE doc_entry='1' AND line_num='0'")
        con.execute("UPDATE incoming SET quantity='4'")
        stats=c.comparison_sql(con,'incoming','old',lines=True)
        assert stats==dict(new=0,modified=1,identical=0,removed=1)
        con.execute(f'CREATE TABLE full_data AS {c.merge_sql("old","incoming")}')
        assert con.execute('SELECT * FROM full_data ORDER BY doc_entry').fetchall()==[('SAP','1','0','4'),('SAP','2','0','9')]
        assert con.execute(f'SELECT * FROM ({c.merge_sql("full_data","incoming")}) EXCEPT SELECT * FROM full_data').fetchall()==[]
    finally: con.close()


def test_stream_canonical_and_raw_currency_summary(tmp_path):
    h,rows=pair()
    rows[0].update(HeaderVatSum='0.13')
    inc.seal(tmp_path/'q000001.response.json',rows)
    unit=dict(domain='sales',pages=['q000001'],committed_at='2026-10-30T00:00:00+00:00')
    con=duckdb.connect()
    try:
        con.execute('SET threads=1');con.execute("SET memory_limit='128MB'")
        inputs=tmp_path/'inputs';inputs.mkdir()
        con.execute('SET temp_directory=?',[str(inputs)])
        for domain,tables in c.TABLES.items():
            candidate=inc.transform_capture(domain,rows,dict(extraction_id='old',source_as_of=unit['committed_at']))
            for table,data in candidate.tables.items():
                spec=','.join('"'+col+'" VARCHAR' for col in data[0])
                con.execute(f'CREATE TABLE old_{table}({spec})')
        access=SimpleNamespace(relation=lambda domain,table:'old_'+table,foundation=SimpleNamespace(reference_version='ref'),manifest={'components':{'reference':{}}})
        counts,money=c.import_canonical(con,tmp_path,[unit],access,Guard())
        assert counts=={'sales_documents':1,'sales_lines':1}
        assert money[0]['header_tax']=='0.13' and money[0]['currency']=='BS'
        assert con.execute('SELECT doc_entry,reference_version FROM incoming_sales_document').fetchone()==('1','ref')
        for domain,tables in c.TABLES.items():
            for table in tables:
                con.execute(f'CREATE TEMP VIEW full_{table} AS {c.merge_sql("old_"+table,"incoming_"+table)}')
            assert not any(c.integrity(con,domain).values())
        answers=c.commercial_answers(con,'offline')
        assert answers['sales_monthly'][0]['documents']==1
        assert answers['metadata']['status']=='ISOLATED_OFFLINE_NOT_PUBLISHED'
        # Duplicate raw replay is detected; it is never accepted as a second unit.
        con.execute('INSERT INTO incoming_sales_document SELECT * FROM incoming_sales_document')
        with pytest.raises(ValueError,match='integrity'): c.integrity(con,'sales')
    finally: con.close()
