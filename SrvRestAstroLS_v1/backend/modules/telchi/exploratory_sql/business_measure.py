"""Reusable deterministic business-measure completeness contracts.

This module owns only measure metadata and evidence checks. It does not execute
SQL or grant access; execution remains in the existing Foundation researcher.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MeasureComponent:
    key: str
    source: str
    column: str
    sign: int
    source_table: str


@dataclass(frozen=True)
class BusinessMeasureContract:
    measure_id: str
    components: tuple[MeasureComponent, ...]
    currency: str
    grain: str
    combination: str
    shared_scope: tuple[str, ...]


TERRITORIAL_LINE_NET = BusinessMeasureContract(
    measure_id='commercial_line_net_amount.v1',
    components=(
        MeasureComponent('sales', 'sales_line', 'line_total', 1, 'INV1'),
        MeasureComponent('credit_memos', 'credit_memo_line', 'line_total', -1, 'RIN1'),
    ),
    currency='BS', grain='commercial_line',
    combination='sales - credit_memos',
    shared_scope=('period', 'territory', 'channel', 'currency', 'publication', 'snapshot'),
)


def contract_for(required_measure):
    return TERRITORIAL_LINE_NET if required_measure == 'territorial_line_net' else None


def _required_line_sum_sql(sql, source, target, source_table, target_table):
    """Keep the admitted predicates while forcing the required line sum."""
    import json
    import duckdb
    with duckdb.connect(':memory:') as db:
        raw = db.execute('SELECT json_serialize_sql(?)', [sql]).fetchone()[0]
        tree = json.loads(raw)
        node = tree['statements'][0]['node']
        seed = db.execute('SELECT json_serialize_sql(?)',
                          [f'SELECT SUM({target_table}.line_total) AS line_total FROM {target_table}']).fetchone()[0]
        sum_node = json.loads(seed)['statements'][0]['node']
        node['select_list'] = sum_node['select_list']
        node['group_expressions'] = []
        node['modifiers'] = []
        node['having'] = None
        node['having_clause'] = None
        text = json.dumps(tree, ensure_ascii=False)
        text = text.replace('"' + source + '"', '"' + target + '"')
        text = text.replace('"' + source_table + '"', '"' + source_table.replace('INV1', target_table) + '"')
        result = db.execute('SELECT json_deserialize_sql(?)', [text]).fetchone()[0]
    return result


def paired_component_proposal(proposal, required_measure, *, mapping_codes=(), territory_code=None):
    """Derive and execute the mandatory counterpart under the same scope.

    The continuation is deterministic: it preserves the admitted FROM/WHERE
    predicates but always projects the contract's required ``SUM(line_total)``.
    Luna cannot accidentally turn the counterpart into a date/count query.
    """
    contract = contract_for(required_measure)
    if contract is None or not getattr(proposal, 'sql', '').strip():
        return None
    target = next(c for c in contract.components if c.source == 'credit_memo_line')
    import re
    try:
        # Keep the exact admitted tail (FROM/WHERE predicates) and replace only
        # the projection. This remains valid for grouped/discovery SQL where the
        # generic AST serializer cannot safely normalize the projection.
        from_match = re.search(r'\bFROM\s+sales_line\b', proposal.sql, re.IGNORECASE)
        if from_match:
            tail = proposal.sql[from_match.start():]
            tail = re.sub(r'(?<![A-Za-z0-9_])sales_line(?![A-Za-z0-9_])', target.source, tail)
            tail = re.sub(r"(['\"])INV1\1", lambda m: m.group(1) + target.source_table + m.group(1), tail)
            # Credit lines receive document predicates through the existing
            # backend projection; sales-line names are not valid counterparts.
            tail = re.sub(r'(?<![A-Za-z0-9_])canceled(?![A-Za-z0-9_])', 'doc_canceled', tail)
            tail = re.sub(r'(?<![A-Za-z0-9_])currency(?![A-Za-z0-9_])', 'doc_currency', tail)
            sql = 'SELECT SUM(' + target.source + '.line_total) AS line_total ' + tail
        else:
            sql = _required_line_sum_sql(proposal.sql, 'sales_line', target.source,
                                         'INV1', target.source_table)
    except Exception:
        sql = re.sub(r'(?<![A-Za-z0-9_])sales_line(?![A-Za-z0-9_])', target.source, proposal.sql)
        sql = re.sub(r"(['\"])INV1\1", lambda m: m.group(1) + target.source_table + m.group(1), sql)
        sql = re.sub(r'(?<![A-Za-z0-9_])canceled(?![A-Za-z0-9_])', 'doc_canceled', sql)
        sql = re.sub(r'(?<![A-Za-z0-9_])currency(?![A-Za-z0-9_])', 'doc_currency', sql)
    import re
    if territory_code:
        safe_territory = re.sub(r'[^A-Za-z0-9_\-]', '', str(territory_code).upper().replace(' ', '_'))
        if safe_territory:
            if 'warehouse_business_location' not in sql:
                sql = re.sub(
                    r'\bFROM\s+' + re.escape(target.source) + r'\b',
                    'FROM ' + target.source + ' INNER JOIN warehouse_business_location '
                    'ON ' + target.source + '.whs_code = warehouse_business_location.warehouse_code',
                    sql, count=1, flags=re.IGNORECASE)
            predicates = (
                "warehouse_business_location.mapping_status = 'VALIDATED' "
                "AND warehouse_business_location.mapping_source = 'BUSINESS_CONFIRMED' "
                "AND warehouse_business_location.business_location_code = '" + safe_territory + "'")
            if re.search(r'\bWHERE\b', sql, re.IGNORECASE):
                sql = re.sub(r'\bWHERE\b', 'WHERE ' + predicates + ' AND ', sql, count=1, flags=re.IGNORECASE)
            else:
                sql += ' WHERE ' + predicates
    if sql == proposal.sql or target.source not in sql:
        return None
    from dataclasses import replace
    # The counterpart keeps every already-declared mapping source.  Declaring
    # only credit_memo_line makes the preserved warehouse join fail closed at
    # validation with ``undeclared_source``; that was the scheduled→executed
    # boundary defect in r23.  Replace the sales endpoint in candidate
    # relations as well, so the same authorized territorial relationship is
    # applied to RIN1 rather than losing the mapping declaration.
    sources = tuple(dict.fromkeys(
        target.source if source == 'sales_line' else source
        for source in proposal.requested_sources))
    if 'warehouse_business_location' in sql and 'warehouse_business_location' not in sources:
        sources = sources + ('warehouse_business_location',)
    relations = tuple(
        replace(relation,
                left_table=target.source if relation.left_table == 'sales_line' else relation.left_table,
                right_table=target.source if relation.right_table == 'sales_line' else relation.right_table)
        for relation in proposal.candidate_relations)
    return replace(proposal, sql=sql, requested_sources=sources,
                   candidate_relations=relations,
                   objective='Execute the required credit-memo component under the identical confirmed scope',
                   justification='Deterministic continuation of the existing sales scope with the contract-required SUM(line_total).')


def _source_signature(registry, claim):
    """Return source, aggregate and amount column for an issued cell."""
    issued = registry._executed_cell(claim)
    _, (_, node, source, index, _) = issued
    expression = node['select_list'][index]
    argument = expression.get('children', [{}])[0] if expression.get('children') else expression
    if argument.get('class') == 'CASE':
        cases = argument.get('case_checks') or ()
        if len(cases) != 1:
            raise ValueError('business_measure_case_scope_invalid')
        argument = cases[0].get('then_expr') or {}
    if (expression.get('function_name') != 'sum'
            or argument.get('class') != 'COLUMN_REF'
            or argument.get('column_names', [])[-1] != 'line_total'):
        raise ValueError('business_measure_component_not_line_sum')
    return source, registry._operand_scope(claim, issued_cell=issued)[1]


def deterministic_claims(registry, required_measure):
    """Build mandatory measure claims from executed cells, not model prose.

    The State Engine may have executed a required continuation while Luna's
    final response mentions only dates or one component.  For a composite line
    measure, only matching accredited ``SUM(line_total)`` cells are eligible;
    missing or ambiguous pairs return no claim and therefore remain PARTIAL.
    """
    contract = contract_for(required_measure)
    if contract is None:
        return []
    candidates = {component.source: [] for component in contract.components}
    for manifest, _query, _result, rows, _node, source in getattr(registry, 'entries', {}).values():
        for row_id in manifest.row_ids:
            for column in manifest.columns:
                ref = {'kind': 'executed_cell', 'result_id': manifest.result_id,
                       'row_id': row_id, 'column_id': column.column_id}
                try:
                    value, (_m, node, cell_source, index, _row) = registry._executed_cell(
                        ref, revalidate=False)
                    expression = node['select_list'][index]
                    argument = expression.get('children', [{}])[0] if expression.get('children') else expression
                    if argument.get('class') == 'CASE':
                        cases = argument.get('case_checks') or ()
                        if len(cases) != 1:
                            continue
                        argument = cases[0].get('then_expr') or {}
                    if (cell_source not in candidates
                            or expression.get('function_name') != 'sum'
                            or argument.get('class') != 'COLUMN_REF'
                            or argument.get('column_names', [])[-1] != 'line_total'):
                        continue
                    scope = _source_signature(registry, ref)[1]
                    candidates[cell_source].append((scope, ref, value))
                except (ValueError, KeyError, TypeError, IndexError):
                    continue
    pairs = []
    left = candidates.get('sales_line', [])
    right = candidates.get('credit_memo_line', [])
    for sales in left:
        matches = [credit for credit in right if credit[0] == sales[0]]
        if len(matches) == 1:
            pairs.append((sales, matches[0]))
    if len(pairs) != 1:
        return []
    sales, credit = pairs[0]
    return [{'kind': 'calculation', 'operation': 'subtract',
             'dependencies': [sales[1], credit[1]]}]


def verify(registry, claims, required_measure):
    """Verify required components and exact effective scope independently of prose."""
    contract = contract_for(required_measure)
    if contract is None:
        return {'complete': True, 'contract': None, 'missing': [], 'rejected': []}
    found = {}
    rejected = []
    def leaves(values):
        for value in values or ():
            if not isinstance(value, dict):
                continue
            if value.get('kind') == 'executed_cell':
                yield value
            else:
                yield from leaves(value.get('dependencies'))

    for claim in leaves(claims):
        try:
            source, scope = _source_signature(registry, claim)
            component = next((c for c in contract.components if c.source == source), None)
            if component is None:
                continue
            if component.key in found:
                continue
            found[component.key] = (claim, scope)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            rejected.append(str(exc))
    missing = [c.key for c in contract.components if c.key not in found]
    same_scope = False
    if not missing:
        scopes = [value[1] for value in found.values()]
        same_scope = all(scope == scopes[0] for scope in scopes[1:])
        if not same_scope:
            rejected.append('business_measure_scope_mismatch')
    complete = not missing and same_scope
    return {'complete': complete, 'contract': contract.measure_id,
            'required_components': [c.key for c in contract.components],
            'verified_components': sorted(found), 'missing': missing,
            'same_scope': same_scope, 'rejected': rejected}


def reconciliation(registry, claims, required_measure):
    result = verify(registry, claims, required_measure)
    if not result.get('complete'):
        return result
    contract = contract_for(required_measure)
    values = {}
    def leaves(values):
        for value in values or ():
            if value.get('kind') == 'executed_cell':
                yield value
            else:
                yield from leaves(value.get('dependencies'))
    for claim in leaves(claims):
        try:
            source, _ = _source_signature(registry, claim)
            key = next(c.key for c in contract.components if c.source == source)
            values[key] = registry._executed_cell(claim)[0]
        except (ValueError, KeyError, TypeError, IndexError):
            continue
    if set(values) != {c.key for c in contract.components}:
        result.update(complete=False, missing=[c.key for c in contract.components if c.key not in values])
        return result
    result['components'] = {key: str(value) for key, value in values.items()}
    result['value'] = str(values['sales'] - values['credit_memos'])
    result['reconciliation_valid'] = all(isinstance(v, Decimal) and v.is_finite() for v in values.values())
    result['complete'] = bool(result['reconciliation_valid'])
    return result
