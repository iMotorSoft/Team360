"""Independent bounded row arithmetic for the fixed DEV control population.

No reuse of the model's aggregation SQL. This does NOT certify arbitrary model
claims, period completeness, brand membership or a causal channel explanation.
"""
from decimal import Decimal, localcontext

from .contracts import ExploratoryQueryProposal
from .foundation import CATALOG, END, SKUS, START
from .validator import context_digest, validate


def control_proposals():
    def make(sql, source, grain):
        return ExploratoryQueryProposal(sql, 'independent_control', 'bounded independent row reference',
                                        (source,), grain, 'control')
    return (
        make('SELECT sum(line_total) AS amount FROM sales_line', 'sales_line', 'total'),
        *(make('SELECT ' + ','.join(c.name for c in table.columns) + ' FROM ' + table.name,
               table.name, ','.join(table.grain)) for table in CATALOG.tables))


def verify_control(context, results, *, reference_proposals=None, allow_supported_channel=False):
    """Only exact controller-owned reference results; truncation never certifies."""
    blocked = lambda reason: dict(state='BLOCKED', reason=reason, claims=[])
    if context.catalog != CATALOG or len(results) != 3:
        return blocked('reference_context_or_count')
    proposals = control_proposals() if reference_proposals is None else reference_proposals
    # Only budget differences are accepted; model-owned SQL is never a reference.
    from dataclasses import replace
    if len(proposals) != 3 or any(replace(p, requested_budget=original.requested_budget) != original
                                  for p, original in zip(proposals, control_proposals())):
        return blocked('reference_proposal_mismatch')
    for proposal, result in zip(proposals, results):
        _, query = validate(proposal, context)
        if (query is None or result.query_id != query.query_id or result.status != 'COMPLETED'
                or result.source != CATALOG.dataset or result.truncated
                or (result.publication, result.snapshot) != (context.publication, context.snapshot)
                or query.context_digest not in result.evidence
                or result.returned_count != len(result.rows)):
            return blocked('reference_missing_truncated_or_binding_mismatch')
    total, headers, lines = results
    if len(total.rows) != 1 or len(total.rows[0]) != 1:
        return blocked('invalid_control_shape')
    for table, result in zip(CATALOG.tables, (headers, lines)):
        if tuple(c.name for c in result.schema) != tuple(c.name for c in table.columns):
            return blocked('reference_schema_mismatch')
    docs = [dict(zip((c.name for c in CATALOG.tables[0].columns), row)) for row in headers.rows]
    detail = [dict(zip((c.name for c in CATALOG.tables[1].columns), row)) for row in lines.rows]
    keys = [d['doc_entry'] for d in docs]
    line_keys = [(r['doc_entry'], r['line_num']) for r in detail]
    if (None in keys or len(keys) != len(set(keys)) or len(line_keys) != len(set(line_keys))
            or any(None in k for k in line_keys)):
        return blocked('duplicate_or_null_documentary_key')
    by_doc = {d['doc_entry']: d for d in docs}
    groups = {name: {} for name in ('product', 'channel', 'seller', 'series')}
    unique_docs, null_channels, supported_channel_lines = set(), 0, 0
    with localcontext() as arithmetic:
        arithmetic.prec = 50
        amount = Decimal(0)
        for line in detail:
            doc = by_doc.get(line['doc_entry'])
            if doc is None:
                return blocked('orphan_line')
            if (line['item_code'] not in SKUS or not START <= doc['doc_date'] < END
                    or line['currency'] != 'BS' or doc['currency'] != 'BS'):
                return blocked('population_period_or_currency_mismatch')
            if any(doc[k] is None or doc[k] != line[k] for k in ('raw_extraction_id', 'source_as_of')):
                return blocked('header_line_lineage_mismatch')
            try:
                value = Decimal(str(line['line_total']))
                if not value.is_finite():
                    return blocked('invalid_line_amount')
            except Exception:
                return blocked('invalid_line_amount')
            amount += value
            unique_docs.add(line['doc_entry'])
            channel = doc['sales_channel_code']
            if channel is not None and doc['sales_channel_semantic_status'] != 'CONFIRMED':
                if not allow_supported_channel or doc['sales_channel_semantic_status'] != 'SUPPORTED':
                    return blocked('unconfirmed_classified_channel')
                supported_channel_lines += 1
            null_channels += channel is None
            for dimension, key in (('product', line['item_code']), ('channel', channel),
                                   ('seller', doc['slp_code']), ('series', doc['series'])):
                bucket = groups[dimension]
                bucket[key] = bucket.get(key, Decimal(0)) + value
        if unique_docs != set(keys):
            return blocked('reference_header_population_mismatch')
        if not detail or total.rows[0][0] is None or Decimal(str(total.rows[0][0])) != amount:
            return blocked('empty_population_or_total_mismatch')
        partitions = all(sum(g.values(), Decimal(0)) == amount for g in groups.values())
        if not partitions:
            return blocked('partition_not_reconciled')
        horizontal = groups['channel'].get('HORIZONTAL', Decimal(0))
        return dict(state='VERIFIED_WITH_LIMITATIONS', total=str(amount),
            breakdowns={dim: [{'key': k, 'amount': str(v)} for k, v in group.items()]
                        for dim, group in groups.items()},
            horizontal_percent=None if amount == 0 else str(horizontal / amount * 100),
            null_channel_lines=null_channels, supported_channel_lines=supported_channel_lines,
            document_count=len(unique_docs), line_count=len(detail),
            checks=['unique_header_keys', 'unique_line_keys', 'many_lines_to_one_header',
                    'no_join_fanout', 'header_line_lineage', 'BS_currency', 'period_and_SKUs',
                    'independent_decimal_total', 'disjoint_complete_partitions', 'pinned_provenance'],
            limitations=(['SUPPORTED channel labels are published evidence, NOT CONFIRMED business classification']
                         if supported_channel_lines else []) + ['bounded reference, truncation blocks verification',
                         'published classification, not historical classification',
                         'month completeness not certified', 'SKU set is not universal brand membership',
                         'no header net billing or credit memo reconciliation',
                         'channel causality and new relationships remain INVESTIGATIVE'])
