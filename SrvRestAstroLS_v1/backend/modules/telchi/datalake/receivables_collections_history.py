"""Fail-closed historical adapter over the existing CxC Atomic/business contracts.

No SAP connection, capture, Foundation publication or persistent table writes.
The caller must supply a frozen normalized Atomic snapshot AND complete source
coverage controls. Overlap observations cannot be upgraded to full history.
The business kernel remains receivables_collections_business._asof_relation.
"""
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from .raw import file_hash, digest as raw_digest

from . import receivables_collections_atomic as atomic
from . import receivables_collections_business as business
from .foundation_publication import FoundationReaderError
from .foundation_read_binding import digest

CONTRACT = 'receivables-historical-asof-v1'


class HistoricalCoverageError(FoundationReaderError):
    pass


def plan(as_of, source_end_exclusive):
    """Use the existing complete-history extraction windows, not an overlap.

    Source end may exceed the requested close: later reversal lineage must be
    captured too, then evaluated at its effective date, never at extraction time.
    This function plans only; it never executes a source statement.
    """
    as_of = date.fromisoformat(as_of)
    end = date.fromisoformat(source_end_exclusive)
    if as_of < atomic.HISTORY_START or end <= as_of:
        raise HistoricalCoverageError('HISTORY_WINDOW_INCOMPLETE')
    return dict(contract=CONTRACT, as_of=as_of.isoformat(),
        history_start=atomic.HISTORY_START.isoformat(), source_end_exclusive=end.isoformat(),
        segments=[dict(id=s.segment_id, entity=s.entity, params=list(s.params))
                  for s in atomic.plan_segments(atomic.HISTORY_START, end)],
        sap_mode='READ_ONLY', publication_authorized=False)


class _Snapshot:
    """Fixed-name SQL projection, exclusively for update-time validation."""
    def __init__(self, connection, snapshot):
        self.connection = connection
        self.snapshot = snapshot
        self.participants = None
        self.documents = None

    def execute(self, sql, params=None):
        for entity in atomic.ENTITY_ORDER:
            relation = f'(SELECT * FROM telchi.atomic."{entity}" AT (VERSION => {self.snapshot}))'
            if entity == 'receivable_document' and self.documents is not None:
                relation = self.documents
            if entity == 'reconciliation_participant' and self.participants is not None:
                relation = self.participants
            sql = re.sub(r'telchi\.atomic\.(?:"'+entity+r'"|'+entity+r'\b)', lambda _: relation, sql)
        return self.connection.execute(sql, params or [])


def snapshot_fingerprint(connection, snapshot):
    if type(snapshot) is not int or snapshot < 0:
        raise HistoricalCoverageError('INVALID_HISTORY_SNAPSHOT')
    return business._source_contract(_Snapshot(connection, snapshot))


def _require(value, code):
    if not value:
        raise HistoricalCoverageError(code)


def validate_coverage(coverage, expected, source):
    """Controls must match the exact complete source plan and frozen inputs.

    These controls are publisher input, never a client/result-supplied assertion.
    Capture/physical receipts still require the canonical source producer's
    validation before this adapter is eligible for Foundation succession.
    """
    _require(isinstance(coverage, dict) and coverage.get('plan') == expected,
             'HISTORY_PLAN_MISMATCH')
    _require(coverage.get('complete') is True and coverage.get('prefix_only') is False,
             'COMPLETE_HISTORY_REQUIRED')
    _require(coverage.get('source_fingerprint') == digest(source), 'HISTORY_SOURCE_CHANGED')
    _require(coverage.get('opening_balance_status') == 'ACCREDITED', 'OPENING_BALANCE_UNACCREDITED')
    controls = coverage.get('segments', {})
    _require(set(controls) == {s['id'] for s in expected['segments']}, 'HISTORY_SEGMENT_GAP')
    totals = {name: 0 for name in atomic.ENTITY_ORDER}
    for segment in expected['segments']:
        control = controls[segment['id']]
        _require(isinstance(control, dict) and control.get('reconciled') is True
                 and type(control.get('normalized_rows')) is int and control['normalized_rows'] >= 0,
                 'HISTORY_SEGMENT_UNRECONCILED')
        totals[segment['entity']] += control['normalized_rows']
    _require(totals == {name: source['entities'][name]['row_count'] for name in totals},
             'HISTORY_NORMALIZED_COUNTS_MISMATCH')


