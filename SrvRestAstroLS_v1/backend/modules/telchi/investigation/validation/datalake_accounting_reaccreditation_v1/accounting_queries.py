"""Research-only SQL contract. Not a reader, authorization engine or SAP extractor.

Normalized relations must be populated only after source/accreditation gates.
Company + publication + snapshot are mandatory partitions. All lines survive;
no line is inferred from a document total, warehouse, seller or branch name.
Actual authorization must use Team360's existing resolver before these queries.
"""

SCHEMA = '''
CREATE TABLE journal (
 company VARCHAR NOT NULL, publication VARCHAR NOT NULL, snapshot VARCHAR NOT NULL,
 trans_id VARCHAR NOT NULL, posting_date DATE NOT NULL, document_date DATE,
 due_date DATE, source_type VARCHAR, base_ref VARCHAR, reversal_of VARCHAR,
 origin_status VARCHAR,
 PRIMARY KEY(company, publication, snapshot, trans_id));
CREATE TABLE journal_line (
 company VARCHAR NOT NULL, publication VARCHAR NOT NULL, snapshot VARCHAR NOT NULL,
 trans_id VARCHAR NOT NULL, line_id INTEGER NOT NULL, account VARCHAR NOT NULL,
 account_name VARCHAR, short_name VARCHAR, branch_id VARCHAR,
 dimension1 VARCHAR, dimension2 VARCHAR, dimension3 VARCHAR, dimension4 VARCHAR, dimension5 VARCHAR,
 PRIMARY KEY(company, publication, snapshot, trans_id, line_id));
-- One row per original line and currency basis, never sum bases together.
CREATE TABLE line_amount (
 company VARCHAR NOT NULL, publication VARCHAR NOT NULL, snapshot VARCHAR NOT NULL,
 trans_id VARCHAR NOT NULL, line_id INTEGER NOT NULL,
 basis VARCHAR NOT NULL CHECK(basis IN ('LOCAL','SYSTEM','FOREIGN')),
 currency VARCHAR NOT NULL, debit DECIMAL(38,6) NOT NULL, credit DECIMAL(38,6) NOT NULL,
 PRIMARY KEY(company, publication, snapshot, trans_id, line_id, basis, currency));
CREATE TABLE document_link (
 company VARCHAR NOT NULL, publication VARCHAR NOT NULL, snapshot VARCHAR NOT NULL,
 document_type VARCHAR NOT NULL, doc_entry VARCHAR NOT NULL, doc_num VARCHAR,
 series VARCHAR, trans_id VARCHAR, documentary_branch_id VARCHAR, cancelled VARCHAR,
 PRIMARY KEY(company, publication, snapshot, document_type, doc_entry));
-- Not an account current balance: certified at the exact requested period start,
-- same account/basis/currency/branch grain and same authorized evidence scope.
CREATE TABLE opening (
 company VARCHAR, publication VARCHAR, snapshot VARCHAR, account VARCHAR,
 basis VARCHAR, currency VARCHAR, branch_id VARCHAR, at_date DATE,
 signed_debit_minus_credit DECIMAL(38,6), accredited BOOLEAN);
'''

PARTITION = 'company=? AND publication=? AND snapshot=?'
DIARY = f'''SELECT j.*,l.* EXCLUDE(company,publication,snapshot,trans_id),a.basis,a.currency,a.debit,a.credit
FROM journal j JOIN journal_line l USING(company,publication,snapshot,trans_id)
JOIN line_amount a USING(company,publication,snapshot,trans_id,line_id)
WHERE j.company=? AND j.publication=? AND j.snapshot=?
AND j.posting_date>=? AND j.posting_date<? AND a.basis=? AND a.currency=?
ORDER BY j.posting_date,j.trans_id,l.line_id'''

INVOICE = '''SELECT d.document_type,d.doc_entry,d.doc_num,d.series,d.cancelled,
d.documentary_branch_id,j.trans_id,j.posting_date,j.source_type,j.reversal_of,
l.line_id,l.account,l.account_name,l.branch_id AS accounting_branch_id,
l.dimension1,l.dimension2,l.dimension3,l.dimension4,l.dimension5,
a.basis,a.currency,a.debit,a.credit
FROM document_link d LEFT JOIN journal j USING(company,publication,snapshot,trans_id)
LEFT JOIN journal_line l USING(company,publication,snapshot,trans_id)
LEFT JOIN line_amount a USING(company,publication,snapshot,trans_id,line_id)
WHERE d.company=? AND d.publication=? AND d.snapshot=? AND d.document_type=? AND d.doc_entry=?
ORDER BY l.line_id,a.basis,a.currency'''

