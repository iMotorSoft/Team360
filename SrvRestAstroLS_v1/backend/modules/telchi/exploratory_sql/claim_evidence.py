"""Server-issued evidence identities and independent, fail-closed analytical checks.

SQL remains free within the existing validator. Unsupported analytical shapes may
execute but cannot acquire business authority. No alias-to-metric dictionary.
The verifier reads reconstructed reference rows, never executes model SQL.
"""
from dataclasses import asdict
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP
import json
from uuid import uuid4

from .contracts import SQLColumnEvidence, SQLResultEvidence
from .validator import canonical, context_digest, digest

# Definitions of existing business measures by source expression, NOT aliases.
MEASURES = {
    ('sales_operation', 'line_total'): ('line_amount_bs', 'money', 'BS', 'commercial_line'),
    ('sales_line', 'line_total'): ('line_amount_bs', 'money', 'BS', 'commercial_line'),
}
METRIC_DEFINITIONS = {
    'line_amount_bs': 'Sum of commercial line_total in BS, before credit memos/global adjustments; not header total, net billing or collections.',
    'line_count': 'Count of source commercial lines in the identified result group.',
    'document_count': 'Distinct doc_entry in the identified result group; not additive across overlapping line groups.',
}
LIMITS = ('Current materialized publication, not certified historical classification.',
          'Published rows only; complete calendar coverage is not certified.',
          'Line amounts precede credit memos/global adjustments; not net billing or collections.',
          'No classifier rule/version or causal mechanism is accredited.')


def identity():
    return uuid4().hex[:24]


def clean(expr):
    if isinstance(expr, dict):
        return {k: clean(v) for k, v in expr.items() if k not in {'alias', 'query_location'}}
    if isinstance(expr, list):
        return [clean(v) for v in expr]
    return expr


def expression_label(expr):
    """Compact lineage for the wire, never executable SQL or semantic authority."""
    cls = expr.get('class')
    if cls == 'COLUMN_REF': return '.'.join(expr['column_names'])
    if cls == 'CONSTANT': return canonical(None if expr['value']['is_null'] else expr['value']['value'])
    if cls == 'FUNCTION':
        return expr['function_name'] + '(' + ('DISTINCT ' if expr.get('distinct') else '') + ','.join(expression_label(e) for e in expr['children']) + ')'
    if cls == 'CASE':
        return 'CASE ' + ' '.join('WHEN '+expression_label(c['when_expr'])+' THEN '+expression_label(c['then_expr']) for c in expr['case_checks']) + ' ELSE ' + expression_label(expr['else_expr']) + ' END'
    if cls == 'COMPARISON': return expression_label(expr['left']) + ' ' + expr['type'] + ' ' + expression_label(expr['right'])
    if 'children' in expr: return expr['type'] + '(' + ','.join(expression_label(e) for e in expr['children']) + ')'
    return 'unaccredited_expression'


def fields(expr, source):
    if not isinstance(expr, dict):
        return set()
    if expr.get('class') == 'COLUMN_REF':
        names = expr['column_names']
        return {source + '.' + names[-1]} if source else set()
    out = set()
    for v in expr.values():
        for child in (v if isinstance(v, list) else [v]):
            out |= fields(child, source)
    return out


