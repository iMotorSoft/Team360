"""Bounded per-result raw-row checks for direct ask, not universal SQL semantics.

The reference independently recomputes measures in Python, from unaggregated
published rows. Completeness still trusts the pinned source and SQL predicate
reader. No causal, cross-result ratio, join or derived lineage accreditation.
"""
from dataclasses import asdict
import copy
import json

from .ask_sources import AskExecutor
from .claim_evidence import EvidenceRegistry, clean, evaluate
from .contracts import Decision, ExploratoryQueryProposal
from .foundation_dev import DevBudget
from .validator import canonical, digest, validate

# Ascending key orders only: an inclusive keyset bound cannot continue a DESC
# prefix or an explicit NULLS FIRST without skipping or repeating rows.
_ASCENDING_ORDERS = {'ORDER_DEFAULT', 'ASCENDING'}
_NULLS_AFTER_KEY = {'ORDER_DEFAULT', 'NULLS LAST'}


def keyset_column(node):
    """Grouped identity column that can bound the next page exactly, or None.

    This is the existing pagination contract (page by the last disclosed unique
    key), not a new resource window: it only qualifies an admitted ordering.
    """
    groups = [g for g in node.get('group_expressions') or ()]
    orders = [o for m in node.get('modifiers') or () if m.get('type') == 'ORDER_MODIFIER'
              for o in m.get('orders') or ()]
    if not groups or not orders:
        return None
    first, expression = orders[0], orders[0].get('expression') or {}
    if (first.get('type') not in _ASCENDING_ORDERS
            or first.get('null_order') not in _NULLS_AFTER_KEY
            or expression.get('class') != 'COLUMN_REF'
            or not any(clean(g) == clean(expression) for g in groups)):
        return None
    return expression['column_names'][-1]


def keyset_literal(value, sql_type):
    """Bound value as a typed literal; None refuses paging instead of guessing."""
    if value is None:
        return None
    kind = str(sql_type).upper()
    if 'CHAR' in kind or 'DATE' in kind:
        return "'" + str(value).replace("'", "''") + "'"
    if isinstance(value, bool):
        return 'true' if value else 'false'
    try:
        from decimal import Decimal
        return str(Decimal(str(value)))
    except Exception:
        return None

_COMPARE_SYMBOL = {'COMPARE_EQUAL': '=', 'COMPARE_NOTEQUAL': '≠', 'COMPARE_LESSTHAN': '<',
                   'COMPARE_GREATERTHAN': '>', 'COMPARE_LESSTHANOREQUALTO': '≤',
                   'COMPARE_GREATERTHANOREQUALTO': '≥'}


def predicate_label(expr):
    """Deterministic, non-executable scope label. Not business authority."""
    if not expr:
        return 'universo publicado accesible'
    cls = expr.get('class')
    if cls == 'COLUMN_REF':
        return expr['column_names'][-1]
    if cls == 'CONSTANT':
        return str(None if expr['value']['is_null'] else expr['value']['value'])
    if cls == 'COMPARISON':
        return (predicate_label(expr['left']) + ' '
                + _COMPARE_SYMBOL.get(expr['type'], expr['type']) + ' '
                + predicate_label(expr['right']))
    if cls == 'CONJUNCTION':
        return '(' + (' y ' if expr['type'] == 'CONJUNCTION_AND' else ' o ').join(
            predicate_label(e) for e in expr['children']) + ')'
    if cls in {'FUNCTION', 'OPERATOR', 'CASE'}:
        return compact_expression_label(expr)
    return 'filtro adicional acreditado (detalle en evidencia)'


def compact_expression_label(expr):
    """The same lineage as expression_label, written for delivery.

    Nothing is paraphrased or dropped: only the operator names of the SQL AST
    are written as their symbols, so a business list fits the channel without
    losing a figure, a condition or a provenance token.
    """
    from .claim_evidence import expression_label
    text = expression_label(expr)
    for name, symbol in _COMPARE_SYMBOL.items():
        text = text.replace(' ' + name + ' ', ' ' + symbol + ' ')
    return text


def presentation_semantics(question):
    """Family-wide inclusion is OR, not universal purchase by each account."""
    import re
    import unicodedata
    text = ''.join(c for c in unicodedata.normalize('NFD', (question or '').lower())
                   if unicodedata.category(c) != 'Mn')
    if re.search(r'cada (?:una|presentacion)|todas y cada', text):
        return 'PER_ACCOUNT_UNIVERSAL_REQUIRES_EVIDENCE'
    if re.search(r'en todas (?:sus |las )?presentaciones', text):
        return 'SKU_UNION_OR'
    return None


