"""Controller-owned row reconstruction, never model SQL or expected answers."""
from dataclasses import asdict
from decimal import Decimal, InvalidOperation, localcontext

from .adaptive_sources import CATALOG, OPERATION_COLUMNS
from .contracts import ExploratoryQueryProposal
from .foundation import SKUS, START, END
from .foundation_dev import DevBudget
from .validator import validate

REFERENCE_TABLES = tuple(t for t in CATALOG.tables if t.name != 'sales_operation')
FILTERS = frozenset(n for n, _ in OPERATION_COLUMNS) - {'line_total'}


def reference_proposals():
    return tuple(ExploratoryQueryProposal(
        'SELECT ' + ','.join(c.name for c in t.columns) + ' FROM ' + t.name,
        'independent_reference', 'sealed raw rows for Decimal reconstruction; never sent to Luna',
        (t.name,), ','.join(t.grain), 'complete bounded reference', requested_budget=DevBudget())
        for t in REFERENCE_TABLES)


def reconstruct(context, results):
    if context.catalog != CATALOG or len(results) != len(REFERENCE_TABLES):
        raise ValueError('reference_scope')
    tables = {}
    for t, p, result in zip(REFERENCE_TABLES, reference_proposals(), results):
        _, q = validate(p, context)
        if (q is None or result.query_id != q.query_id or result.status != 'COMPLETED' or result.truncated
                or (result.publication, result.snapshot) != (context.publication, context.snapshot)
                or result.source != CATALOG.dataset or q.context_digest not in result.evidence
                or result.returned_count != len(result.rows)
                or tuple(c.name for c in result.schema) != tuple(c.name for c in t.columns)):
            raise ValueError('reference_incomplete_or_binding_mismatch')
        rows = [dict(zip((c.name for c in t.columns), row)) for row in result.rows]
        keys = [tuple(row[n] for n in t.grain) for row in rows]
        if any(None in k for k in keys) or len(keys) != len(set(keys)):
            raise ValueError('reference_duplicate_or_null_key:' + t.name)
        tables[t.name] = rows
    docs = {r['doc_entry']: r for r in tables['sales_document']}
    meta = {r['doc_entry']: r for r in tables['document_metadata']}
    line_meta = {(r['doc_entry'], r['line_num']): r for r in tables['line_metadata']}
    lines = tables['sales_line']
    if (set(meta) != set(docs) or set(line_meta) != {(r['doc_entry'], r['line_num']) for r in lines}
            or {r['doc_entry'] for r in lines} != set(docs) or not lines):
        raise ValueError('reference_coverage')
    operations = []
    for line in lines:
        doc = docs[line['doc_entry']]
        if (line['item_code'] not in SKUS or not START <= doc['doc_date'] < END
                or doc['currency'] != 'BS' or line['currency'] != 'BS'
                or any(doc[k] is None or doc[k] != line[k] for k in ('raw_extraction_id', 'source_as_of'))):
            raise ValueError('population_currency_period_or_lineage')
        amount = Decimal(str(line['line_total']))
        if not amount.is_finite():
            raise ValueError('invalid_money')
        operations.append(doc | line | meta[doc['doc_entry']] | line_meta[(line['doc_entry'], line['line_num'])])
    tables['sales_operation'] = operations
    summary = summarize(operations)
    return tables, summary


def measure(rows, metric):
    with localcontext() as ctx:
        ctx.prec = 50
        if metric == 'line_amount_bs':
            return sum((Decimal(str(r['line_total'])) for r in rows), Decimal(0))
        if metric == 'document_count':
            return Decimal(len({r['doc_entry'] for r in rows}))
        if metric == 'line_count':
            return Decimal(len(rows))
    raise ValueError('unsupported_metric')


def summarize(rows):
    total = measure(rows, 'line_amount_bs')
    groups = {}
    for field in ('sales_channel_code', 'slp_code', 'series', 'user_sign', 'whs_code', 'item_code'):
        groups[field] = []
        for key in sorted({r[field] for r in rows}, key=lambda x: (x is not None, str(x))):
            selected = [r for r in rows if r[field] == key]
            amount = measure(selected, 'line_amount_bs')
            with localcontext() as ctx:
                ctx.prec = 50
                share = str(amount / total * 100) if total else None
            groups[field].append(dict(key=key, amount_bs=str(amount), percent=share,
                                      document_count=int(measure(selected, 'document_count')), line_count=len(selected)))
        if sum((Decimal(g['amount_bs']) for g in groups[field]), Decimal(0)) != total:
            raise ValueError('partition_reconciliation')
    return dict(state='VERIFIED_WITH_LIMITATIONS', total_bs=str(total),
                document_count=int(measure(rows, 'document_count')), line_count=len(rows), groups=groups,
                checks=['unique_header_and_line_keys', 'complete_many_lines_to_one_header', 'no_join_fanout',
                        'independent_decimal_arithmetic', 'disjoint_complete_amount_partitions',
                        'BS_currency', 'four_SKUs_and_period', 'matching_lineage', 'pinned_versions'],
                unique_documents_not_additive_across_line_dimensions=True)


def verify_claim(claim, rows):
    try:
        if not isinstance(claim, dict) or set(claim) != {'metric', 'filters', 'value'}:
            raise ValueError('invalid_claim_shape')
        filters = claim['filters']
        if (not isinstance(filters, dict) or not set(filters) <= FILTERS
                or any(v is not None and not isinstance(v, str) for v in filters.values())):
            raise ValueError('unsupported_filters')
        raw = claim['value']
        if not isinstance(raw, str) or len(raw) > 64:
            raise ValueError('invalid_claim_value')
        value = Decimal(raw)
        if not value.is_finite():
            raise ValueError('invalid_claim_value')
        selected = [r for r in rows if all(r[k] == v for k, v in filters.items())]
        expected = measure(selected, claim['metric'])
        return dict(claim=claim, state='VERIFIED' if expected == value else 'UNVERIFIED',
                    match=expected == value, expected=str(expected), reason='independent_row_reconstruction')
    except (ValueError, InvalidOperation, KeyError, TypeError) as exc:
        return dict(claim=claim, state='UNVERIFIED', reason=str(exc)[:100])


def profile_relation(relation, tables):
    """Technical link validation never accredits a new business interpretation."""
    try:
        left = [r[relation.left_column] for r in tables[relation.left_table]]
        right = [r[relation.right_column] for r in tables[relation.right_table]]
    except KeyError:
        return dict(relation=asdict(relation), state='BLOCKED', reason='unsupported_reference_scope')
    lkeys, rkeys = set(left) - {None}, set(right) - {None}
    counts = {k: right.count(k) for k in rkeys}
    matched = sum(k is not None and k in rkeys for k in left)
    pairs = sum(counts.get(k, 0) for k in left if k is not None)
    return dict(relation=asdict(relation), state='INVESTIGATIVE',
                left_rows=len(left), right_rows=len(right), matched_left_rows=matched,
                left_nulls=left.count(None), right_nulls=right.count(None),
                unmatched_left_keys=sorted(lkeys-rkeys), right_unique=len(rkeys) == len(right),
                inner_join_pairs=pairs, left_join_rows=pairs+len(left)-matched,
                multiplication_detected=any(counts.get(k, 0) > 1 for k in lkeys),
                meaning='Key equality and coverage do not accredit business equivalence. Seller category is not operation channel.')
