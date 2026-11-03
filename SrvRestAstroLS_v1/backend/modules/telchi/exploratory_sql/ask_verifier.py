"""Bounded per-result raw-row checks for direct ask, not universal SQL semantics.

The reference independently recomputes measures in Python, from unaggregated
published rows. Completeness still trusts the pinned source and SQL predicate
reader. No causal, cross-result ratio, join or derived lineage accreditation.
"""
from dataclasses import asdict
import copy
import json

from .ask_sources import AskExecutor
from .claim_evidence import EvidenceRegistry, evaluate
from .contracts import ExploratoryQueryProposal
from .foundation_dev import DevBudget
from .validator import canonical, digest, validate


class AskRegistry(EvidenceRegistry):
    def __init__(self, context, *, executor_factory=AskExecutor, cancel=None):
        # Scope is publication, NOT a claim of calendar completeness.
        super().__init__(context, {}, ('published_rows', 'not_complete_calendar'))
        self.controls = executor_factory(context, authorized=True)
        self.cancel = cancel
        self.populations, self.audit = {}, []

    def close(self):
        self.controls.close()

    def register(self, query, result, visible_rows):
        manifest = super().register(query, result, visible_rows)
        if manifest is None:
            return None
        entry = self.entries[manifest['result_id']]
        _, _, _, _, node, source = entry
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

    def verify(self, claim):
        if isinstance(claim, dict) and claim.get('kind') == 'share_of_universe':
            # Filtered reference populations must never impersonate an entire
            # authorized universe. No ratio accreditation in this first runner.
            return dict(claim=claim, state='UNVERIFIED', match=False,
                reason='cross_result_denominator_universe_not_accredited', evidence=[],
                required='Withdraw the ratio; report independently checked component figures.')
        return super().verify(claim)

    def render(self, checks):
        from decimal import Decimal
        from .claim_evidence import clean
        lines, filters = [], []
        def predicate(expr):
            if not expr:
                return 'universo publicado accesible'
            cls = expr.get('class')
            if cls == 'COLUMN_REF':
                return expr['column_names'][-1]
            if cls == 'CONSTANT':
                return str(None if expr['value']['is_null'] else expr['value']['value'])
            if cls == 'COMPARISON':
                op = {'COMPARE_EQUAL': '=', 'COMPARE_NOTEQUAL': '≠', 'COMPARE_LESSTHAN': '<',
                    'COMPARE_GREATERTHAN': '>', 'COMPARE_LESSTHANOREQUALTO': '≤',
                    'COMPARE_GREATERTHANOREQUALTO': '≥'}.get(expr['type'], expr['type'])
                return predicate(expr['left'])+' '+op+' '+predicate(expr['right'])
            if cls == 'CONJUNCTION':
                return '('+(' y ' if expr['type'] == 'CONJUNCTION_AND' else ' o ').join(predicate(e) for e in expr['children'])+')'
            return 'filtro adicional acreditado (detalle en evidencia)'
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
            scope = predicate(node['where_clause'])
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