UNLINKED = f'''SELECT d.* FROM document_link d LEFT JOIN journal j
USING(company,publication,snapshot,trans_id) WHERE d.company=? AND d.publication=? AND d.snapshot=?
AND j.trans_id IS NULL'''

BALANCE = f'''SELECT trans_id,basis,currency,sum(debit) AS debit,sum(credit) AS credit,
sum(debit-credit) AS difference FROM line_amount WHERE {PARTITION}
GROUP BY 1,2,3 ORDER BY 1,2,3'''

# Signed bookkeeping balance only. Business presentation additionally requires an
# accredited per-account DEBIT_NORMAL/CREDIT_NORMAL convention (never GroupMask guess).
LEDGER = '''WITH movements AS (
 SELECT l.branch_id,sum(a.debit) AS debit,sum(a.credit) AS credit
 FROM journal j JOIN journal_line l USING(company,publication,snapshot,trans_id)
 JOIN line_amount a USING(company,publication,snapshot,trans_id,line_id)
 WHERE j.company=? AND j.publication=? AND j.snapshot=? AND l.account=?
 AND a.basis=? AND a.currency=? AND j.posting_date>=? AND j.posting_date<?
 GROUP BY l.branch_id), initial AS (
 SELECT branch_id,signed_debit_minus_credit AS initial_balance
 FROM opening WHERE company=? AND publication=? AND snapshot=? AND account=?
 AND basis=? AND currency=? AND at_date=? AND accredited=true)
SELECT coalesce(m.branch_id,i.branch_id) AS branch_id,i.initial_balance,
coalesce(m.debit,0) AS debit,coalesce(m.credit,0) AS credit,
i.initial_balance+coalesce(m.debit,0)-coalesce(m.credit,0) AS final_balance,
i.initial_balance IS NOT NULL AS balance_accredited
FROM movements m FULL OUTER JOIN initial i ON m.branch_id IS NOT DISTINCT FROM i.branch_id
ORDER BY branch_id'''


# Documentary branch and accounting branch must first resolve to the same
# accredited namespace; NULL is unknown, never a proved discrepancy.
BRANCH_DIFFERENCES = '''SELECT DISTINCT d.document_type,d.doc_entry,
d.documentary_branch_id,l.branch_id AS accounting_branch_id
FROM document_link d JOIN journal j USING(company,publication,snapshot,trans_id)
JOIN journal_line l USING(company,publication,snapshot,trans_id)
WHERE d.company=? AND d.publication=? AND d.snapshot=?
AND d.documentary_branch_id IS NOT NULL AND l.branch_id IS NOT NULL
AND d.documentary_branch_id<>l.branch_id'''

BRANCH_DOCUMENTS = '''SELECT DISTINCT d.document_type,d.doc_entry,d.doc_num,d.series
FROM document_link d JOIN journal j USING(company,publication,snapshot,trans_id)
WHERE d.company=? AND d.publication=? AND d.snapshot=?
AND j.posting_date>=? AND j.posting_date<? AND EXISTS (
SELECT 1 FROM journal_line l WHERE l.company=j.company AND l.publication=j.publication
AND l.snapshot=j.snapshot AND l.trans_id=j.trans_id AND l.branch_id=?)'''

MONTHLY = '''SELECT date_trunc('month',j.posting_date)::DATE AS month,l.branch_id,
a.basis,a.currency,sum(a.debit) AS debit,sum(a.credit) AS credit
FROM journal j JOIN journal_line l USING(company,publication,snapshot,trans_id)
JOIN line_amount a USING(company,publication,snapshot,trans_id,line_id)
WHERE j.company=? AND j.publication=? AND j.snapshot=? AND l.account=?
AND j.posting_date>=? AND j.posting_date<? AND a.basis=? AND a.currency=?
GROUP BY 1,2,3,4 ORDER BY 1,2'''


def ledger_parameters(scope, account, basis, currency, start, end):
    """Opening is exact at start; coverage of [start,end) remains a separate gate."""
    if basis not in ('LOCAL', 'SYSTEM', 'FOREIGN') or start >= end:
        raise ValueError('Invalid basis or period')
    return [*scope, account, basis, currency, start, end,
            *scope, account, basis, currency, start]


def business_balance(signed_amount, normal_side):
    if normal_side not in ('DEBIT_NORMAL', 'CREDIT_NORMAL'):
        raise ValueError('Account presentation convention not accredited')
    if signed_amount is None:
        return None
    return signed_amount if normal_side == 'DEBIT_NORMAL' else -signed_amount