def active_participants(events, members, end, *, native=False):
    """A cancellation undoes an original at its date; it is not a payment."""
    original = "E.cancelled IN ('N','Y')" if native else "coalesce(E.cancellation_of_reconciliation_id,'0') IN ('0','')"
    reversal = "R.cancelled='C' AND " if native else ''
    return f'''(SELECT P.* FROM {members} P JOIN {events} E USING(reconciliation_id)
        WHERE {original} AND NOT EXISTS(SELECT 1 FROM {events} R
            WHERE {reversal}R.cancellation_of_reconciliation_id=E.reconciliation_id
            AND try_cast(R.reconciliation_date AS DATE)<=DATE '{end}'))'''


def validate_cancellations(fixed, coverage):
    """Accredit native reciprocal OITR pairs using type, dates and ITR1 evidence.

    Keep explicitly accredited legacy one-way inputs compatible. Native C rows
    can never enter that path merely because a caller supplies a legacy label.
    """
    def count(sql):
        return fixed.execute(sql).fetchone()[0]
    native = count("SELECT count(*) FROM telchi.atomic.reconciliation_event WHERE cancelled='C'") > 0
    has_links = count('''SELECT count(*) FROM telchi.atomic.reconciliation_event
        WHERE cancelled IN ('Y','C') OR coalesce(cancellation_of_reconciliation_id,'0') NOT IN ('0','')''')
    if not has_links:
        return False
    if not native:
        _require(coverage.get('cancellation_link_direction') == 'REVERSAL_TO_ORIGINAL',
                 'CANCELLATION_SOURCE_SEMANTICS_UNACCREDITED')
        _require(count('''SELECT count(*) FROM telchi.atomic.reconciliation_event O
            WHERE O.cancelled IN ('Y','C') AND NOT EXISTS (
                SELECT 1 FROM telchi.atomic.reconciliation_event R
                WHERE R.cancellation_of_reconciliation_id=O.reconciliation_id
                AND try_cast(R.reconciliation_date AS DATE) IS NOT NULL)''') == 0,
            'CANCELLATION_LINEAGE_INCOMPLETE')
        _require(count('''SELECT count(*) FROM telchi.atomic.reconciliation_event R
            LEFT JOIN telchi.atomic.reconciliation_event O
            ON R.cancellation_of_reconciliation_id=O.reconciliation_id
            WHERE coalesce(R.cancellation_of_reconciliation_id,'0') NOT IN ('0','')
            AND (O.reconciliation_id IS NULL OR O.cancelled<>'Y' OR R.cancelled<>'N'
                OR coalesce(O.cancellation_of_reconciliation_id,'0') NOT IN ('0','')
                OR try_cast(R.reconciliation_date AS DATE)<try_cast(O.reconciliation_date AS DATE))''') == 0,
            'CANCELLATION_PAIR_CONTRADICTORY')
        _require(count('''SELECT count(*) FROM (SELECT cancellation_of_reconciliation_id
            FROM telchi.atomic.reconciliation_event
            WHERE coalesce(cancellation_of_reconciliation_id,'0') NOT IN ('0','')
            GROUP BY cancellation_of_reconciliation_id HAVING count(*)<>1)''') == 0,
            'AMBIGUOUS_CANCELLATION_IDENTITY')
        return False
    _require(count('''SELECT count(*)-count(DISTINCT reconciliation_id)
        FROM telchi.atomic.reconciliation_event''') == 0, 'AMBIGUOUS_CANCELLATION_IDENTITY')
    _require(count('''SELECT count(*) FROM telchi.atomic.reconciliation_event E
        LEFT JOIN telchi.atomic.reconciliation_event T
        ON E.cancellation_of_reconciliation_id=T.reconciliation_id
        WHERE E.cancelled IS NULL OR E.cancelled NOT IN ('N','Y','C')
        OR try_cast(E.reconciliation_date AS DATE) IS NULL
        OR (E.cancelled='N' AND (coalesce(E.cancellation_of_reconciliation_id,'0') NOT IN ('0','')
            OR E.reconciliation_type='7'))
        OR (E.cancelled IN ('Y','C') AND (T.reconciliation_id IS NULL
            OR T.reconciliation_id=E.reconciliation_id
            OR T.cancellation_of_reconciliation_id IS DISTINCT FROM E.reconciliation_id
            OR T.cancelled IS DISTINCT FROM CASE E.cancelled WHEN 'Y' THEN 'C' ELSE 'Y' END
            OR E.reconciliation_type IS NULL
            OR (E.cancelled='C' AND E.reconciliation_type<>'7')
            OR (E.cancelled='Y' AND E.reconciliation_type='7')
            OR E.currency IS NULL OR E.currency IS DISTINCT FROM T.currency
            OR try_cast(E.reconciliation_total AS DECIMAL(38,6)) IS NULL
            OR try_cast(E.reconciliation_total AS DECIMAL(38,6)) IS DISTINCT FROM
               try_cast(T.reconciliation_total AS DECIMAL(38,6))
            OR (E.cancelled='C' AND try_cast(E.reconciliation_date AS DATE)<try_cast(T.reconciliation_date AS DATE))
            OR try_cast(E.created_date AS DATE) IS NULL
            OR (E.cancelled='C' AND try_cast(E.created_date AS DATE)<try_cast(T.created_date AS DATE))
        ))''') == 0, 'CANCELLATION_PAIR_CONTRADICTORY')
    # CreateTS is not an ordering authority: real SAP pairs include an original
    # timestamp a few seconds AFTER C (e.g. 508848/508849). This is daily-close
    # semantics; ReconDate, flags/type and exact reversal lines determine roles.
    # Compare multisets, including non-invoice participants, all currencies and
    # ledger-line/installment identity. Equal totals alone cannot accredit a pair.
    keys = ['transaction_id','transaction_row_id','participant_short_name',
            'participant_object_type','participant_object_abs','is_credit','installment_id','foreign_currency','account']
    amounts = ['reconciled_amount','reconciled_amount_foreign','reconciled_amount_system','sum_in_matching_currency']
    # SAP-generated reconciliation journal lines (object 321) refer to their
    # own ReconNum, not to a shared invoice ID: 1040126/1040134 is a real example.
    fields = ','.join("CASE WHEN P.participant_object_type='321' AND P.participant_object_abs=E.reconciliation_id "
        "THEN '@SELF_RECONCILIATION' ELSE P.participant_object_abs END" if k == 'participant_object_abs'
        else 'P.'+k for k in keys)
    invalid_amount = ' OR '.join(f'(P.{k} IS NOT NULL AND try_cast(P.{k} AS DECIMAL(38,6)) IS NULL)' for k in amounts)
    _require(count(f'''SELECT count(*) FROM telchi.atomic.reconciliation_participant P
        JOIN telchi.atomic.reconciliation_event E USING(reconciliation_id)
        WHERE E.cancelled IN ('Y','C') AND ({invalid_amount}
        OR try_cast(P.reconciliation_date AS DATE) IS DISTINCT FROM try_cast(E.reconciliation_date AS DATE)
        OR try_cast(P.reconciled_amount AS DECIMAL(38,6)) IS NULL
        OR P.transaction_id IS NULL OR P.transaction_row_id IS NULL
        OR P.participant_object_type IS NULL OR P.participant_object_abs IS NULL
        OR P.is_credit IS NULL OR P.is_credit NOT IN ('D','C'))''') == 0,
        'INVALID_CANCELLATION_PARTICIPANT')
    left = fields + ',' + ','.join(f'try_cast(P.{k} AS DECIMAL(38,6))' for k in amounts)
    right = fields + ',' + ','.join(f'-try_cast(P.{k} AS DECIMAL(38,6))' for k in amounts)
    original = f'''SELECT E.reconciliation_id,{left} FROM telchi.atomic.reconciliation_participant P
        JOIN telchi.atomic.reconciliation_event E USING(reconciliation_id) WHERE E.cancelled='Y' '''
    reversal = f'''SELECT E.cancellation_of_reconciliation_id,{right} FROM telchi.atomic.reconciliation_participant P
        JOIN telchi.atomic.reconciliation_event E USING(reconciliation_id) WHERE E.cancelled='C' '''
    _require(count(f'''SELECT count(*) FROM (({original} EXCEPT ALL {reversal})
        UNION ALL ({reversal} EXCEPT ALL {original}))''') == 0, 'CANCELLATION_PARTICIPANTS_DIFFER')
    _require(count('''SELECT count(*) FROM telchi.atomic.reconciliation_event E
        WHERE E.cancelled IN ('Y','C') AND NOT EXISTS (SELECT 1 FROM
        telchi.atomic.reconciliation_participant P WHERE P.reconciliation_id=E.reconciliation_id)''') == 0,
        'CANCELLATION_PARTICIPANTS_MISSING')
    return True


