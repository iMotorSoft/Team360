"""Independent bounded SQL parity for the actual six-turn audit, not model output."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader


def verify(path):
    conversation=json.loads(path.read_text())
    turns=conversation['turns']
    assert len(turns)==6
    assert all(turns[i]['classification']=='DIRECT_AVAILABLE' for i in (0,1,3,4,5))
    assert turns[2]['classification']=='DIRECT_UNAVAILABLE'
    assert turns[2]['audit']['capability_calls']==0
    assert conversation['missing_period_proposal']['action']=='ASK'
    assert len({t['thread_id'] for t in turns})==1
    proof=[]
    connector=DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=2')
        con.execute("SET memory_limit='512MB'")
        con.execute("SET max_temp_directory_size='0B'")
        access=FoundationReader(connector).resolve_on(con)
        docs=access.sales('sales_document')
        credits=access.credit_memo('credit_memo_document')
        for i in (0,1):
            result=turns[i]['audit']['execution_result']
            start,end=result['period']['date_from'],result['period']['date_to_exclusive']
            totals={}
            for name,table,source_table in [('invoice',docs,'OINV'),('credit',credits,'ORIN')]:
                # Different plan: group by currency/day, sum those daily amounts in Python.
                rows=con.execute(f'''SELECT currency,substr(doc_date,1,10),COUNT(*),SUM(CAST(doc_total AS DECIMAL(38,6)))
                    FROM {table} WHERE source_system='SAP_B1_HANA' AND source_table=? AND canceled='N'
                    AND doc_date>=? AND doc_date<? GROUP BY 1,2 ORDER BY 1,2''',[source_table,start,end]).fetchall()
                totals[name]=sum((r[3] for r in rows if r[0]=='BS'),Decimal(0))
                totals[name+'_count']=sum(r[2] for r in rows if r[0]=='BS')
                totals[name+'_currencies']=sorted({r[0] for r in rows},key=str)
            row=result['rows'][0]
            assert totals['invoice']==Decimal(row['billed_amount'])
            assert totals['credit']==Decimal(row['credit_amount'])
            assert totals['invoice']-totals['credit']==Decimal(row['net_amount'])
            assert totals['invoice_count']==row['invoice_count'] and totals['credit_count']==row['credit_count']
            assert result['source']==dict(publication_id=access.foundation_publication_id,
                snapshot_id=access.ducklake_snapshot_id,updated_at=access.foundation_data_as_of)
            proof.append(dict(period=result['period'],totals=totals,difference='0.000000'))
        listed=turns[3]['audit']['execution_result']['rows']
        independent=con.execute(f'''SELECT doc_entry,doc_num,doc_date FROM {docs}
            WHERE source_system='SAP_B1_HANA' AND source_table='OINV' AND canceled='N' AND doc_date IS NOT NULL
            ORDER BY doc_date DESC,CAST(doc_entry AS BIGINT) DESC,doc_entry DESC LIMIT 5''').fetchall()
        assert independent==[(r['doc_entry'],r['doc_num'],r['doc_date']) for r in listed]
        line_result=turns[4]['audit']['execution_result']
        amount_result=turns[5]['audit']['execution_result']
        assert line_result['document']==amount_result['document']
        assert line_result['document']['doc_entry']==listed[0]['doc_entry']
        header=con.execute(f'''SELECT doc_total,currency FROM {docs} WHERE source_system='SAP_B1_HANA'
            AND source_table='OINV' AND canceled='N' AND doc_entry=?''',[listed[0]['doc_entry']]).fetchall()
        assert len(header)==1 and Decimal(header[0][0])==Decimal(amount_result['rows'][0]['amount'])
        assert header[0][1]==amount_result['rows'][0]['currency']
        line_rows=con.execute(f'''SELECT item_code,quantity FROM {access.sales('sales_line')}
            WHERE source_system='SAP_B1_HANA' AND source_table='INV1' AND doc_entry=? ORDER BY CAST(line_num AS BIGINT)''',
            [listed[0]['doc_entry']]).fetchall()
        assert line_rows==[(r['item_code'],r['quantity']) for r in line_result['rows']]
        assert amount_result['amount_source']=='OINV.DocTotal'
        proof.append(dict(invoice_number=listed[0]['doc_num'],amount=header[0][0],currency=header[0][1],
            lines=line_rows,same_parent=True))
    return dict(status='PASS',questions_available=5,comparison='BLOCKED: no supported result comparison operation',
        independent_sql_parity=proof,sap_accessed=False,foundation_modified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--conversation',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    result=verify(args.conversation)
    args.output.write_text(json.dumps(result,indent=2,default=str)+'\n')
    print(json.dumps(result,default=str))


if __name__=='__main__':
    main()