def evaluate(expr, row, parameters):
    """Small independent scalar interpreter; unknown forms never imply truth."""
    if expr is None:
        return True
    cls, typ = expr.get('class'), expr.get('type')
    if cls == 'COLUMN_REF':
        return row[expr['column_names'][-1]]
    if cls == 'CONSTANT':
        return None if expr['value']['is_null'] else expr['value']['value']
    if cls == 'PARAMETER':
        return parameters[expr['identifier']]
    child = lambda e: evaluate(e, row, parameters)
    if cls == 'FUNCTION' and expr.get('function_name') in {'lower', 'upper', 'contains'}:
        values = [child(e) for e in expr['children']]
        if any(v is None for v in values):
            return None
        if not all(isinstance(v, str) for v in values):
            raise ValueError('independent_string_type_mismatch')
        fn = expr['function_name']
        return values[1] in values[0] if fn == 'contains' else values[0].lower() if fn == 'lower' else values[0].upper()
    if cls == 'CASE':
        for case in expr['case_checks']:
            if child(case['when_expr']) is True:
                return child(case['then_expr'])
        return child(expr['else_expr'])
    if cls == 'COMPARISON':
        a, b = child(expr['left']), child(expr['right'])
        if typ == 'COMPARE_NOT_DISTINCT_FROM':
            return a == b
        if a is None or b is None:
            return None
        ops = {'COMPARE_EQUAL': lambda: a == b, 'COMPARE_NOTEQUAL': lambda: a != b,
               'COMPARE_LESSTHAN': lambda: a < b, 'COMPARE_GREATERTHAN': lambda: a > b,
               'COMPARE_LESSTHANOREQUALTO': lambda: a <= b, 'COMPARE_GREATERTHANOREQUALTO': lambda: a >= b}
        return ops[typ]()
    if cls in {'CONJUNCTION', 'OPERATOR'}:
        values = [child(e) for e in expr['children']]
        if typ == 'CONJUNCTION_AND':
            return False if False in values else None if None in values else True
        if typ == 'CONJUNCTION_OR':
            return True if True in values else None if None in values else False
        if typ == 'OPERATOR_IS_NULL': return values[0] is None
        if typ == 'OPERATOR_IS_NOT_NULL': return values[0] is not None
        if typ == 'OPERATOR_NOT': return None if values[0] is None else not values[0]
        if typ == 'OPERATOR_COALESCE': return next((v for v in values if v is not None), None)
        if typ in {'COMPARE_IN', 'COMPARE_NOT_IN'}:
            hit = values[0] in [v for v in values[1:] if v is not None] if values[0] is not None else False
            result = True if hit else None if None in values else False
            return (not result if result is not None else None) if typ == 'COMPARE_NOT_IN' else result
    raise ValueError('unsupported_independent_expression')


def metric_for(expr, source):
    fn = expr.get('function_name') if expr.get('class') == 'FUNCTION' else None
    args = expr.get('children', [])
    field = args[0]['column_names'][-1] if len(args) == 1 and args[0].get('class') == 'COLUMN_REF' else None
    if fn == 'sum' and not expr.get('distinct') and (source, field) in MEASURES:
        return MEASURES[source, field]
    if source == 'sales_document' and fn in {'count', 'count_star'} and (fn == 'count_star' or field == 'doc_entry'):
        return 'document_count', 'documents', None, 'document'
    if source in {'sales_operation', 'sales_line'}:
        if fn == 'count_star' or (fn == 'count' and field in {'doc_entry', 'line_num'} and not expr.get('distinct')):
            return 'line_count', 'lines', None, 'commercial_line'
        if fn == 'count' and field == 'doc_entry' and expr.get('distinct'):
            return 'document_count', 'documents', None, 'document'
    return None, None, None, 'unaccredited'