class AskRegistry(EvidenceRegistry):
    def __init__(self, context, *, executor_factory=AskExecutor, cancel=None):
        # Scope is publication, NOT a claim of calendar completeness.
        super().__init__(context, {}, ('published_rows', 'not_complete_calendar'))
        self.controls = executor_factory(context, authorized=True)
        self.cancel = cancel
        self.populations, self.audit = {}, []
        # Complete-population recovery: durable records plus their accounting.
        self.population_pages, self.population_recovery = {}, {}
        self.continuity_manifests = {}

    def manifests(self):
        """Export issued metadata, including durable source-derived cell contracts."""
        return [dict(asdict(entry[0]), **self.continuity_manifests.get(result_id, {}))
                for result_id, entry in self.entries.items()]

    def close(self):
        self.controls.close()

    def register(self, query, result, visible_rows):
        manifest = super().register(query, result, visible_rows)
        if manifest is None:
            return None
        entry = self.entries[manifest['result_id']]
        _, _, _, _, node, source = entry
        self._recover_population(query, node, source, result, manifest)
        from .authorized_foundation import binding_for
        if binding_for(self.context) is not None:
            # Distinguish exact execution evidence from the old metric/raw-row
            # verifier. A NULL business metric does NOT invalidate an executed
            # conditional source sum. Make that distinction visible to Luna.
            # Small source-derived contracts, not aliases or model-authored units.
            # Persist beside the existing manifest; no second result store.
            from .authorized_foundation import authorize_issued
            authorize_issued(self.context)
            manifest['continuity_cells'] = []
            for row_id in manifest['row_ids']:
                for column in manifest['columns']:
                    ref = dict(kind='executed_cell', result_id=manifest['result_id'],
                               row_id=row_id, column_id=column['column_id'])
                    try:
                        issued = self._executed_cell(ref, revalidate=False)
                        value = issued[0]
                        from decimal import Decimal
                        if not isinstance(value, Decimal):
                            continue
                        signature, predicates = self._operand_scope(ref, issued_cell=issued)
                        manifest['continuity_cells'].append(dict(reference=ref,
                            signature=signature, predicates=sorted(predicates)))
                    except (ValueError, TypeError, KeyError):
                        continue
            authorize_issued(self.context)
            self.continuity_manifests[manifest['result_id']] = dict(
                continuity_cells=manifest['continuity_cells'])
            manifest['execution_accreditation'] = (
                'executed_cell claims support direct source columns, source aggregates, and '
                'sum(CASE WHEN condition THEN original_source_amount ELSE 0 END), and '
                'min/max(CASE WHEN condition THEN original_source_column ELSE NULL END) with one WHEN. '
                'These cells remain usable when metric is null; that null concerns independent '
                'business semantics, not execution fidelity. Match WHERE/group/CASE scopes for net pairs. '
                'CTE/join/constant or invented-value expressions are NOT accredited.')
            return manifest
        if source is None or not any(c['metric'] for c in manifest['columns']):
            return manifest
        try:
            if '"class":"PARAMETER"' in canonical(node):
                raise ValueError('named_parameter_reference_not_accredited')
            table = next(t for t in self.context.catalog.tables if t.name == source)
            if not table.grain:
                raise ValueError('discovered_grain_and_business_semantics_not_accredited')
            # Native AST is data. Keep the admitted FROM/WHERE, discard model
            # projection, grouping, DISTINCT, HAVING, ordering and LIMIT. Revalidate
            # the resulting raw reference through the same positive validator.
            alias = node['from_table'].get('alias') or source
            import duckdb
            with duckdb.connect(':memory:', config={'threads': '1', 'enable_external_access': 'false'}) as db:
                raw = db.execute('SELECT json_serialize_sql(?)', [
                    'SELECT ' + ','.join(alias+'.'+c.name+' AS '+c.name for c in table.columns) + ' FROM '+source+' AS '+alias]).fetchone()[0]
                tree = json.loads(raw)
                reference = tree['statements'][0]['node']
                reference['from_table'] = copy.deepcopy(node['from_table'])
                reference['where_clause'] = copy.deepcopy(node['where_clause'])
                sql = db.execute('SELECT json_deserialize_sql(?)', [canonical(tree)]).fetchone()[0]
            p = ExploratoryQueryProposal(sql, 'independent_raw_reference',
                'Unaggregated bounded rows; never disclose reference rows to the model',
                (source,), ','.join(table.grain), 'complete filtered raw population', requested_budget=DevBudget())
            self.controls.reference_document_keys = None
            self.controls.reference_item_codes = None
            decision, reference_query = validate(p, self.context)
            decision, raw_result = self.controls.execute(p, self.context, cancel=self.cancel)
            self.audit.append(dict(result_id=manifest['result_id'], proposal=asdict(p),
                decision=asdict(decision), result=asdict(raw_result)))
            if reference_query is None or raw_result.status != 'COMPLETED' or raw_result.truncated:
                raise ValueError('independent_raw_reference_incomplete_or_blocked')
            # Same execution/context binding checks as ordinary evidence.
            EvidenceRegistry(self.context, {}, self.temporal_scope).register(reference_query, raw_result, ())
            rows = [dict(zip((c.name for c in table.columns), r)) for r in raw_result.rows]
            keys = [tuple(r[n] for n in table.grain) for r in rows]
            if any(None in k for k in keys) or len(keys) != len(set(keys)):
                raise ValueError('reference_duplicate_or_null_grain_join_fanout')
            if source in {'sales_operation', 'sales_line'} and any(
                    r['raw_extraction_id'] is None or r['source_as_of'] is None for r in rows):
                raise ValueError('reference_missing_provenance')
            if source in {'sales_operation', 'sales_line'}:
                self._reconcile_raw_keys(source, rows, node, manifest['result_id'])
            self.populations[manifest['result_id']] = {source: rows}
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            self.audit.append(dict(result_id=manifest['result_id'], reason=str(exc)[:160], state='UNVERIFIED'))
        return manifest

    @staticmethod
    def _scope_projection(node):
        """Everything except the keyset bound and the page window must be identical."""
        value = clean({k: v for k, v in node.items() if k not in {'where_clause', 'modifiers'}})
        orders = [m for m in node.get('modifiers') or () if m.get('type') == 'ORDER_MODIFIER']
        return canonical(dict(value, orders=clean(orders)))

    @staticmethod
    def _flat(expr):
        """DuckDB serialization flattens nested AND; compare the same shape."""
        if isinstance(expr, list):
            return [AskRegistry._flat(v) for v in expr]
        if not isinstance(expr, dict):
            return expr
        value = {k: AskRegistry._flat(v) for k, v in expr.items()}
        if value.get('class') == 'CONJUNCTION' and value.get('type') == 'CONJUNCTION_AND':
            children = []
            for child in value.get('children') or ():
                if child.get('class') == 'CONJUNCTION' and child.get('type') == 'CONJUNCTION_AND':
                    children.extend(child.get('children') or ())
                else:
                    children.append(child)
            value['children'] = children
        return value

    @staticmethod
    def _keyset_sql(query, key, literal):
        """Same admitted statement with an inclusive keyset bound and no LIMIT.

        The tree round-trip is verified before use; any reconstruction doubt
        returns None so the caller fails closed instead of paging a guess.
        """
        import duckdb
        candidate = json.loads(query.admitted_tree_json)
        node = candidate['statements'][0]['node']
        node['modifiers'] = [m for m in node.get('modifiers') or ()
                             if m.get('type') != 'LIMIT_MODIFIER']
        table = node['from_table'].get('table_name') or 'page_scope'
        try:
            with duckdb.connect(':memory:', config={'threads': '1',
                                                    'enable_external_access': 'false'}) as db:
                def parsed(sql):
                    tree = json.loads(db.execute('SELECT json_serialize_sql(?)', [sql]).fetchone()[0])
                    return tree['statements'][0]['node']
                shape = parsed('SELECT 1 AS one FROM ' + table + ' WHERE 1=1 AND 1=1')['where_clause']
                keyset = parsed('SELECT 1 AS one FROM ' + table + ' WHERE '
                                + key + ' >= ' + literal)['where_clause']
                predicate = keyset
                if node.get('where_clause') is not None:
                    shape['children'] = [node['where_clause'], keyset]
                    predicate = shape
                node['where_clause'] = predicate
                sql = db.execute('SELECT json_deserialize_sql(?)', [canonical(candidate)]).fetchone()[0]
                if (canonical(AskRegistry._flat(clean(parsed(sql)['where_clause'])))
                        != canonical(AskRegistry._flat(clean(predicate)))):
                    return None
                return sql
        except Exception:
            return None

    def _recover_population(self, query, node, source, result, manifest):
        """Recover the whole grouped population with the existing keyset paging.

        A page-sized prefix (SQL LIMIT or the executor fetch window) is not the
        population. The controller continues the SAME admitted scope in ordinary
        authorized pages, merging each record once, instead of raising the row
        budget or asking the model to repeat the list. Incomplete recovery stays
        incomplete and is never presented as a durable population.
        """
        key = keyset_column(node)
        tables = {t.name for t in self.context.catalog.tables}
        simple = (source in tables and node['from_table'].get('type') == 'BASE_TABLE'
                  and not node['cte_map']['map'])
        limit = self.context.effective_budget.result_rows
        declared_limit = any(m.get('type') == 'LIMIT_MODIFIER' for m in node.get('modifiers') or ())
        if key is None or not simple or not result.rows or manifest is None:
            return
        if not declared_limit and len(result.rows) < limit and not result.truncated:
            return  # Read to the end of the population inside the row budget.
        groups = [g for g in node['group_expressions']]
        group_indexes = [i for i, expr in enumerate(node['select_list'])
                         if any(clean(expr) == clean(g) for g in groups)]
        key_index = next((i for i, expr in enumerate(node['select_list'])
                          if expr.get('class') == 'COLUMN_REF' and any(
                              expr['column_names'][-1] == key
                              and clean(expr) == clean(g) for g in groups)), None)
        if key_index is None or not group_indexes:
            return
        sql_type = result.schema[key_index].sql_type
        recovered = [tuple(row) for row in result.rows]
        seen = {tuple(row[i] for i in group_indexes) for row in recovered}
        pages, complete, reason = [], False, None
        saved = (getattr(self.controls, 'reference_document_keys', None),
                 getattr(self.controls, 'reference_item_codes', None))
        self.controls.reference_document_keys = self.controls.reference_item_codes = None
        try:
            for _ in range(self.context.effective_budget.queries):
                literal = keyset_literal(recovered[-1][key_index], sql_type)
                if literal is None:
                    reason = 'keyset_value_not_pageable'
                    break
                sql = self._keyset_sql(query, key, literal)
                if sql is None:
                    reason = 'keyset_sql_not_reconstructable'
                    break
                p = ExploratoryQueryProposal(sql,
                    'Página de continuación del mismo listado agrupado autorizado',
                    'Paginación por clave sobre el mismo alcance ya admitido; sin cambio de filtros, medidas ni permisos',
                    (source,), str(manifest.get('grain') or 'filas agrupadas del alcance'),
                    'siguiente página del mismo universo ordenado', requested_budget=DevBudget())
                try:
                    decision, page_query = validate(p, self.context)
                except ValueError:
                    reason = 'continuation_not_admitted'
                    break
                if page_query is None or decision.decision is not Decision.ALLOW:
                    reason = 'continuation_not_admitted'
                    break
                page_node = json.loads(page_query.admitted_tree_json)['statements'][0]['node']
                if self._scope_projection(page_node) != self._scope_projection(node):
                    reason = 'continuation_scope_changed'
                    break
                decision, page = self.controls.execute(p, self.context, cancel=self.cancel)
                self.audit.append(dict(result_id=manifest['result_id'], population_page=len(pages) + 1,
                    keyset=dict(column=key, inclusive_lower_bound=literal), proposal=asdict(p),
                    decision=asdict(decision), result=asdict(page)))
                if page.status != 'COMPLETED':
                    reason = 'continuation_not_completed'
                    break
                if [c.name for c in page.schema] != [c.name for c in result.schema]:
                    reason = 'continuation_schema_changed'
                    break
                fresh = [tuple(row) for row in page.rows
                         if tuple(row[i] for i in group_indexes) not in seen]
                if not fresh:
                    # The inclusive bound repeats the boundary record; no new
                    # records exist after it, so the population is exhausted.
                    complete = not page.truncated
                    if not complete:
                        reason = 'keyset_page_without_progress'
                    break
                seen.update(tuple(row[i] for i in group_indexes) for row in fresh)
                recovered.extend(fresh)
                pages.append(dict(query_id=page.query_id, page=len(pages) + 1,
                    schema=[asdict(c) for c in page.schema], rows=[list(row) for row in fresh],
                    truncated=page.truncated, status=page.status))
                if not page.truncated:
                    complete = True
                    break
            else:
                reason = 'page_budget_reached'
        finally:
            self.controls.reference_document_keys, self.controls.reference_item_codes = saved
        entity = next((i for i, expr in enumerate(node['select_list'])
                       if expr.get('class') == 'COLUMN_REF'
                       and expr['column_names'][-1] in {'card_code', 'item_code'}), None)
        recovery = dict(complete=complete, recovered_records=len(recovered), pages=len(pages),
            first_page_records=len(result.rows),
            entity_column=None if entity is None else node['select_list'][entity]['column_names'][-1],
            distinct_entities=None if entity is None else len({row[entity] for row in recovered}),
            reason=reason,
            protocol=('Controlador: paginación por clave del MISMO alcance admitido; '
                      'no se elevó el presupuesto de filas, consultas ni permisos.'))
        manifest['population_recovery'] = recovery
        self.population_recovery[manifest['result_id']] = recovery
        if complete:
            self.population_pages[manifest['result_id']] = pages

    def _raw_reference(self, source, document_keys, result_id):
        table = next(t for t in self.context.catalog.tables if t.name == source)
        # Server-issued keys are bound as DATA to private temporary tables by
        # trusted connection setup, never inserted into model SQL or Foundation.
        self.controls.reference_document_keys = document_keys
        scope_digest = digest((sorted(document_keys), sorted(self.controls.reference_item_codes or ())))
        sql = 'SELECT '+','.join(c.name for c in table.columns)+' FROM '+source
        p = ExploratoryQueryProposal(sql, 'independent_documentary_keys',
            'Raw header/line reconstruction, never the investigative operation join',
            (source,), ','.join(table.grain)+':scope:'+scope_digest,
            'complete bounded raw documentary rows', requested_budget=DevBudget())
        _, query = validate(p, self.context)
        decision, result = self.controls.execute(p, self.context, cancel=self.cancel)
        self.audit.append(dict(result_id=result_id, reference_scope_digest=scope_digest,
            document_keys=sorted(document_keys), item_codes=sorted(self.controls.reference_item_codes or ()),
            proposal=asdict(p), decision=asdict(decision), result=asdict(result)))
        if query is None or result.status != 'COMPLETED' or result.truncated:
            raise ValueError('raw_documentary_reference_incomplete_or_budget_blocked')
        EvidenceRegistry(self.context, {}, self.temporal_scope).register(query, result, ())
        rows = [dict(zip((c.name for c in table.columns), r)) for r in result.rows]
        keys = [tuple(r[n] for n in table.grain) for r in rows]
        if any(None in k for k in keys) or len(keys) != len(set(keys)):
            raise ValueError('raw_documentary_duplicate_or_null_key')
        return rows

    def _reconcile_raw_keys(self, source, rows, node, result_id):
        if not rows:
            return
        document_keys = {r['doc_entry'] for r in rows}
        self.controls.reference_item_codes = {r['item_code'] for r in rows}
        docs = self._raw_reference('sales_document', document_keys, result_id)
        lines = self._raw_reference('sales_line', document_keys, result_id)
        headers = {r['doc_entry']: r for r in docs}
        if set(headers) != document_keys:
            raise ValueError('raw_header_coverage_mismatch')
        reconstructed = []
        fields = next(t.columns for t in self.context.catalog.tables if t.name == source)
        for line in lines:
            header = headers[line['doc_entry']]
            if any(header[k] is None or header[k] != line[k] for k in ('currency', 'raw_extraction_id', 'source_as_of')):
                raise ValueError('raw_header_line_currency_or_provenance_mismatch')
            combined = (header | line) if source == 'sales_operation' else line
            if evaluate(node['where_clause'], combined, {}) is True:
                reconstructed.append({c.name: combined[c.name] for c in fields})
        if sorted(map(canonical, reconstructed)) != sorted(map(canonical, rows)):
            raise ValueError('raw_operation_population_or_join_multiplication_mismatch')

    def _measure(self, ref):
        result_id = ref.get('result_id') if isinstance(ref, dict) else None
        if result_id not in self.populations:
            # Preserve the actual control failure. A missing source contract is
            # not a numerical contradiction and cannot be repaired by another SUM.
            failure = next((a['reason'] for a in reversed(self.audit)
                if a.get('result_id') == result_id and a.get('state') == 'UNVERIFIED'), None)
            raise ValueError(failure or 'independent_raw_population_or_semantics_not_accredited')
        self.tables = self.populations[result_id]
        return super()._measure(ref)

    def _executed_cell(self, ref, *, revalidate=True):
        from .authorized_foundation import authorize_issued
        if revalidate:
            authorize_issued(self.context)
        from decimal import Decimal
        m, q, result, row, node, source, index = self._cell(ref)
        if result.truncated:
            raise ValueError('truncated_result_not_final_evidence')
        if source is None or node['cte_map']['map']:
            raise ValueError('derived_or_join_lineage_not_accredited')
        expr = node['select_list'][index]
        field = expr if expr.get('class') == 'COLUMN_REF' else (
            expr.get('children', [None])[0] if len(expr.get('children', [])) == 1 else None)
        aggregate = expr.get('class') == 'FUNCTION' and expr.get('function_name') in {'sum','count','count_star','min','max','avg'}
        if aggregate and expr.get('function_name') in {'sum', 'min', 'max', 'count'} and field and field.get('class') == 'CASE':
            cases = field.get('case_checks', [])
            default = field.get('else_expr', {})
            identity_default = (default.get('value', {}).get('value') == 0
                                and not default.get('value', {}).get('is_null')) if expr['function_name'] == 'sum' else (
                                    default.get('value', {}).get('is_null') is True)
            if len(cases) == 1 and default.get('class') == 'CONSTANT' and identity_default:
                field = cases[0]['then_expr']
        if not (field and field.get('class') == 'COLUMN_REF') and not (aggregate and expr.get('function_name') == 'count_star'):
            raise ValueError('direct_source_cell_or_aggregate_required')
        if expr.get('class') != 'COLUMN_REF' and not aggregate:
            raise ValueError('unaccredited_cell_calculation')
        value = row[index]
        if any(t in m.columns[index].sql_type for t in ('INT', 'DECIMAL', 'DOUBLE', 'FLOAT')):
            if isinstance(value, bool) or value is None:
                raise ValueError('numeric_executed_cell_required')
            value = Decimal(str(value))
            if not value.is_finite():
                raise ValueError('finite_executed_cell_required')
        elif m.columns[index].sql_type in {'DATE', 'TIMESTAMP'}:
            from datetime import date, datetime
            expected = datetime if m.columns[index].sql_type == 'TIMESTAMP' else date
            if value is not None:
                # datetime subclasses date; a timestamp must not silently lose
                # its time. Strings cannot acquire temporal authority by format.
                if type(value) is not expected:
                    raise ValueError('typed_temporal_executed_cell_required')
                value = value.isoformat()
        elif not isinstance(value, (str, bool, type(None))):
            raise ValueError('scalar_executed_cell_required')
        return value, (m, node, source, index, row)

    def _calculation_signature(self, claim, *, issued_cell=None):
        """Distinguish a measure from its delta; arithmetic fidelity is not intent."""
        if claim.get('kind') == 'executed_cell':
            _, (_, node, source, index, _) = issued_cell or self._executed_cell(claim)
            expr = node['select_list'][index]
            argument = expr.get('children', [{}])[0] if expr.get('children') else expr
            if argument.get('class') == 'CASE':
                argument = argument['case_checks'][0]['then_expr']
            return ('source_metric', source, expr.get('function_name'), tuple(argument.get('column_names', [])[-1:]), bool(expr.get('distinct')))
        deps = claim['dependencies']
        if claim['operation'] == 'subtract' and all(d.get('kind') == 'executed_cell' for d in deps):
            try:
                a, b = map(self._document_scope, deps)
                if a[0] == 'sales_document' and b[0] == 'credit_memo_document' and a[1] == b[1]:
                    return ('net_document',)
            except ValueError:
                pass
        return (claim['operation'], *(self._calculation_signature(d) for d in deps))

    def requested_scope(self):
        """Requested shape of the answer, beyond the quantitative operations."""
        return {'period_separation'} if self.requires_period_separation() else set()

    def requires_period_separation(self):
        """The question wants each period's value, not one merged figure.

        Generic intent guidance: it never grants scope, never replaces evidence
        and never names a month, a channel or a measure.
        """
        import re
        import unicodedata
        question = ''.join(c for c in unicodedata.normalize('NFD', getattr(self, 'question', '').lower())
                           if unicodedata.category(c) != 'Mn')
        pattern = (r'\bpor separado\b|\bseparad[oa]s?\b|\bcada mes\b|\bmes a mes\b|\bmes por mes\b|'
                   r'\bpor mes\b|\bpor cada mes\b|\bdesglos\w*\b|\bindividualmente\b|\buno por mes\b')
        for clause in re.split(r'[.;!?\n]|\bpero\b', question):
            for hit in re.finditer(pattern, clause):
                if not re.search(r'\b(?:no|sin|evitar)\b[^,]*$', clause[:hit.start()]):
                    return True
        return False

    def _manifests_of(self, claim):
        """Evidence manifests a verified claim is bound to (never inferred)."""
        if claim.get('kind') == 'executed_cell':
            return [self._executed_cell(claim)[1][0]]
        found = []
        for dependency in claim.get('dependencies') or []:
            if isinstance(dependency, dict):
                found.extend(self._manifests_of(dependency))
        return found

    def requested_calculations(self):
        """Extend the existing verifier's question-intent checks, not a router.

        Intent is guidance only; every operand still needs issued, authorized
        evidence. Negative clauses do not create a requested operation.
        """
        import re
        import unicodedata
        question = ''.join(c for c in unicodedata.normalize('NFD', getattr(self, 'question', '').lower())
                           if unicodedata.category(c) != 'Mn')
        patterns = {
            'share': r'\bparticipacion\b|\bque (?:parte|porcentaje)\b|\bque proporcion\b(?! entre\b)|\bproporcion de\b|\bporcentaje (?:del|sobre|de las|de los)\b',
            'percent_change': r'\bvariacion\b|\bcrecimiento\b|\bcambio porcentual\b|\baumento porcentual\b',
            'subtract': r'\bdiferencia absoluta\b|\bresta\b',
            'ratio': r'\bratio\b|\bproporcion entre\b|\brazon entre\b',
        }
        requested = set()
        for clause in re.split(r'[.;!?\n]|\bpero\b', question):
            for operation, pattern in patterns.items():
                for hit in re.finditer(pattern, clause):
                    if not re.search(r'\b(?:no|sin|evitar)\b[^,]*$', clause[:hit.start()]):
                        requested.add(operation)
        return requested

    def _operand_scope(self, claim, *, issued_cell=None):
        """Comparable metric and exact conjunctive scope from admitted AST/data.

        Unknown boolean shapes fail closed for subset accreditation; aliases and
        model-authored descriptions are never a population/measure contract.
        """
        from .claim_evidence import clean
        if claim.get('kind') != 'executed_cell':
            raise ValueError('direct_operands_required_for_subset_accreditation')
        issued = issued_cell or self._executed_cell(claim)
        _, (_, node, source, index, row) = issued
        expr = node['select_list'][index]
        def normalized(value):
            if isinstance(value, dict):
                return {k: ([v[-1]] if k == 'column_names' else normalized(v)) for k, v in clean(value).items()}
            if isinstance(value, list): return [normalized(v) for v in value]
            return value
        def atoms(value):
            if value is None: return set()
            if value.get('type') == 'CONJUNCTION_AND':
                return set().union(*(atoms(v) for v in value['children']))
            if value.get('class') not in {'COMPARISON', 'OPERATOR'}:
                raise ValueError('conjunctive_population_scope_required')
            if value.get('class') == 'OPERATOR' and value.get('type') not in {'OPERATOR_IS_NULL', 'OPERATOR_IS_NOT_NULL'}:
                raise ValueError('conjunctive_population_scope_required')
            return {canonical(normalized(value))}
        predicates = atoms(node.get('where_clause'))
        argument = expr.get('children', [{}])[0] if expr.get('children') else expr
        if argument.get('class') == 'CASE':
            predicates |= atoms(argument['case_checks'][0]['when_expr'])
        for group in node['group_expressions']:
            indexes = [i for i,e in enumerate(node['select_list']) if clean(e) == clean(group)]
            if len(indexes) != 1: raise ValueError('group_not_bound')
            predicates.add(canonical(dict(group=normalized(group), value=row[indexes[0]])))
        return self._calculation_signature(claim, issued_cell=issued), predicates

    def _calculation(self, claim, depth=0):
        from decimal import Decimal
        if depth > 3 or not isinstance(claim, dict):
            raise ValueError('bounded_calculation_required')
        if claim.get('kind') == 'executed_cell':
            return self._executed_cell(claim)[0]
        if claim.get('kind') != 'calculation':
            raise ValueError('unsupported_execution_claim')
        if claim.get('operation') not in {'subtract', 'percent_change', 'share', 'ratio'}:
            raise ValueError('unsupported_calculation')
        dependencies = claim.get('dependencies')
        if not isinstance(dependencies, list) or len(dependencies) != 2:
            raise ValueError('two_evidence_dependencies_required')
        a, b = (self._calculation(d, depth+1) for d in dependencies)
        if not isinstance(a, Decimal) or not isinstance(b, Decimal):
            raise ValueError('numeric_calculation_dependencies_required')
        net_pair = False
        if claim.get('operation') == 'subtract' and all(d.get('kind') == 'executed_cell' for d in dependencies):
            sources = [self._executed_cell(d)[1][2] for d in dependencies]
            if sources == ['sales_document', 'credit_memo_document']:
                if self._document_scope(dependencies[0])[1] != self._document_scope(dependencies[1])[1]:
                    raise ValueError('net_document_scopes_must_match')
                net_pair = True
        signatures = [self._calculation_signature(d) for d in dependencies]
        scopes = ([self._operand_scope(d)[1] for d in dependencies]
                  if not net_pair and all(d.get('kind') == 'executed_cell' for d in dependencies) else None)
        return self.calculate_pair(claim.get('operation'), a, b, signatures, scopes, net_pair=net_pair)

    @staticmethod
    def calculate_pair(operation, a, b, signatures, scopes, *, net_pair=False):
        """Same business checks for live cells and authorized durable references."""
        from decimal import Decimal, localcontext, ROUND_HALF_UP
        if not all(isinstance(v, Decimal) and v.is_finite() for v in (a, b)):
            raise ValueError('finite_numeric_operands_required')
        if operation in {'subtract', 'absolute_difference', 'add'} and not net_pair:
            if canonical(signatures[0]) != canonical(signatures[1]):
                raise ValueError('difference_requires_compatible_measures')
        if scopes is not None and not net_pair:
            units = [{p for p in predicates if any('"' + key + '"' in p
                for key in ('currency', 'unit', 'uom', 'inventory_uom_id'))} for predicates in scopes]
            if units[0] != units[1]:
                raise ValueError('calculation_units_or_currency_scope_mismatch')
        with localcontext() as ctx:
            ctx.prec = 50
            if operation == 'subtract':
                return a-b
            if operation == 'absolute_difference':
                return abs(a-b)
            if operation == 'add':
                return a+b
            if operation in {'percent_change', 'share', 'ratio'}:
                if canonical(signatures[0]) != canonical(signatures[1]):
                    raise ValueError('percent_change_requires_comparable_measures_not_delta_and_base')
                if b == 0:
                    raise ValueError('nonzero_denominator_required')
                if operation == 'share':
                    signature = signatures[0]
                    if signature[0] != 'source_metric' or signature[2] not in {'sum', 'count', 'count_star'}:
                        raise ValueError('additive_part_and_total_required')
                    if scopes is None:
                        raise ValueError('direct_operands_required_for_subset_accreditation')
                    numerator, denominator = scopes
                    if not denominator <= numerator:
                        raise ValueError('share_requires_part_within_same_scoped_total')
                    if b <= 0 or a < 0 or a > b:
                        raise ValueError('share_requires_nonnegative_part_and_positive_total')
                    return (a/b*100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if operation == 'ratio':
                    return a/b
                return ((a-b)/b*100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        raise ValueError('unsupported_calculation')

    def _execution_claim(self, claim):
        from decimal import Decimal, InvalidOperation
        try:
            requested = self.requested_calculations()
            if (claim.get('kind') == 'calculation' and requested
                    and claim.get('operation') not in requested):
                # Net subtraction may remain a component, not a substitute for
                # the requested top-level share/change/ratio/difference.
                raise ValueError('calculation_does_not_answer_requested_operation')
            value = self._calculation(claim)
            # Values are optional assertions, never the delivered source of truth.
            if 'value' in claim and (not isinstance(claim['value'], str)
                    or (Decimal(claim['value']) if isinstance(value, Decimal) else claim['value']) != value):
                raise ValueError('claim_value_contradicts_executor')
            evidence = []
            if claim.get('kind') == 'executed_cell':
                _, (m, node, source, index, _) = self._executed_cell(claim)
                if m.columns[index].sql_type in {'DATE', 'TIMESTAMP'}:
                    evidence.append(dict(value=value, sql_type=m.columns[index].sql_type,
                        source=source, column=asdict(m.columns[index]),
                        publication=m.publication, snapshot=m.snapshot,
                        temporal_scope=m.temporal_scope, filter_expression=m.filter_expression,
                        limitations=m.limitations))
            return dict(claim=claim, state='EXECUTOR_OBSERVED_WITH_LIMITATIONS', match=True,
                value=str(value), evidence=evidence,
                reason='exact_executor_cells_and_decimal_arithmetic_not_independent_source_reconstruction')
        except (ValueError, KeyError, TypeError, InvalidOperation, ZeroDivisionError) as exc:
            return dict(claim=claim, state='UNVERIFIED', match=False, reason=str(exc), evidence=[],
                required='Correct evidence IDs or obtain additional evidence; never transcribe unsupported figures.')

    def _document_scope(self, ref):
        from .claim_evidence import clean
        _, node, source, index, row = self._executed_cell(ref)[1]
        expression = clean(node['select_list'][index])
        if expression.get('function_name') != 'sum' or len(expression.get('children', [])) != 1:
            raise ValueError('net_requires_document_sums')
        argument = expression['children'][0]
        cell_predicate = None
        if argument.get('class') == 'CASE':
            cases, default = argument.get('case_checks', []), argument.get('else_expr', {})
            if len(cases) != 1 or default.get('class') != 'CONSTANT' or default.get('value', {}).get('value') != 0:
                raise ValueError('net_requires_identity_conditional_sum')
            cell_predicate, argument = cases[0]['when_expr'], cases[0]['then_expr']
        if argument.get('class') != 'COLUMN_REF' or argument.get('column_names', [])[-1:] != ['doc_total']:
            raise ValueError('net_requires_document_sums')
        def normalize(value):
            if isinstance(value, dict):
                return {k: ([v[-1]] if k == 'column_names' else normalize(v)) for k,v in clean(value).items()}
            if isinstance(value, list): return [normalize(v) for v in value]
            return value
        groups = []
        for g in node['group_expressions']:
            indexes = [i for i,e in enumerate(node['select_list']) if clean(e) == clean(g)]
            if len(indexes) != 1: raise ValueError('group_not_bound')
            groups.append((normalize(g), row[indexes[0]]))
        return source, canonical((normalize(node['where_clause']), groups, normalize(cell_predicate)))

    def final_feedback(self, claims, *, net_required=False):
        """Model labels cannot replace comparable invoice/credit evidence."""
        requested = self.requested_calculations()
        present = {c.get('operation') for c in claims if c.get('kind') == 'calculation'
                   and self._execution_claim(c).get('match')}
        if claims and requested - present:
            return ('Requested quantitative operations still missing: ' + ', '.join(sorted(requested - present))
                    + '. share=part/total*100; percent_change=(current-base)/base*100; '
                    'subtract=current-base; ratio=numerator/denominator. Reuse issued cells; '
                    'do not re-query already observed components or substitute one operation for another.')
        if claims and self.requires_period_separation():
            # A consolidated value is not a per-period answer: the figure must be
            # bound to its own observed scope, never to the merged window only.
            scopes = set()
            for claim in claims:
                if not isinstance(claim, dict) or claim.get('kind') not in {'executed_cell', 'calculation'}:
                    continue
                if not self.verify(claim).get('match'):
                    continue
                for manifest in self._manifests_of(claim):
                    # The executed scope of the evidence: publication window plus the
                    # query's own filter. A merged query has one scope, never two.
                    scopes.add(canonical([list(str(value) for value in manifest.temporal_scope),
                                          manifest.filter_expression]))
            if len(scopes) < 2:
                return ('The question asks for each period shown separately. Bind every figure to its own '
                        'period (one aggregate per period, or GROUP BY the period) and submit those cells. '
                        'One consolidated value over the merged window does not answer a per-period request, '
                        'and the merged total must not be presented as the periods.')
        def net_pair(claim):
            if claim.get('kind') == 'calculation':
                deps = claim.get('dependencies', [])
                if claim.get('operation') == 'subtract' and len(deps) == 2 and all(d.get('kind') == 'executed_cell' for d in deps):
                    try:
                        a, b = map(self._document_scope, deps)
                        return a[0] == 'sales_document' and b[0] == 'credit_memo_document' and a[1] == b[1]
                    except (ValueError, KeyError, TypeError): return False
            return any(net_pair(d) for d in claim.get('dependencies', []) if isinstance(d, dict))
        import re
        import unicodedata
        question = ''.join(c for c in unicodedata.normalize('NFD', getattr(self, 'question', '').lower())
                           if unicodedata.category(c) != 'Mn')
        account_nodes = [entry[4] for entry in self.entries.values()
                         if any(g.get('class') == 'COLUMN_REF' and g['column_names'][-1] == 'card_code'
                                for g in entry[4].get('group_expressions', []))]
        if account_nodes:
            node = account_nodes[-1]
            having = node.get('having') or node.get('having_clause')
            def walk(value):
                if isinstance(value, dict):
                    yield value
                    for child in value.values():
                        yield from walk(child)
                elif isinstance(value, list):
                    for child in value:
                        yield from walk(child)
            if (presentation_semantics(question) == 'SKU_UNION_OR'
                    and (any(e.get('function_name') == 'count' and e.get('distinct')
                             and any(c.get('column_names', [''])[-1] == 'item_code'
                                     for c in walk(e)) for e in walk(having))
                         or sum(e.get('function_name') == 'count'
                                and any(c.get('class') == 'CASE' for c in walk(e))
                                and any(c.get('column_names', [''])[-1] == 'item_code'
                                        for c in walk(e)) for e in walk(having)) > 1)
                    # The correction is already materialised when a complete
                    # account population of that OR universe was recovered.
                    and not self._has_recovered_account_population()):
                return ('All presentations expands the SKU universe with OR; the question does not require '
                        'each account to buy every SKU. Remove per-account HAVING count(DISTINCT item_code)=family_size; '
                        'retrieve accounts over the complete selected SKU universe in ONE list ordered by the '
                        'account key. The controller recovers and counts that whole population '
                        '(population_recovery), so do not spend a second query on a separate distinct-account count.')
            aliases = {e.get('alias'): e for e in node.get('select_list', []) if e.get('alias')}
            def zero_aggregate(function):
                for e in walk(having):
                    if e.get('class') != 'COMPARISON' or e.get('type') != 'COMPARE_EQUAL':
                        continue
                    for value, zero in ((e['left'], e['right']), (e['right'], e['left'])):
                        if value.get('class') == 'COLUMN_REF':
                            value = aliases.get(value['column_names'][-1], value)
                        if (value.get('function_name') in function and zero.get('class') == 'CONSTANT'
                                and not zero['value']['is_null'] and str(zero['value']['value']) in {'0', '0.0'}):
                            return True
                return False
            if (re.search(r'pero no|no en|sin compras|no compr', question)
                    and zero_aggregate({'sum'}) and not zero_aggregate({'count', 'count_star'})):
                return ('Zero monetary SUM is not documentary absence: zero-valued/offsetting purchases exist. '
                        'Use documentary COUNT=0 in HAVING for the excluded period under the same SKU universe, '
                        'and select the counts as existence evidence. Do not finalize an amount-only anti-purchase predicate.')
        if not claims:
            # A complete recovered population keeps its tail in the durable
            # result: repeating or paging the list with more SQL is waste, and
            # describing it as an unrecovered sample would be false. Guidance
            # only, never an extra execution or a rejected final.
            for result_id, recovery in getattr(self, 'population_recovery', {}).items():
                if recovery.get('complete') and recovery.get('pages'):
                    return ('The controller already recovered the complete population of the last grouped '
                            'list (' + str(recovery['recovered_records']) + ' records in '
                            + str(recovery['pages']) + ' bounded keyset pages of the same authorized scope). '
                            'Do NOT page it again and do NOT call it a non-exhaustive sample. Select the '
                            'identity/measure cells of that result, plus the same-filter distinct count if '
                            'the question asks how many, and state that the remaining rows are a local '
                            'presentation page of a fully recovered universe.')
        if net_required and not any(net_pair(c) for c in claims if isinstance(c, dict)):
            return 'Net requested/inherited: obtain matching invoice AND credit memo document sums for each period/filter; submit their subtraction. Invoice-only evidence is incomplete.'
        return None

    def _has_recovered_account_population(self):
        """A complete, paged account population without a per-account HAVING exists.

        That is exactly the OR correction the scope rule asks for, already
        materialised in recovered evidence, so the final is not contradicted.
        """
        for result_id, recovery in getattr(self, 'population_recovery', {}).items():
            entry = self.entries.get(result_id)
            if not entry or not (recovery.get('complete') and recovery.get('pages')):
                continue
            node = entry[4]
            if not any(group.get('class') == 'COLUMN_REF'
                       and group['column_names'][-1] == 'card_code'
                       for group in node.get('group_expressions') or ()):
                continue
            if not (node.get('having') or node.get('having_clause')):
                return True
        return False

    def verify(self, claim):
        from .authorized_foundation import binding_for
        if binding_for(self.context) is not None and isinstance(claim, dict) and claim.get('kind') in {'executed_cell', 'calculation'}:
            return self._execution_claim(claim)
        if isinstance(claim, dict) and claim.get('kind') == 'share_of_universe':
            # Filtered reference populations must never impersonate an entire
            # authorized universe. No ratio accreditation in this first runner.
            return dict(claim=claim, state='UNVERIFIED', match=False,
                reason='cross_result_denominator_universe_not_accredited', evidence=[],
                required='Withdraw the ratio; report independently checked component figures.')
        return super().verify(claim)

    def _render_executed(self, checks):
        """Deliver every accredited figure without repeating the shared scope.

        The executed scope is identical for every cell of one query, so it is
        stated once instead of once per cell: that repetition was what pushed a
        complete list past the channel limit. One line per executed row keeps the
        whole population visible; figures, groups, conditions and provenance are
        never altered. The unabridged evidence stays in the private audit.
        """
        from decimal import Decimal
        from .claim_evidence import expression_label, clean
        def number(value):
            d = Decimal(str(value))
            places = max(2, -d.normalize().as_tuple().exponent)
            return format(d, f',.{places}f').replace(',', '_').replace('.', ',').replace('_', '.')
        filters, rows, derived, rankings = [], {}, [], {}
        result_scopes = {}
        field_labels = {}
        account_scope = set()
        shared_names = {}

        def scope_text(node):
            text = predicate_label(node['where_clause'])
            having = node.get('having') or node.get('having_clause')
            return text + ('; condición sobre grupos: ' + predicate_label(having) if having else '')

        def ranking_text(ref):
            value, (m, node, source, index, row) = self._executed_cell(ref)
            groups = node['group_expressions']
            for group in groups:
                if group.get('class') == 'COLUMN_REF':
                    account_scope.add(group['column_names'][-1])
            orders = [order for mod in node['modifiers'] if mod['type'] == 'ORDER_MODIFIER'
                      for order in mod['orders']]
            limits = [mod for mod in node['modifiers'] if mod['type'] == 'LIMIT_MODIFIER']
            # A prefix with an offset, HAVING, derived lineage or an unrelated
            # primary ordering cannot establish the leader of the WHERE universe.
            if (not groups or not orders or orders[0]['type'] != 'DESCENDING'
                    or node.get('having') or node.get('having_clause')
                    or any(mod.get('offset') is not None for mod in limits)):
                return
            expression = node['select_list'][index]
            order = orders[0]['expression']
            same = clean(order) == clean(expression)
            same = same or (order.get('class') == 'COLUMN_REF'
                            and order.get('column_names') == [m.columns[index].alias])
            arguments = expression.get('children', [])
            measure = (arguments[0].get('column_names', [''])[-1]
                       if len(arguments) == 1 and arguments[0].get('class') == 'COLUMN_REF' else None)
            if (not same or expression.get('class') != 'FUNCTION'
                    or expression.get('function_name') != 'sum'
                    or measure not in {'line_total', 'doc_total', 'quantity'}):
                return
            entry = self.entries[ref['result_id']]
            # Documentary quantities from different SKUs/units cannot establish
            # a global physical leader, even when the SQL ORDER BY is valid.
            if measure == 'quantity':
                physical = [i for i, e in enumerate(node['select_list'])
                            if e.get('class') == 'COLUMN_REF' and e['column_names'][-1]
                            in {'item_code', 'product_name', 'inventory_uom_id', 'unit', 'uom'}]
                if physical and len({tuple(r[i] for i in physical) for r in entry[3]}) > 1:
                    rankings[ref['result_id']] = (
                        'Cantidades por presentación: no hay un líder físico global acreditado. '
                        'Este orden mezcla SKU/unidades; hace falta un ranking independiente por presentación.')
                    return
            identity_columns = {e['column_names'][-1]: i for i, e in enumerate(node['select_list'])
                                if e.get('class') == 'COLUMN_REF'
                                and any(clean(e) == clean(g) for g in groups)}
            if {'card_code', 'customer_name'} <= identity_columns.keys():
                for observed in entry[3]:
                    name = observed[identity_columns['customer_name']]
                    code = observed[identity_columns['card_code']]
                    if name is not None and code is not None:
                        shared_names.setdefault(str(name), set()).add(str(code))
            if not entry[3] or tuple(row) != tuple(entry[3][0]):
                return
            names = [f'{expression_label(g)}={row[i]}' for g in groups
                     for i, e in enumerate(node['select_list']) if clean(e) == clean(g)]
            criterion = {'line_total': 'importe comercial de líneas (antes de notas de crédito)',
                         'doc_total': 'importe documental', 'quantity': 'cantidad documental'}[measure]
            rankings[ref['result_id']] = (
                'Líder observado por ' + criterion + ': '
                + ', '.join(names) + ' (' + number(value) + '). '
                'Universo: grupos del alcance consultado; puede haber empates. '
                'Es un ranking de importe, no de cantidad.'
                if measure in {'line_total', 'doc_total'} else
                'Primera fila por cantidad documental del alcance SQL (no líder físico global): '
                + ', '.join(names) + ' (' + number(value) + '). '
                'Universo: grupos del alcance consultado; puede haber empates. '
                'Cantidad documental; no acredita conversión entre presentaciones o unidades.')
        def cell_text(ref):
            if ref.get('kind') == 'calculation':
                # Calculations have dependencies, not result IDs. Resolve every
                # leaf through the same authorized registry as verification.
                value = self._calculation(ref)
                a, b = ref['dependencies']
                label = {'percent_change': 'Variación porcentual', 'share': 'Participación',
                         'ratio': 'Proporción', 'subtract': 'Diferencia'}[ref['operation']]
                return (label + ' = ' + number(value)
                        + (' %' if ref['operation'] in {'percent_change', 'share'} else '')
                        + ' (' + cell_text(a) + '; ' + cell_text(b) + ')')
            value, (m, node, source, index, row) = self._executed_cell(ref)
            scope = scope_text(node)
            if scope not in filters:
                filters.append(scope)
            displayed = number(value) if isinstance(value, Decimal) else str(value)
            label = compact_expression_label(node['select_list'][index])
            # Keep long conditional scopes once, not in every customer row.
            # Generated field handles carry no semantic authority from aliases.
            if len(label) > 60:
                key = (source, label)
                if key not in field_labels:
                    field_labels[key] = 'campo ' + str(len(field_labels) + 1)
                label = field_labels[key]
            return f'{source}: {label} = {displayed}'
        for check in checks:
            if not check.get('match'):
                continue
            claim = check['claim']
            if claim.get('kind') == 'executed_cell':
                value, (m, node, source, index, row) = self._executed_cell(claim)
                ranking_text(claim)
                result_scopes[claim['result_id']] = node
                # Period, units and group names come ONLY from executed SQL/data.
                names = [f'{expression_label(g)}={row[i]}' for g in node['group_expressions']
                         for i, e in enumerate(node['select_list']) if clean(e) == clean(g)]
                key = (claim.get('result_id'), claim.get('row_id'), tuple(names))
                entry = rows.setdefault(key, dict(names=names, cells=[], scope=scope_text(node)))
                text = cell_text(claim)
                # GROUP BY values are already displayed as the row identity.
                if not any(clean(node['select_list'][index]) == clean(g) for g in node['group_expressions']):
                    entry['cells'].append(text)
                continue
            dependencies = claim['dependencies']
            label = {'percent_change': 'Variación porcentual', 'share': 'Participación',
                     'ratio': 'Proporción', 'subtract': 'Diferencia'}[claim['operation']]
            if claim['operation'] == 'subtract' and all(d.get('kind') == 'executed_cell' for d in dependencies):
                sources = [self._executed_cell(d)[1][2] for d in dependencies]
                if sources == ['sales_document', 'credit_memo_document']:
                    label = 'Ventas netas documentales (facturas − notas de crédito)'
            derived.append(label+' = '+number(self._calculation(claim))
                          +(' %' if claim['operation'] in {'percent_change', 'share'} else '')
                          +'\n  A: '+cell_text(dependencies[0])+'\n  B: '+cell_text(dependencies[1]))
        lines, numbered = [], len(rows) > 1
        for position, entry in enumerate(rows.values(), 1):
            head = ', '.join(entry['names'])
            line = ((f'{position}. ' if numbered else '') + head
                    + (' · ' if head and entry['cells'] else '') + ' · '.join(entry['cells']))
            if len(filters) > 1:
                line += f' [alcance {filters.index(entry["scope"])+1}]'
            lines.append(line)
        row_lines = lines
        lines = list(rankings.values()) + derived
        for (source, expression), label in field_labels.items():
            lines.append(f'{label}: {source}: {expression}.')
        for result_id, node in result_scopes.items():
            shown = sum(1 for key in rows if key[0] == result_id)
            recovery = getattr(self, 'population_recovery', {}).get(result_id) or {}
            available = recovery.get('recovered_records') or self.entries[result_id][2].returned_count
            disclosed = len(self.entries[result_id][3])
            limits = [mod for mod in node['modifiers'] if mod['type'] == 'LIMIT_MODIFIER']
            if recovery.get('complete') and (recovery.get('pages') or limits or shown < available):
                identity = ''
                if recovery.get('distinct_entities') is not None:
                    label = {'card_code': 'cuentas SAP distintas',
                             'item_code': 'códigos de producto distintos'}.get(
                                 recovery.get('entity_column'), 'valores distintos')
                    identity = f" ({recovery['distinct_entities']} {label})"
                remaining = max(available - shown, 0)
                lines.append(f'Universo recuperado completo: {available} registros{identity}; '
                             f'{shown} seleccionados en esta respuesta y {remaining} pendientes, '
                             'disponibles por paginación local del resultado conservado sin repetir SQL.')
            elif shown < available or limits:
                lines.append(f'Selección investigativa: {shown} de {available} filas recuperadas'
                             + (f'; {disclosed} divulgadas al investigador' if disclosed < available else '')
                             + ('; SQL con LIMIT: puede haber más grupos fuera del resultado' if limits else '')
                             + '. No es una enumeración exhaustiva del universo consultado.')
        for name, codes in sorted(shared_names.items()):
            if len(codes) > 1:
                lines.append('El nombre «' + name + '» aparece en al menos ' + str(len(codes))
                             + ' cuentas SAP observadas (' + ', '.join(sorted(codes))
                             + '); se mantienen separadas, no se fusionan como una empresa ni se excluyen por su nombre.')
        if account_scope & {'card_code', 'customer_name', 'card_name'}:
            lines.append('Identidad: card_code distingue cuentas SAP; agrupar solo por nombre puede unir cuentas distintas. '
                         'El nombre no acredita cliente comercial ni comprador final, ni permite excluir cuentas de control. '
                         'Sin clasificación acreditada, el universo verificable son las cuentas facturadas, no un ranking depurado de clientes comerciales.')
        if presentation_semantics(getattr(self, 'question', '')) == 'SKU_UNION_OR':
            lines.append('Contrato: todas las presentaciones amplía los SKU acreditados mediante OR '
                         '(al menos uno); no acredita que cada cuenta compró las seis ni todas las presentaciones. '
                         'Población completa no certifica cobertura temporal ni interpretación empresarial.')
        if filters:
            lines.append('Alcance consultado (aplica a todas las cifras): '+filters[0]+'.'
                         if len(filters) == 1 else 'Alcance consultado: '
                         +'; '.join(f'{i}) {scope}' for i, scope in enumerate(filters, 1))+'.')
        lines.append('Fuente: resultados del ejecutor autorizado, publicación '+self.context.publication+
            ', snapshot '+self.context.snapshot+'. Cálculos Decimal; filas publicadas, no certificación de mes completo ni interpretación causal.')
        if any(not c.get('match') for c in checks): lines.append('Existen afirmaciones no acreditadas; respuesta parcial.')
        # Build a progressive page BEFORE the transport guard, reserving room
        # for scope, totals and omissions. Never claim that audit-only rows were
        # delivered. The durable result, not this page, serves follow-ups.
        suffix = '\n'.join(lines)
        visible = []
        for line in row_lines:
            if len(visible) >= 10 or len('\n'.join(visible + [line])) + len(suffix) + 240 > 3900:
                break
            visible.append(line)
        self.presentation_pages = {}
        for result_id, row_id, _ in list(rows)[:len(visible)]:
            manifest = self.entries[result_id][0]
            row_ids = getattr(manifest, 'row_ids', ())
            ordinal = list(row_ids).index(row_id) + 1 if row_id in row_ids else None
            if ordinal is not None:
                self.presentation_pages.setdefault(result_id, []).append(ordinal)
        if len(visible) < len(row_lines):
            suffix += (f'\nPágina: {len(visible)} de {len(row_lines)} registros seleccionados; '
                       f'{len(row_lines)-len(visible)} pendientes de presentación. '
                       'Podés pedir los siguientes del resultado conservado.')
        return '\n'.join(visible + [suffix])

    def render(self, checks):
        from decimal import Decimal
        from .claim_evidence import clean
        if any(c.get('claim', {}).get('kind') in {'executed_cell', 'calculation'} for c in checks):
            return self._render_executed(checks)
        lines, filters = [], []
        def amount(value, money):
            number = Decimal(value)
            places = max(2 if money else 0, -number.normalize().as_tuple().exponent)
            return format(number, f',.{places}f').replace(',', '_').replace('.', ',').replace('_', '.')
        labels = {'line_amount_bs': 'Importe de líneas comerciales', 'line_count': 'Líneas',
                  'document_count': 'Documentos únicos'}
        for check in checks:
            if not check.get('match'):
                continue
            c = check['claim']
            m, _, _, output, node, _, index = self._cell(c)
            groups = {col.alias: output[i] for i, col in enumerate(m.columns)
                if any(clean(node['select_list'][i]) == clean(g) for g in node['group_expressions'])}
            group_label = ', '.join(f'{k}={v}' for k, v in groups.items())
            lines.append(f"{labels[c['metric']]}: {amount(c['value'], bool(c['currency']))} {c['currency'] or ''}"
                + (f" · {group_label}" if groups else ''))
            scope = predicate_label(node['where_clause'])
            if scope not in filters:
                filters.append(scope)
        if not lines:
            lines.append('No pude acreditar cifras suficientes para responder esta pregunta.')
        if filters:
            lines.append('Alcance consultado: '+'; '.join(filters)+'.')
            lines.append('Cifras verificadas con limitaciones; interpretación empresarial no certificada.')
        if any(not c.get('match') for c in checks):
            lines.append('Hay afirmaciones no acreditadas; no se presentan como hechos.')
        lines.append('Alcance: filas publicadas; cobertura del período no certificada. Importes antes de notas de crédito y ajustes; no ventas netas ni cobros. Clasificación actual, no histórica. Causas y conversiones físicas no acreditadas.')
        lines.append('Investigación adicional: precisar productos/período o contrastar la interpretación con fuentes acreditadas.')
        return '\n'.join(lines)
