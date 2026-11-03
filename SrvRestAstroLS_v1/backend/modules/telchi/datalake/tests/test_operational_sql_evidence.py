import duckdb
import pytest
from modules.telchi.datalake.operational_query import EvidenceConnection


def test_sql_evidence_retains_batch_unknown_identities_and_cursor_semantics():
    with duckdb.connect(config={'threads':2}) as con:
        recorded = EvidenceConnection(con)
        recorded.execute('CREATE TEMP TABLE op_unknown(doc_entry BIGINT,line_num BIGINT)')
        recorded.executemany('INSERT INTO op_unknown VALUES (?,?)', iter([(1,2),(3,4)]))
        cursor = recorded.execute('SELECT * FROM op_unknown ORDER BY doc_entry')
        assert cursor.fetchall() == [(1,2),(3,4)]
        assert recorded.statements[1] == dict(sql='INSERT INTO op_unknown VALUES (?,?)',parameters=[[1,2],[3,4]],batch=True)
        assert cursor.description[0][0] == 'doc_entry'
        with pytest.raises(duckdb.Error):
            recorded.execute('SELECT * FROM missing_relation')
        assert len(recorded.statements) == 3  # never attest a failed statement
