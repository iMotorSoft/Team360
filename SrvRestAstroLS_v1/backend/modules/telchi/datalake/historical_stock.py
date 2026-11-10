"""Source-native historical on-hand, not a relabelled current OITW snapshot.

The full SAP ledger is reconciled to current OITW; the historical projection is
sparse over native positions with pre-cutoff ledger entries. Absence is never
an inferred zero. This is a dated reconstruction as observed, not a frozen
accounting close, historical commitments, or a cross-item physical-unit metric.
"""
from pathlib import Path
from decimal import Decimal
from . import sales_incremental as durable
from .full_refresh_capture import verify_capture
from .independent_facts_succession import checked_path

CONTRACT='SAP_LEDGER_CLOSING_ON_HAND_V1'
DATASET='historical_inventory_balance'
CUTOFF='2026-11-01'
CLOSING_DATE='2026-10-31'
SQL='''SELECT L."ItemCode",L."Warehouse" AS "WhsCode",L."ClosingQty" AS "OnHand",
    L."ClosingRows",L."CurrentNet",W."OnHand" AS "CurrentOnHand",
    L."CurrentNet"-COALESCE(W."OnHand",0) AS "CurrentDifference",
    L."FirstDate",L."LastDate",'2026-10-31' AS "ClosingDate"
    FROM (SELECT "ItemCode","Warehouse",SUM("InQty"-"OutQty") AS "CurrentNet",
        SUM(CASE WHEN "DocDate" < ? THEN "InQty"-"OutQty" ELSE 0 END) AS "ClosingQty",
        SUM(CASE WHEN "DocDate" < ? THEN 1 ELSE 0 END) AS "ClosingRows",
        MIN("DocDate") AS "FirstDate",MAX("DocDate") AS "LastDate"
        FROM "TELCHI"."OINM" GROUP BY "ItemCode","Warehouse") L
    LEFT JOIN "TELCHI"."OITW" W ON W."ItemCode"=L."ItemCode" AND W."WhsCode"=L."Warehouse"
    WHERE L."ClosingRows">0 ORDER BY L."ItemCode",L."Warehouse"'''
SCOPE=dict(kind=CONTRACT,closing_date=CLOSING_DATE,end_exclusive=CUTOFF,
    reconstruction='SAP_BUSINESS_DATE_LEDGER_AS_OBSERVED_NOT_FROZEN_CLOSE',
    position_universe='NATIVE_LEDGER_POSITIONS_WITH_PRE_CUTOFF_ENTRIES',
    absent_position_semantics='NOT_OBSERVED_NOT_ZERO',
    quantity_unit='SAP_NATIVE_INVENTORY_QUANTITY_PER_ITEM',
    commitments_and_open_orders_historical=False)


def validate_relation(con, relation, global_control):
    """Exact native position identity, quantities and current-ledger tie-out."""
    from .operational_domains import fail
    controls=global_control['queries']['stock_per_position_ledger_reconciliation']['rows']
    if len(controls)!=1:
        fail('historical stock global reconciliation missing')
    control=controls[0]
    if any(Decimal(str(control[k]))!=0 for k in ('different_positions','max_difference','nonzero_without_ledger','nonzero_without_position')):
        fail('historical stock full SAP ledger does not reconcile')
    row=con.execute('''SELECT count(*),count(DISTINCT ("ItemCode","WhsCode")),
        sum(cast("OnHand" AS DECIMAL(38,12))),count(*) FILTER(WHERE
        "ItemCode" IS NULL OR trim("ItemCode")='' OR "WhsCode" IS NULL OR trim("WhsCode")=''
        OR try_cast("OnHand" AS DECIMAL(38,12)) IS NULL
        OR try_cast("CurrentDifference" AS DECIMAL(38,12)) IS NULL
        OR cast("CurrentDifference" AS DECIMAL(38,12))<>0
        OR try_cast("CurrentNet" AS DECIMAL(38,12)) IS NULL
        OR ("CurrentOnHand" IS NOT NULL AND try_cast("CurrentOnHand" AS DECIMAL(38,12)) IS NULL)
        OR try_cast("CurrentNet" AS DECIMAL(38,12))-coalesce(try_cast("CurrentOnHand" AS DECIMAL(38,12)),0)
            IS DISTINCT FROM try_cast("CurrentDifference" AS DECIMAL(38,12))
        OR try_cast("ClosingRows" AS BIGINT) IS NULL OR cast("ClosingRows" AS BIGINT)<=0
        OR "ClosingDate" IS DISTINCT FROM '2026-10-31') FROM '''+relation).fetchone()
    if (row[0]<=0 or row[0]>int(control['union_positions']) or row[0]!=row[1] or row[3]
            or row[2]!=Decimal(str(control['october_closing_quantity_control']))):
        fail('historical stock native identity, decimal control or position reconciliation mismatch')
    return dict(rows=row[0],closing_date=CLOSING_DATE,end_exclusive=CUTOFF,
        reconciled_current_position_universe=int(control['union_positions']),
        current_position_differences=0,historical_quantity_control=str(row[2]),
        position_universe=SCOPE['position_universe'],absent_position_semantics=SCOPE['absent_position_semantics'],
        quantity_unit=SCOPE['quantity_unit'],reconstruction=SCOPE['reconstruction'],
        quantities_across_items_are_not_a_single_unit_metric=True,
        commitments_and_open_orders_historical=False)


def load(con, recovery_root, evidence):
    from .operational_domains import fail, files_relation
    directory=Path(recovery_root)/'stock-history'/DATASET
    directory=checked_path(directory,durable.DATA_ROOT/'raw/sap/full-data-lake-refresh-capture-v1')
    receipt=verify_capture(directory)
    plan=durable.read_json(directory/'intent.json')['plan']
    if (plan['sql']!=SQL or plan['params']!=[CUTOFF,CUTOFF] or plan['keys']!=['ItemCode','WhsCode']
            or plan['sums']!=['OnHand'] or plan['semantic_scope']!=SCOPE
            or plan['nullable_keys'] is not False or plan['ordered_keys'] is not True
            or (directory/'failure.json').exists()):
        fail('historical stock source projection/scope mismatch')
    path=checked_path(evidence['path'],durable.DATA_ROOT/'staging')
    if durable.file_hash(path)!=evidence['sha256']:
        fail('historical stock global control bytes changed')
    control=durable.read_json(path)
    import hashlib
    query_id='stock_per_position_ledger_reconciliation'
    query=control['queries'][query_id]['sql']
    logs=[r for r in control['audit'] if r['query_id']==query_id and r.get('status')=='FETCHED']
    if (control.get('SAP_WRITE_COUNT')!=0 or len(logs)!=1
            or logs[0]['query_hash']!=hashlib.sha256(query.encode()).hexdigest()
            or not logs[0]['cursor_closed'] or not logs[0]['connection_closed']):
        fail('historical stock global source query binding mismatch')
    relation=files_relation([page['path'] for page in receipt['pages']])
    con.execute('CREATE TEMP VIEW '+DATASET+' AS SELECT * FROM '+relation)
    coverage=validate_relation(con,DATASET,control)
    for master,field in (('oitm','ItemCode'),('owhs','WhsCode')):
        if con.execute(f'SELECT count(*) FROM {DATASET} S ANTI JOIN {master} M ON S."{field}"=M."{field}"').fetchone()[0]:
            fail('historical stock native master identity unresolved: '+master)
    coverage.update(contract=CONTRACT,observation_start=receipt['source_before']['utc'],
        observation_end=receipt['source_after']['utc'],receipt_sha256=durable.file_hash(directory/'complete.json'))
    return coverage