INVOICE_DATE_CONTRACT = 'OINV_CANCELLATION_LEDGER_DATE_V1'
# Additional source evidence, not a change to any existing Atomic extraction.
INVOICE_DATE_SQL = '''SELECT I."DocEntry" AS "doc", I."CANCELED" AS "role",
 I."DocDate" AS "posting", I."TaxDate" AS "tax", I."CreateDate" AS "created",
 I."CardCode" AS "customer", I."DocCur" AS "currency", I."DocTotal" AS "total",
 I."DocTotalFC" AS "foreign_total", I."DocTotalSy" AS "system_total",
 I."TransId" AS "transaction", J."RefDate" AS "journal_posting",
 J."TaxDate" AS "journal_tax", J."CreateDate" AS "journal_created",
 J."TransType" AS "journal_type", J."CreatedBy" AS "journal_document",
 (SELECT MIN(CASE WHEN I."CANCELED"='C' AND R."BaseType"=13 THEN R."BaseEntry"
                  WHEN I."CANCELED"='Y' AND R."TargetType"=13 THEN R."TrgetEntry" END)
  FROM "INV1" R WHERE R."DocEntry"=I."DocEntry") AS "pair_min",
 (SELECT MAX(CASE WHEN I."CANCELED"='C' AND R."BaseType"=13 THEN R."BaseEntry"
                  WHEN I."CANCELED"='Y' AND R."TargetType"=13 THEN R."TrgetEntry" END)
  FROM "INV1" R WHERE R."DocEntry"=I."DocEntry") AS "pair_max",
 (SELECT COUNT(*) FROM "INV1" R WHERE R."DocEntry"=I."DocEntry") AS "lines",
 (SELECT COUNT(*) FROM "INV1" R WHERE R."DocEntry"=I."DocEntry" AND
    ((I."CANCELED"='C' AND R."BaseType"=13 AND R."BaseEntry" IS NOT NULL AND R."BaseLine">=0)
     OR (I."CANCELED"='Y' AND R."TargetType"=13 AND R."TrgetEntry" IS NOT NULL))) AS "linked_lines",
 MIN(L."RefDate") AS "ledger_min", MAX(L."RefDate") AS "ledger_max",
 COUNT(L."Line_ID") AS "ledger_lines", SUM(L."Debit"-L."Credit") AS "local_effect",
 SUM(L."FCDebit"-L."FCCredit") AS "foreign_effect",
 SUM(L."SYSDeb"-L."SYSCred") AS "system_effect"
 FROM "OINV" I LEFT JOIN "OJDT" J ON J."TransId"=I."TransId"
 LEFT JOIN "JDT1" L ON L."TransId"=I."TransId" AND L."ShortName"=I."CardCode"
 WHERE I."CANCELED" IN ('Y','C') AND I."DocDate">=? AND I."DocDate"<?
 GROUP BY I."DocEntry",I."CANCELED",I."DocDate",I."TaxDate",I."CreateDate",
 I."CardCode",I."DocCur",I."DocTotal",I."DocTotalFC",I."DocTotalSy",I."TransId",
 J."RefDate",J."TaxDate",J."CreateDate",J."TransType",J."CreatedBy"'''


