"""Deterministic representation normalization for intent comparison.

Purpose: separate REPRESENTATION differences from SEMANTIC losses. Only the
equivalence classes explicitly listed in ``EQUIVALENCES`` are applied. Anything
not listed is left untouched and must be reported as a real divergence.

This module never repairs a candidate output, never grants permission and never
changes execution state. It is a scorer-side canonical projection applied
symmetrically to gold and candidate.
"""

from copy import deepcopy
import json

# Fields ignored by the structural atom projection. These are provenance or
# lifecycle metadata, not requested business requirements.
IGNORED_KEYS = frozenset({
    'pending_clarification', 'pending', 'intent', 'schema_version', 'status',
    'evidence', 'source_turn_id',
})

# Declared representation equivalence classes. Each entry must be applied to
# BOTH gold and candidate. Adding an entry changes published metrics and
# therefore requires a new benchmark version.
EQUIVALENCES = (
    'time.periods[].end -> end_exclusive when end_exclusive absent',
    'sort: single dict -> one-element list',
    'filters[].op: eq -> in (single value preserved)',
    'filters: OR of single-predicate eq clauses on one field -> one in clause',
)


def atoms(value, ignored_keys=IGNORED_KEYS):
    """Structural atom set as ``(path, canonical_json_value)``.

    Lists are order-insensitive sets (path does not encode index). Dict keys are
    ordered by the atom sort, never by input order.
    """
    out = set()

    def visit(node, path):
        if isinstance(node, dict):
            for key, child in node.items():
                if key not in ignored_keys:
                    visit(child, path + '/' + key)
        elif isinstance(node, list):
            for child in node:
                visit(child, path)
        elif node is not None and node != '':
            out.add((path, json.dumps(node, ensure_ascii=False, sort_keys=True)))

    visit(value, '')
    return out


def canonicalize(value):
    """Apply the declared representation equivalences. Idempotent."""
    if not isinstance(value, dict):
        return deepcopy(value)
    out = deepcopy(value)

    periods = (out.get('time') or {}).get('periods')
    if isinstance(periods, list):
        for period in periods:
            if isinstance(period, dict) and 'end' in period and 'end_exclusive' not in period:
                period['end_exclusive'] = period.pop('end')

    if isinstance(out.get('sort'), dict):
        out['sort'] = [out['sort']]

    clauses = out.get('filters')
    if isinstance(clauses, list):
        for clause in clauses:
            if not isinstance(clause, list):
                continue
            for predicate in clause:
                if isinstance(predicate, dict) and predicate.get('op') == 'eq':
                    predicate['op'] = 'in'
        # OR of single eq predicates on the same field == one in predicate.
        if len(clauses) > 1 and all(
            isinstance(c, list) and len(c) == 1
            and isinstance(c[0], dict) and c[0].get('op') == 'in'
            for c in clauses
        ):
            fields = {c[0]['field'] for c in clauses}
            if len(fields) == 1:
                field = next(iter(fields))
                values = [v for c in clauses for v in c[0].get('values', [])]
                out['filters'] = [[dict(field=field, op='in', values=values)]]
    return out


def end_key_only(value):
    """Apply ONLY the end -> end_exclusive renaming, no other equivalence.

    Reproduces the published V1 end-key-only diagnostic independently.
    """
    if not isinstance(value, dict):
        return deepcopy(value)
    out = deepcopy(value)
    periods = (out.get('time') or {}).get('periods')
    if isinstance(periods, list):
        for period in periods:
            if isinstance(period, dict) and 'end' in period and 'end_exclusive' not in period:
                period['end_exclusive'] = period.pop('end')
    return out


def atoms_of(value):
    """Canonicalized structural atoms."""
    return atoms(canonicalize(value))