class EvidenceRegistry:
    """Run-local, immutable result handles. IDs are never resolved by alias."""
    def __init__(self, context, tables, temporal_scope):
        self.context, self.tables, self.temporal_scope = context, tables, tuple(temporal_scope)
        self.entries = {}

    def register(self, query, result, visible_rows):
        if query is None or result.status != 'COMPLETED':
            return None
        expected_source = 'synthetic' if self.context.catalog.synthetic_only else self.context.catalog.dataset
        if (result.query_id != query.query_id or result.source != expected_source
                or (result.publication, result.snapshot) != (self.context.publication, self.context.snapshot)
                or context_digest(self.context) != query.context_digest or query.context_digest not in result.evidence
                or result.returned_count != len(result.rows)):
            raise ValueError('result_execution_binding_mismatch')
        if tuple(visible_rows) != result.rows[:len(visible_rows)]:
            raise ValueError('visible_rows_not_bound_to_result')
        node = json.loads(query.admitted_tree_json)['statements'][0]['node']
        base = node['from_table']
        simple = base.get('type') == 'BASE_TABLE' and not node['cte_map']['map']
        source = base.get('table_name') if simple else None
        expressions = node['select_list']
        if len(expressions) != len(result.schema):
            raise ValueError('result_schema_binding_mismatch')
        columns = []
        occurrences = {}
        for col, expr in zip(result.schema, expressions):
            metric, unit, currency, grain = metric_for(expr, source)
            direct = expr.get('class') == 'COLUMN_REF' and source in self.tables
            key = canonical(clean(expr))
            occurrence = occurrences.get(key, 0)
            occurrences[key] = occurrence + 1
            column_id = digest((self.context.catalog.dataset, self.context.publication, self.context.snapshot, source, clean(expr), col.sql_type, occurrence))[:24]
            columns.append(SQLColumnEvidence(column_id, col.name, col.sql_type, expression_label(expr),
                tuple(sorted(fields(expr, source))), 'SOURCE' if direct else 'CALCULATION',
                metric, METRIC_DEFINITIONS.get(metric), grain if metric else
                'group_dimension' if simple and any(clean(expr) == clean(g) for g in node['group_expressions']) else 'unaccredited',
                () if direct else (expression_label(expr),),
                unit, currency, 'MATERIALIZED_SOURCE' if direct else 'DERIVED_NOT_OFFICIAL',
                () if simple else ('Analytical lineage across CTE/subquery/join is not accredited.',)))
        manifest = SQLResultEvidence(identity(), query.query_id, identity(), self.context.catalog.dataset,
            result.publication, result.snapshot,
            ('group_of_source_rows' if node['group_expressions'] else 'aggregate_of_authorized_subset' if any(c.metric for c in columns) else 'unaccredited') if simple else 'unaccredited',
            tuple(columns), tuple(identity() for _ in visible_rows), query.relations,
            self.temporal_scope, expression_label(node['where_clause']) if node['where_clause'] else 'entire_authorized_universe',
            tuple(expression_label(g) for g in node['group_expressions']), LIMITS + result.limitations)
        self.entries[manifest.result_id] = (manifest, query, result, tuple(visible_rows), node, source)
        return asdict(manifest)

    def _cell(self, ref):
        if not isinstance(ref, dict): raise ValueError('invalid_evidence_reference')
        if ref.get('result_id') not in self.entries: raise ValueError('unknown_result_id')
        manifest, query, result, rows, node, source = self.entries[ref['result_id']]
        indexes = {c.column_id: i for i, c in enumerate(manifest.columns)}
        if ref.get('column_id') not in indexes: raise ValueError('unknown_column_id')
        if ref.get('row_id') not in manifest.row_ids: raise ValueError('unknown_or_undisclosed_row_id')
        col_index, row_index = indexes[ref['column_id']], manifest.row_ids.index(ref['row_id'])
        return manifest, query, result, rows[row_index], node, source, col_index

    def _population(self, node, source, output, query):
        if source not in self.tables: raise ValueError('unaccredited_join_or_derived_lineage')
        # Named parameters refer to proposal names, not regenerated SQL parameter indexes.
        # Original AST PARAMETER cannot safely be rebound from rewritten names.
        if '"class":"PARAMETER"' in canonical(node):
            raise ValueError('unaccredited_named_parameter_lineage')
        params = {}
        rows = [r for r in self.tables[source] if evaluate(node['where_clause'], r, params) is True]
        for group in node['group_expressions']:
            matches = [i for i, e in enumerate(node['select_list']) if clean(e) == clean(group)]
            if len(matches) != 1: raise ValueError('group_key_not_identifiable')
            observed = output[matches[0]]
            rows = [r for r in rows if evaluate(group, r, params) == observed]
        if node['group_expressions'] and not rows:
            raise ValueError('group_has_no_independent_source_rows')
        return rows

    def _measure(self, ref):
        m, q, result, output, node, source, index = self._cell(ref)
        col = m.columns[index]
        for relation in q.relations:
            table, field = relation.right
            keys = [r[field] for r in self.tables.get(table, []) if r[field] is not None]
            if len(keys) != len(set(keys)):
                raise ValueError('join_multiplication_detected')
        if q.relations:
            raise ValueError('join_business_grain_not_accredited')
        if m.publication != self.context.publication or m.snapshot != self.context.snapshot:
            raise ValueError('foundation_version_changed')
        if (ref.get('publication'), ref.get('snapshot')) != (m.publication, m.snapshot):
            raise ValueError('claim_foundation_version_mismatch')
        if ref.get('temporal_scope') != list(m.temporal_scope): raise ValueError('temporal_scope_mismatch')
        if col.metric is None: raise ValueError('metric_definition_not_accredited')
        expected = metric_for(node['select_list'][index], source)
        if (ref.get('metric'), ref.get('unit'), ref.get('currency'), ref.get('grain')) != expected:
            raise ValueError('measure_unit_currency_or_grain_mismatch')
        if ref.get('classification') != 'observed':
            raise ValueError('source_vs_derived_or_official_classification_not_accredited')
        rows = self._population(node, source, output, q)
        if col.currency and any(r.get('currency') != col.currency for r in rows):
            raise ValueError('incompatible_source_currency')
        with localcontext() as ctx:
            ctx.prec = 50
            if col.metric == 'line_amount_bs': value = sum((Decimal(str(r['line_total'])) for r in rows), Decimal(0))
            elif col.metric == 'line_count': value = Decimal(len(rows))
            else: value = Decimal(len({r['doc_entry'] for r in rows}))
        observed = output[index]
        if isinstance(observed, bool) or not any(t in col.sql_type for t in ('INT', 'DECIMAL', 'DOUBLE', 'FLOAT', 'HUGEINT')):
            raise ValueError('result_type_mismatch')
        if Decimal(str(observed)) != value: raise ValueError('independent_value_contradiction_or_join_fanout')
        raw = ref.get('value')
        if not isinstance(raw, str) or len(raw) > 64: raise ValueError('invalid_claim_value')
        claimed = Decimal(raw)
        if not claimed.is_finite() or claimed != value: raise ValueError('claim_value_contradicts_evidence')
        return value, rows, source, col, m

    def verify(self, claim):
        try:
            if not isinstance(claim, dict): raise ValueError('invalid_claim_shape')
            if claim.get('kind') == 'causal':
                # Correlation and correct sums cannot prove a transformation mechanism.
                self._cell(claim)
                raise ValueError('causal_mechanism_and_accredited_classifier_version_missing')
            if claim.get('kind') == 'hypothesis_equal':
                a, b = claim['dependencies']
                av, *_ = self._measure(a)
                bv, *_ = self._measure(b)
                if av != bv:
                    raise ValueError('hypothesis_contradicted_by_observation')
                raise ValueError('hypothesis_business_meaning_not_accredited')
            if claim.get('kind') == 'share_of_universe':
                numerator, denominator = claim.get('dependencies', [None, None])
                a, subset, source, col, manifest = self._measure(numerator)
                b, population, ds, dc, dm = self._measure(denominator)
                if (source != ds or col.metric != dc.metric or manifest.snapshot != dm.snapshot
                        or len(population) != len(self.tables[source])
                        or {canonical(r) for r in population} != {canonical(r) for r in self.tables[source]}
                        or not {canonical(r) for r in subset} <= {canonical(r) for r in population}):
                    raise ValueError('incorrect_denominator_or_population')
                ratio_grain = 'document' if col.metric == 'document_count' else 'commercial_line'
                if (claim.get('metric'), claim.get('unit'), claim.get('currency'), claim.get('grain')) != ('share_of_universe', 'percent', None, ratio_grain):
                    raise ValueError('ratio_definition_mismatch')
                for key, expected in (('publication', manifest.publication), ('snapshot', manifest.snapshot),
                                      ('temporal_scope', list(manifest.temporal_scope)), ('classification', 'observed')):
                    if key in claim and claim[key] != expected:
                        raise ValueError('ratio_scope_or_classification_mismatch')
                raw = claim.get('value')
                if not isinstance(raw, str) or len(raw) > 64:
                    raise ValueError('invalid_percentage_value')
                claimed = Decimal(raw)
                if not claimed.is_finite() or claimed.as_tuple().exponent < -12:
                    raise ValueError('invalid_percentage_value')
                with localcontext() as ctx:
                    ctx.prec = 50
                    value = (a / b * 100).quantize(Decimal(1).scaleb(claimed.as_tuple().exponent), rounding=ROUND_HALF_UP)
                if claimed != value:
                    raise ValueError('percentage_contradicts_dependencies')
            elif claim.get('kind') == 'measure':
                value, *_ = self._measure(claim)
            else:
                raise ValueError('unsupported_claim_kind')
            return dict(claim=claim, state='VERIFIED_WITH_LIMITATIONS', match=True,
                        reason='independent_reference_rows_and_server_evidence_binding', limitations=LIMITS)
        except (ValueError, KeyError, TypeError, InvalidOperation, ZeroDivisionError) as exc:
            evidence = []
            refs = claim.get('dependencies', [claim]) if isinstance(claim, dict) else []
            if not isinstance(refs, list): refs = []
            for ref in refs[:2]:
                try:
                    m, _, _, row, _, _, i = self._cell(ref)
                    evidence.append(dict(result_id=m.result_id, column=asdict(m.columns[i]), row_id=ref['row_id'], observed=str(row[i])))
                except (KeyError, TypeError, ValueError):
                    pass
            return dict(claim=claim, state='UNVERIFIED', match=False, reason=str(exc)[:160], evidence=evidence,
                        required='Use issued evidence IDs and observed semantics; revise, query, or withdraw. Causality requires accredited mechanism evidence.')

    def render(self, checks):
        """Only accredited facts reach the business answer. Raw model prose is audit-only."""
        lines = ['Resultado principal: evidencia verificada de la población publicada.']
        for check in checks:
            if check['state'] != 'VERIFIED_WITH_LIMITATIONS': continue
            c = check['claim']
            if c['kind'] == 'share_of_universe':
                refs = '; '.join('/'.join(dep[k] for k in ('result_id', 'column_id', 'row_id')) for dep in c['dependencies'])
                lines.append(f"Participación del subconjunto en el universo: {c['value']} % [VERIFIED_WITH_LIMITATIONS; {refs}]")
                continue
            manifest, _, _, output, node, _, index = self._cell(c)
            group_indexes = {i for i, e in enumerate(node['select_list']) if any(clean(e) == clean(g) for g in node['group_expressions'])}
            scope = {((','.join(col.source_fields)) if col.source_or_calculation == 'SOURCE' else 'expresión calculada (' + col.alias + ')'): v
                     for i, (col, v) in enumerate(zip(manifest.columns, output)) if i in group_indexes}
            label = {'line_amount_bs': 'Importe comercial de líneas', 'line_count': 'Líneas', 'document_count': 'Documentos únicos'}[manifest.columns[index].metric]
            lines.append(f"{label}: {c['value']} {c['currency'] or c['unit']}; filtro {manifest.filter_expression}; grupo {canonical(scope)} [VERIFIED_WITH_LIMITATIONS; {c['result_id']}/{c['column_id']}/{c['row_id']}]")
        lines += ['Explicación causal: no acreditada. Las distribuciones observadas no prueban el mecanismo del clasificador.',
                  'Anomalías y limitaciones: ' + ' '.join(LIMITS),
                  'Impacto: una clasificación incompleta no demuestra ausencia ni pérdida de ventas.',
                  'Próximo paso: contrastar documentos y reglas/versiones acreditadas del clasificador antes de reclasificar.']
        return '\n'.join(lines)


def verification_feedback(checks):
    return dict(status='INDEPENDENT_VERIFICATION_DISCREPANCY',
                rejected_claims=[{k: c[k] for k in ('claim', 'state', 'match', 'reason', 'required', 'evidence')} for c in checks if not c['match']],
                instruction=('Inspect each reason: UNVERIFIED can mean missing evidence, not a numerical contradiction. '
                    'Repeating an aggregate cannot establish missing trusted source grain, provenance or business semantics. '
                    'Query only if it can supply the missing evidence within the existing authority and budget; '
                    'otherwise retain the claim as investigative or withdraw it. '
                    'For an actual value contradiction, reconsider the hypothesis. No expected business answer is supplied.'))