def invoice_cancellation_dates(fixed, coverage):
    """Verify physical supplemental receipt, exact invoice binding and BP reversal.

    RefDate is the accounting authority. Tax/creation dates are retained evidence,
    not substituted for posting. C documents never become positive obligations.
    Existing dated legacy inputs remain supported when no supplement is supplied.
    """
    receipt = coverage.get('invoice_cancellation_receipt')
    if receipt is None:
        return {}, None
    path = Path(receipt['path'])
    _require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'INVOICE_DATE_RECEIPT_MISSING')
    manifest = json.loads((path.parent / 'manifest.json').read_text())
    _require(manifest.get('manifest_hash') == raw_digest({k:v for k,v in manifest.items() if k != 'manifest_hash'})
             == receipt.get('manifest_hash'), 'INVOICE_DATE_MANIFEST_CHANGED')
    p = coverage['plan']
    _require(manifest.get('contract') == INVOICE_DATE_CONTRACT
        and manifest.get('query_hash') == hashlib.sha256(INVOICE_DATE_SQL.encode()).hexdigest()
        and manifest.get('params') == [p['history_start'], p['source_end_exclusive']]
        and manifest.get('status') == 'COMPLETED' and manifest.get('sap_access_mode') == 'READ_ONLY'
        and manifest.get('sap_write_count') == 0
        and manifest.get('file_references') == [str(path)]
        and manifest.get('file_hashes') == [file_hash(path)]
        and manifest.get('files') == [dict(file=path.name, bytes=path.stat().st_size, sha256=file_hash(path))]
        and str(manifest.get('source_as_of', ''))[:10] >= p['as_of'], 'INVOICE_DATE_RECEIPT_INVALID')
    # Use the caller's bounded connection; no SAP or persistent writes here.
    cursor = fixed.execute('SELECT * FROM read_parquet(?)', [str(path)])
    names = [d[0] for d in cursor.description]
    rows = [dict(zip(names, r)) for r in cursor.fetchall()]
    _require(len(rows) == manifest['row_count'], 'INVOICE_DATE_COUNT_MISMATCH')
    docs = {}
    for row in rows:
        key = str(row['doc'])
        _require(key not in docs, 'INVOICE_DATE_DUPLICATE')
        docs[key] = row
    cursor = fixed.execute('''SELECT source_doc_entry, cancelled, customer_code, currency,
        document_date, document_total, document_total_foreign, document_total_system, transaction_id,
        cancel_date FROM telchi.atomic.receivable_document WHERE cancelled IN ('Y','C')''')
    obligations = cursor.fetchall()
    _require({str(r[0]) for r in obligations} == set(docs), 'INVOICE_DATE_COVERAGE_GAP')
    def day(value):
        return date.fromisoformat(str(value)[:10]).isoformat()
    def number(value):
        n = Decimal(str(value))
        _require(n.is_finite(), 'INVOICE_DATE_INVALID_AMOUNT')
        return n
    dates = {}
    for key,role,customer,currency,posting,total,fc,sy,transaction,cancel in obligations:
        r = docs[str(key)]
        t = docs.get(str(r['pair_min']))
        _require(r['role'] == role and role in ('Y','C') and t is not None
            and str(r['pair_min']) == str(r['pair_max'])
            and str(t['pair_min']) == str(t['pair_max']) == str(key)
            and t['role'] == ('C' if role == 'Y' else 'Y')
            and r['lines'] == r['linked_lines'] and r['lines'] > 0
            and r['lines'] == t['lines'], 'INVOICE_DATE_PAIR_INVALID')
        _require(r['customer'] == customer == t['customer'] and r['currency'] == currency == t['currency']
            and str(r['transaction']) == str(transaction)
            and str(r['journal_document']) == str(key) and str(r['journal_type']) == '13'
            and r['ledger_lines'] > 0
            and day(r['posting']) == day(posting) == day(r['journal_posting'])
                == day(r['ledger_min']) == day(r['ledger_max']), 'INVOICE_DATE_LEDGER_MISMATCH')
        for field, effect, expected in [('total','local_effect',total),
                ('foreign_total','foreign_effect',fc),('system_total','system_effect',sy)]:
            _require(number(r[field]) == number(expected) == number(t[field])
                and number(r[effect]) == (1 if role == 'Y' else -1)*number(expected)
                and number(r[effect]) == -number(t[effect]), 'INVOICE_DATE_REVERSAL_MISMATCH')
        reversal = t if role == 'Y' else r
        original = r if role == 'Y' else t
        effective = day(reversal['journal_posting'])
        _require(effective >= day(original['posting'])
            and (cancel is None or day(cancel) == effective), 'INVOICE_DATE_CONTRADICTION')
        dates[str(key)] = effective
    return dates, dict(contract=INVOICE_DATE_CONTRACT, manifest_hash=manifest['manifest_hash'],
        documents=len(docs), pairs=len(docs)//2, effective_date_authority='OJDT.RefDate/JDT1.RefDate',
        source_as_of=manifest['source_as_of'])


def invoice_relation(table, dates):
    """Project accredited dates without changing immutable Atomic source facts."""
    if not dates:
        return table
    values = ','.join("('"+key.replace("'", "''")+"', DATE '"+day+"')" for key,day in sorted(dates.items()))
    return f'''(SELECT D.* REPLACE(coalesce(V.effective,try_cast(D.cancel_date AS DATE)) AS cancel_date)
        FROM {table} D LEFT JOIN (VALUES {values}) V(doc,effective)
        ON D.source_doc_entry=V.doc)'''


def historical_snapshot(connection, *, snapshot, as_of, coverage):
    """Evaluate daily-close debt and aging, never cash receipts as debt.

    All effects come from invoice-side ITR1. RCT2 and ORCT are relationship
    controls, NOT additional reductions. Ambiguous cancellation lineage blocks.
    Returns validation evidence only; it cannot select or publish Foundation.
    """
    _require(isinstance(coverage, dict), 'COMPLETE_HISTORY_REQUIRED')
    source = snapshot_fingerprint(connection, snapshot)
    expected = plan(as_of, coverage.get('plan', {}).get('source_end_exclusive', as_of))
    validate_coverage(coverage, expected, source)
    for entity, metadata in source['entities'].items():
        if metadata['row_count']:
            observed = str(metadata['source_as_of_min'] or '')[:10]
            _require(observed >= as_of, 'SOURCE_OBSERVED_BEFORE_CLOSE:'+entity)
    fixed = _Snapshot(connection, snapshot)
    def count(sql):
        return fixed.execute(sql).fetchone()[0]
    for entity in atomic.ENTITY_ORDER:
        _require(count(f'SELECT count(*)-count(DISTINCT atomic_id) FROM telchi.atomic.{entity}') == 0,
                 'DUPLICATE_HISTORY_IDENTITY:'+entity)
    invoice_dates, invoice_evidence = invoice_cancellation_dates(fixed, coverage)
    fixed.documents = invoice_relation(
        f'(SELECT * FROM telchi.atomic.receivable_document AT (VERSION => {snapshot}))', invoice_dates)
    _require(count('''SELECT count(*) FROM telchi.atomic.receivable_document
        WHERE source_doc_entry IS NULL OR customer_code IS NULL
        OR try_cast(document_date AS DATE) IS NULL OR try_cast(due_date AS DATE) IS NULL
        OR try_cast(document_total AS DECIMAL(38,6)) IS NULL
        OR try_cast(document_total AS DECIMAL(38,6))<0
        OR cancelled NOT IN ('N','Y','C') OR cancelled IS NULL
        OR (cancelled IN ('Y','C') AND try_cast(cancel_date AS DATE) IS NULL)''') == 0,
        'INVALID_HISTORICAL_OBLIGATION')
    _require(count('''SELECT count(*) FROM telchi.atomic.reconciliation_participant P
        ANTI JOIN telchi.atomic.reconciliation_event E USING(reconciliation_id)''') == 0,
        'ORPHAN_RECONCILIATION_PARTICIPANT')
    _require(count('''SELECT count(*) FROM telchi.atomic.reconciliation_participant P
        ANTI JOIN telchi.atomic.receivable_document D ON P.participant_object_abs=D.source_doc_entry
        WHERE P.participant_object_type='13' ''') == 0,
        'ORPHAN_INVOICE_RECONCILIATION')
    _require(count('''SELECT count(*) FROM telchi.atomic.collection_allocation A
        ANTI JOIN telchi.atomic.collection_payment P ON A.payment_doc_entry=P.source_doc_entry''') == 0,
        'ORPHAN_COLLECTION_APPLICATION')
    native = validate_cancellations(fixed, coverage)
    _require(count('''SELECT count(*) FROM telchi.atomic.reconciliation_participant P
        JOIN telchi.atomic.reconciliation_event E USING(reconciliation_id)
        WHERE participant_object_type='13' AND (participant_object_abs IS NULL
        OR is_credit NOT IN ('D','C') OR is_credit IS NULL
        OR try_cast(P.reconciliation_date AS DATE) IS NULL
        OR try_cast(reconciled_amount AS DECIMAL(38,6)) IS NULL
        OR (E.cancelled<>'C' AND try_cast(reconciled_amount AS DECIMAL(38,6))<0)
        OR (E.cancelled='C' AND try_cast(reconciled_amount AS DECIMAL(38,6))>0))''') == 0,
        'INVALID_RECONCILIATION_EFFECT')
    end = date.fromisoformat(as_of).isoformat()
    # Only original effects count. An original canceled AFTER the requested
    # close still counts at that close; a reversal is never a second payment.
    events = f'(SELECT * FROM telchi.atomic.reconciliation_event AT (VERSION => {snapshot}))'
    members = f'(SELECT * FROM telchi.atomic.reconciliation_participant AT (VERSION => {snapshot}))'
    fixed.participants = active_participants(events, members, end, native=native)
    # Replay exactly the existing dated-balance and aging kernel.
    _require(fixed.execute(business._asof_relation(date.fromisoformat(as_of)) + '''
        SELECT count(*) FROM classified WHERE reduction<0 OR reduction>document_total+.01''').fetchone()[0] == 0,
        'HISTORICAL_RECONCILIATION_EXCEEDS_OBLIGATION')
    result = business.board_snapshot(fixed, date.fromisoformat(as_of))
    over_30 = fixed.execute(business._asof_relation(date.fromisoformat(as_of)) + '''
        SELECT coalesce(sum(open_amount) FILTER(WHERE open_amount>.01 AND days_past_due>30),0),
        count(*) FILTER(WHERE open_amount>.01 AND days_past_due>30)
        FROM classified''').fetchone()
    _require(result['total_open_receivables'] == result['current_receivables']+result['overdue_receivables'],
             'HISTORICAL_DEBT_PARTITION_FAILED')
    _require(result['overdue_receivables'] == sum(result[k] for k in
        ('aging_1_30','aging_31_60','aging_61_90','aging_91_120','aging_120_plus')),
        'HISTORICAL_AGING_PARTITION_FAILED')
    return dict(contract=CONTRACT, snapshot_id=snapshot, source_as_of=source['source_as_of'],
                source_fingerprint=digest(source), as_of=as_of, board=result,
                over_30_days_amount=over_30[0], over_30_days_documents=over_30[1],
                **({'invoice_cancellation_lineage': invoice_evidence} if invoice_evidence else {}),
                publication_ready=False,
                limitation='Historical business validation only; canonical component succession and physical source-receipt replay still required')
