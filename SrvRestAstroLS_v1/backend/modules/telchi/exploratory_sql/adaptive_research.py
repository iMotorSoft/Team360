"""Local bounded adaptive Foundation experiment, not a Web/WhatsApp endpoint.

python -m modules.telchi.exploratory_sql.adaptive_research --authorize-dev-io-exception --output NEW.json
"""
import argparse
import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import resource
import time

from .adaptive_sources import AdaptiveExecutor, CATALOG, context_for_run
from .adaptive_verifier import reference_proposals, reconstruct, profile_relation
from .claim_evidence import EvidenceRegistry, verification_feedback, LIMITS
from .foundation import START, END
from .contracts import Decision, SecurityDecision, ExploratoryQueryResult
from .foundation import host_read_preflight
from .foundation_dev import DevBudget
from .research import LunaSQL, code_digest, proposal_from
from .validator import authorize, canonical, validate

QUESTION = ('Durante agosto de 2026, ¿por qué una parte de las ventas de estos cuatro productos '
            'de Calenta aparece sin canal comercial clasificado? Investigá cuánto representa, '
            'cuántos documentos únicos y líneas están involucrados, y qué podemos afirmar con certeza '
            'frente a lo que sigue siendo una hipótesis.')
SYSTEM = '''You are Luna, an autonomous business researcher in an explicitly authorized local DEV test.
Use only the catalog and observations, not previous experiments. Choose your investigation yourself.
The query phase is OPEN: query actions are available and will actually execute. No results have yet been observed.
Use the available reader to investigate; do not claim a query failed or execution closed without an observed failure.
An absence of initial observations is the starting point of research, not a reason to refuse investigation.
Return a JSON object, never chain-of-thought. Provide concise auditable hypotheses, evidence and decisions only.
Query action fields:
{"action":"query","sql":"SELECT ...","objective":"...","justification":"why this follows from observed evidence",
"requested_sources":["logical_table"],"expected_grain":"...","expected_result":"...","candidate_relations":[],
"hypothesis":"testable hypothesis or open question","prior_observation_interpretation":"concise interpretation; empty initially",
"hypothesis_state":"OPEN|SUPPORTED|CONTRADICTED|INSUFFICIENT", "evidence_turns":[]}
Evidence_turns may cite ONLY past observed turn numbers. Use [] before the first query; never cite your future query.
Candidate relations fields: left_table,left_column,right_table,right_column,rationale.
Final action:
{"action":"final","answer":"Spanish, BUSINESS ANSWER FIRST: result, material risks/limitations and impact, next step",
"claims":[{"kind":"measure","result_id":"server ID","column_id":"server ID","row_id":"server ID",
"metric":"line_amount_bs|document_count|line_count","value":"decimal string","unit":"money|documents|lines",
"currency":"BS or null","grain":"commercial_line|document","classification":"observed",
"publication":"observed publication","snapshot":"observed snapshot","temporal_scope":["2026-08-01","2026-09-01"]}],
"conclusions":[{"text":"...","state":"VERIFIED|VERIFIED_WITH_LIMITATIONS|INVESTIGATIVE|UNVERIFIED|BLOCKED","evidence_turns":[1]}],
"prior_observation_interpretation":"...","hypothesis_state":"..."}
Use ONLY evidence_manifest IDs from observations. An alias is presentation, never source identity or metric authority.
The manifest identifies expression, source versus calculation, unit, currency and metric accreditation.
If compact_evidence_protocol is true, manifest columns contain column_id and alias only; resolve their metadata
through the root evidence_columns dictionary. Global evidence_limitations apply to every manifest.
Focus the final answer on material findings, not unnecessary group enumerations; unsupported shapes can execute
but cannot yield accredited claims. A short correct answer with explicit uncertainty is preferable.
A row_id binds the complete group, not an arbitrary subset. Use observed classification, never claim a calculated label is official.
A percentage claim is {kind:share_of_universe,metric:share_of_universe,unit:percent,currency:null,grain:commercial_line,
value:decimal string,dependencies:[complete numerator measure claim,complete denominator measure claim]}.
The denominator must be the entire scoped universe. Query an ungrouped total if needed. No other ratio definition is accredited.
A causal claim uses kind:causal and the evidence IDs; absent accredited classifier mechanism it will be rejected.
State every material numeric assertion as a claim (max 60). Verification is controller-owned, not your labels.
Your raw answer is audit-only. Only independently verified structured facts are delivered, with their IDs and limitations.
If rejected, reconsider your hypothesis; choose your next query or correct/withdraw the claim. Do not repeat without progress.
Inspect metadata in the catalog; query only when useful. No minimum or target number of queries.
Stop when evidence is sufficient, or honestly state what cannot be established. Later queries must be motivated by observations.
Challenge alternatives; distinguish observed correlation, transformation explanation and true business cause.
No seller category, warehouse, office, series or creator may arbitrarily replace operation channel.
Only four reference SKUs L02822,L02823,L03658,L03649; not all Calenta. August 2026 active OINV/INV1.
Commercial line amounts before credit memos/global adjustments, NOT header totals, net billing or collections.
Current publication classifications, not certified historical category or month completeness. SUPPORTED is not CONFIRMED.
Use sales_operation for line money with documentary dimensions: the known OINV/INV1 link is already projected.
Header tables have no money. A document can contain several lines; document counts across line groups may overlap.
Relations proposed by you remain investigative until keys, coverage, cardinality and meaning are checked.
Joins remain subject to the existing conservative pair ceiling and may be unavailable; no bypass.
SQL subset: SELECT, explicit columns except count(*), unique ASCII snake_case aliases on all selected expressions,
CASE/COALESCE, sum/min/max/avg/count/abs/round(one arg)/lower/upper/length, GROUP BY/HAVING/ORDER BY/LIMIT,
nonrecursive CTE and FROM subquery, INNER/LEFT equijoin with known or declared candidate relation.
No casts/date functions/windows/UNION/scalar subqueries/files/network/system tables/settings/DDL/DML/extensions.
Integer/string/bool/null literals only. Values are parameterized by the engine. Denials never grant alternate access.
Only aggregates and up to three documentary samples per observation may be sent. A truncated observation is incomplete.
CRITICAL TURN PROTOCOL: Produce exactly ONE action JSON as your final_answer message, NOT commentary.
A query action is the COMPLETE response for this API call. Once you choose SQL, emit action=query in final_answer
and END YOUR TURN IMMEDIATELY. The controller will execute it and call you again with observations.
Do NOT try to execute SQL inside this response. There are no in-response tools. Do not simulate tool calls,
continue reasoning after emitting an action, or replace your query with a later final summary in the same call.
An action=query JSON in final_answer is how you request execution; action=final ends the entire investigation.
'''
QUERY_META = {'hypothesis', 'prior_observation_interpretation', 'hypothesis_state', 'evidence_turns'}


def model_proposal(value):
    for key in ('hypothesis', 'prior_observation_interpretation', 'hypothesis_state'):
        if not isinstance(value.get(key), str) or len(value[key]) > 3000:
            raise ValueError('invalid_research_metadata')
    refs = value.get('evidence_turns', [])
    if not isinstance(refs, list) or any(type(r) is not int or r < 1 for r in refs):
        raise ValueError('invalid_evidence_references')
    return replace(proposal_from({k: v for k, v in value.items() if k not in QUERY_META}), requested_budget=DevBudget())


def terminal_status(reason):
    """Classify a terminal investigation outcome by cause.

    A resource limit is a distinct state: it is not a missing capability, an
    unauthorized source, absent data or an ambiguous question.
    """
    return 'RESOURCE_LIMITED' if reason == 'observation_byte_budget' else 'BLOCKED'


def observation_rows(query, result):
    """Conservative AST-derived disclosure, never SQL regex or model-declared grain.

    Aggregation in a subquery is insufficient: the outer SELECT must group or
    aggregate. Otherwise this is a documentary sample, even if it contains 'sum'.
    """
    tree = json.loads(query.admitted_tree_json) if query else {}
    # Admitted tree is the native parsed statement; inspect only outer SELECT.
    statements = tree.get('statements', [])
    node = statements[0].get('node', {}) if len(statements) == 1 else {}
    def aggregate(expr):
        if not isinstance(expr, dict):
            return False
        if expr.get('type') == 'FUNCTION' and expr.get('function_name', '').lower() in {'sum', 'count', 'count_star', 'min', 'max', 'avg'}:
            return True
        return any(aggregate(v) for v in expr.values() if isinstance(v, dict)) or any(
            aggregate(x) for v in expr.values() if isinstance(v, list) for x in v)
    grouped = bool(node.get('group_expressions')) or any(aggregate(e) for e in node.get('select_list', []))
    def documentary(expr):
        if not isinstance(expr, dict):
            return False
        # COUNT(document key) discloses a count, not the key. MIN/MAX or
        # grouping by a documentary key is still a sample, not safe bulk export.
        if expr.get('type') == 'FUNCTION' and expr.get('function_name', '').lower() in {'count', 'count_star'}:
            return False
        if expr.get('type') == 'COLUMN_REF' and expr.get('column_names', [''])[-1] in {'doc_entry', 'doc_num', 'line_num', 'raw_extraction_id'}:
            return True
        return any(documentary(v) for v in expr.values() if isinstance(v, dict)) or any(
            documentary(x) for v in expr.values() if isinstance(v, list) for x in v)
    # Inspect derived/CTE projections too: renaming a document key must not
    # turn documentary samples into a 30-row aggregate export. Conservatively
    # using three rows for outer aggregates is acceptable when lineage is mixed.
    has_document_keys = documentary(node)
    cap = 30 if grouped and not has_document_keys else 3
    return result.rows[:cap]


def ordered_observation(query):
    """Only an admitted OUTER ORDER BY establishes an ordered result prefix."""
    tree = json.loads(query.admitted_tree_json) if query else {}
    statements = tree.get('statements', [])
    node = statements[0].get('node', {}) if len(statements) == 1 else {}
    return any(m.get('type') == 'ORDER_MODIFIER' and m.get('orders') for m in node.get('modifiers', []))


OBSERVATION_BUDGET = 32768


def payload_sizes(payload):
    """Byte cost per transported component. Measurement, never truncation."""
    size = lambda value: len(canonical(value).encode())
    sizes = {key: size(value) for key, value in payload.items()
             if key in {'question', 'conversation', 'observations', 'catalog',
                        'business_knowledge', 'query_limits', 'requested_calculations',
                        'requested_scope'}}
    sizes['total'] = size(payload)
    sizes['observations_detail'] = [
        dict(turn=o.get('turn'), total=size(o), rows=size(o.get('rows')),
             manifest=size(o.get('evidence_manifest')), schema=size(o.get('schema')),
             evidence=bool(o.get('evidence_manifest')))
        for o in payload.get('observations') or [] if isinstance(o, dict)]
    return sizes


def bounded_payload(payload, stats=None, *, wire_budget=None):
    """Compact prior samples, never expand the budget or hide truncation.

    `stats` (optional) receives the measured size of every compaction stage and
    of each transported component, so a budget stop is reported with its actual
    cause instead of being discarded downstream.
    """
    import copy
    compact = copy.deepcopy(payload)
    record = stats if stats is not None else {}
    wire_limit = wire_budget or OBSERVATION_BUDGET
    record['limit'] = wire_limit
    sizes = lambda: len(canonical(compact).encode())

    def checkpoint(stage):
        record.setdefault('stages', {})[stage] = sizes()

    checkpoint('input')
    # The effective scope is already the durable conversational context for a
    # territorial reconciliation. Do not retransmit prior research prose; it is
    # audit-only and can crowd out the current mapping/line evidence.
    scope_state = (compact.get('effective_scope') or {}).get('state') or {}
    if scope_state.get('branches') or scope_state.get('entity_mention'):
        compact.pop('conversation', None)
        compact.pop('business_knowledge', None)
        checkpoint('territorial_context_compacted')
    if sizes() > OBSERVATION_BUDGET:
        record['components'] = payload_sizes(payload)
    if (len(canonical(compact).encode()) > wire_limit and 'catalog' in compact
            and any(isinstance(c, dict) for t in compact['catalog'].get('tables', [])
                    for c in (t.get('columns') or []))):
        # Discovery may already have emitted the lossless compact column mapping.
        # Do not treat its dictionary keys as column records on the next payload
        # pass: that was the TypeError behind durable dispatch_uncommitted.
        # Compact redundant field labels only; do not drop sources, columns, types
        # or semantic limits.
        catalog = compact['catalog']
        types = sorted({c['sql_type'] for t in catalog['tables'] for c in t['columns']})
        constraints = sorted({s for t in catalog['tables'] for s in t['semantic_constraints']})
        catalog['tables'] = [dict(name=t['name'], grain=t['grain'],
            columns={c['name']: types.index(c['sql_type']) for c in t['columns']},
            semantic_constraints=[constraints.index(s) for s in t['semantic_constraints']])
            for t in catalog['tables']]
        catalog['column_type_dictionary'] = types
        catalog['semantic_constraint_dictionary'] = constraints
        compact['compact_catalog_protocol'] = 'Column types and constraints are zero-based dictionary indices.'
        if len(canonical(compact).encode()) > wire_limit:
            # Published sources share many columns. Intern the complete
            # (name, type-index) pair; keep every table's membership and order.
            columns = sorted({(name, kind) for table in catalog['tables']
                              for name, kind in table['columns'].items()})
            indices = {column: index for index, column in enumerate(columns)}
            for table in catalog['tables']:
                table['columns'] = [indices[column] for column in table['columns'].items()]
            catalog['column_dictionary'] = columns
            compact['compact_catalog_protocol'] += (
                ' Table columns are zero-based column_dictionary indices; each dictionary '
                'entry is [column_name, column_type_dictionary index]. All sources remain available.')
    for observation in compact['observations']:
        if observation.get('evidence_manifest'):
            observation.pop('schema', None)  # schema is already in the manifest
    if len(canonical(compact).encode()) > wire_limit:
        descriptors = {}
        for observation in compact['observations']:
            manifest = observation.get('evidence_manifest')
            if not manifest: continue
            for col in manifest['columns']:
                descriptors[col['column_id']] = {k: v for k, v in col.items() if k != 'alias'}
            manifest['columns'] = [{k: col[k] for k in ('column_id', 'alias')} for col in manifest['columns']]
            compact['evidence_limitations'] = LIMITS
            manifest['limitations'] = tuple(limit for limit in manifest.get('limitations', ()) if limit not in LIMITS)
        compact['evidence_columns'] = descriptors
        compact['compact_evidence_protocol'] = True
    if len(canonical(compact).encode()) > wire_limit:
        # Feedback is persisted in full by the controller. On the wire its
        # column description can reference the very same issued manifest. Never
        # remove a discrepancy, observed value, dependency or required action.
        columns = compact.get('evidence_columns', {})
        for observation in compact['observations']:
            for check in observation.get('rejected_claims', ()):
                for evidence in check.get('evidence', ()):
                    column = evidence.get('column', {})
                    column_id = column.get('column_id')
                    if column_id in columns and columns[column_id] == {k: v for k, v in column.items() if k != 'alias'}:
                        evidence['column_ref'] = column_id
                        evidence['column_alias'] = column['alias']
                        del evidence['column']
        if columns:
            # Lossless tabular encoding of repeated descriptor field names.
            # This is transport only; it cannot grant grain or business meaning.
            names = list(next(iter(columns.values())))
            compact['evidence_column_fields'] = names
            compact['evidence_columns'] = {key: [col[name] for name in names] for key, col in columns.items()}
            compact['compact_evidence_protocol'] = (
                'evidence_columns values follow evidence_column_fields. '
                'column_ref resolves there; column_alias is presentation only.')
    for observation in compact['observations']:
        if len(canonical(compact).encode()) <= wire_limit:
            break
        rows = observation.get('rows', ())
        if len(rows) > 3 and observation.get('evidence_manifest'):
            observation['rows'] = rows[:3]
            observation['evidence_manifest']['row_ids'] = observation['evidence_manifest']['row_ids'][:3]
            observation['truncated'] = True
            observation['history_compacted'] = True
    checkpoint('evidence_compacted')
    if len(canonical(compact).encode()) > wire_limit:
        for observation in compact['observations']:
            if not observation.get('evidence_manifest'): continue
            # Model-authored rationale is already audited; it is not evidence.
            observation.pop('hypothesis', None)
            observation.pop('objective', None)
            if observation.get('decision', {}).get('decision') == 'ALLOW':
                observation['decision'] = {'decision': 'ALLOW'}
    checkpoint('rationale_compacted')
    if len(canonical(compact).encode()) > wire_limit:
        # Controller feedback is guidance that the audit already persists; it is
        # not an operand, a population or a column. Only those entries leave the
        # wire, and the omission is declared with its count.
        omitted = 0
        kept = []
        for observation in compact['observations']:
            if observation.get('evidence_manifest') or observation.get('turn'):
                kept.append(observation)
            else:
                omitted += 1
        if omitted:
            compact['observations'] = kept
            compact['omitted_feedback_entries'] = omitted
            protocol = compact.get('compact_evidence_protocol')
            compact['compact_evidence_protocol'] = (
                (protocol if isinstance(protocol, str) else '') +
                ' Controller feedback entries (already persisted in the audit, never evidence) '
                'are summarized by omitted_feedback_entries.').strip()
            checkpoint('feedback_summarized')
    if len(canonical(compact).encode()) > wire_limit:
        # Prior conversation prose is context, not evidence: bound it explicitly
        # so the current question and every observation stay intact.
        conversation = compact.get('conversation') or []
        bounded, changed = [], False
        for message in conversation:
            content = message.get('content') if isinstance(message, dict) else None
            if isinstance(content, str) and len(content) > 600:
                message = dict(message, content=content[:600] +
                    ' [recortado en este envío; el texto completo queda en la auditoría]')
                changed = True
            bounded.append(message)
        if changed:
            compact['conversation'] = bounded
            compact['conversation_bounded'] = True
            checkpoint('conversation_bounded')
    if len(canonical(compact).encode()) > wire_limit:
        # The complete manifest remains in the durable evidence registry/report.
        # On-wire repetition is transport overhead, not business evidence. Keep
        # the issued identifiers and observed cells, and publish a recovery
        # handle for metadata that the controller can recover from persistence.
        omitted = []
        for observation in compact.get('observations', ()):
            manifest = observation.get('evidence_manifest') or {}
            for field in ('continuity_cells', 'filter_expression', 'limitations'):
                if field in manifest:
                    omitted.append(dict(turn=observation.get('turn'), field=field,
                                        result_id=manifest.get('result_id')))
                    manifest.pop(field, None)
        if omitted:
            compact['evidence_recovery'] = {
                'status': 'PERSISTED_FULL_EVIDENCE_AVAILABLE',
                'omitted_manifest_fields': omitted,
                'instruction': 'Use issued result/column/row handles; full manifests remain controller-owned and recoverable.',
            }
            checkpoint('persisted_evidence_referenced')
    if len(canonical(compact).encode()) > wire_limit:
        raise RuntimeError('observation_byte_budget')
    checkpoint('delivered')
    return compact


def discovery_catalog(catalog, sources):
    """Transport projection only; authorization always retains the FULL catalog.

    All source names/grains remain visible. A discover action replaces the loaded
    schemas, rather than appending schemas to evidence history indefinitely.
    """
    value = asdict(catalog)
    # Expose schema differences BEFORE selecting a source. Names alone hide
    # relevant alternatives (header vs line facts, different date/name fields).
    # Intern names to retain every authorized column within the existing budget;
    # types and constraints still require loading the actual schema.
    names = sorted({c.name for t in catalog.tables for c in t.columns})
    indices = {name: i for i, name in enumerate(names)}
    value['source_column_dictionary'] = names
    value['source_index'] = [dict(name=t.name, grain=t.grain, permission=t.permission,
        columns=[indices[c.name] for c in t.columns]) for t in catalog.tables]
    if len(canonical(value['source_index']).encode()) + len(canonical(names).encode()) > 8000:
        # Large authorized catalogs need discovery headroom. Retain every source
        # and its access family; full columns remain discoverable on demand via
        # the existing discover action rather than consuming the observation
        # budget before Luna can select a source.
        value.pop('source_column_dictionary')
        for item in value['source_index']:
            item['column_count'] = len(item.pop('columns'))
    value['tables'] = [asdict(t) for t in catalog.tables if t.name in sources]
    # Keep selected schemas exact for small discoveries; large mixed discoveries
    # use the same lossless dictionaries as bounded_payload so evidence and the
    # source index can coexist under the fixed 32 KiB wire budget.
    if len(canonical(value).encode()) > 12000 and value['tables']:
        types = sorted({c['sql_type'] for t in value['tables'] for c in t['columns']})
        constraints = sorted({s for t in value['tables'] for s in t['semantic_constraints']})
        for table in value['tables']:
            table['columns'] = {c['name']: types.index(c['sql_type']) for c in table['columns']}
            table['semantic_constraints'] = [constraints.index(s) for s in table['semantic_constraints']]
        value['column_type_dictionary'] = types
        value['semantic_constraint_dictionary'] = constraints
        value['compact_catalog_protocol'] = 'Selected table columns and constraints use zero-based dictionaries; exact names remain keys.'
    value['discovery_protocol'] = (
        'source_index lists ALL authorized sources; when present, its columns index source_column_dictionary (names only). '
        'Shared permission identifies possible alternatives, NOT equivalent populations or accredited semantics. '
        'Presence in this index proves no rows, dates, grain or calendar completeness. '
        'tables contains only currently loaded schemas. '
        'Request any sources, across domains, with {"action":"discover","requested_sources":["name",...]}. '
        'This replaces loaded schemas, executes no SQL, and grants no new authority. '
        'Use exact column names from the loaded schema. Request a smaller set if schemas exceed the byte budget.')
    return value


class EvidenceWireIds:
    """Lossless short handles for issued evidence, scoped to ONE investigation.

    Long cryptographic IDs stay in audit/verification; wire handles grant nothing.
    Only delivered manifests can issue handles, never arbitrary model fields.
    """
    def __init__(self):
        self.encode = {key: {} for key in ('result_id', 'column_id', 'row_id')}
        self.decode = {key: {} for key in self.encode}

    def payload(self, payload):
        for observation in payload['observations']:
            manifest = observation.get('evidence_manifest')
            if not manifest:
                continue
            values = dict(result_id=[manifest['result_id']], row_id=manifest['row_ids'],
                          column_id=[c['column_id'] for c in manifest['columns']])
            for key, ids in values.items():
                for value in ids:
                    if value not in self.encode[key]:
                        prefix = {'result_id': 'q', 'column_id': 'c', 'row_id': 'r'}[key]
                        short = prefix + str(len(self.encode[key]) + 1)
                        self.encode[key][value] = short
                        self.decode[key][short] = value
        return self.translate(payload, self.encode)

    def translate(self, value, maps):
        if isinstance(value, list):
            return [self.translate(v, maps) for v in value]
        if isinstance(value, tuple):
            return tuple(self.translate(v, maps) for v in value)
        if isinstance(value, dict):
            return {k: (maps[k].get(v, v) if k in maps and isinstance(v, str)
                        else [maps['row_id'].get(r, r) for r in v] if k == 'row_ids'
                        else self.translate(v, maps)) for k, v in value.items()}
        return value

    def claims(self, claims):
        return self.translate(claims, self.decode)


def population_coverage(registry, checks):
    """Coverage of selected populations only; unrelated discovery cannot complete it."""
    selected = {check.get('claim', {}).get('result_id') for check in checks if check.get('match')}
    recoveries = getattr(registry, 'population_recovery', {})
    populations = [recoveries[key] for key in selected if key in recoveries]
    if not populations:
        return 'NOT_CERTIFIED'
    return ('COMPLETE' if all(p.get('complete') and not p.get('reason')
                             and isinstance(p.get('recovered_records'), int)
                             and p['recovered_records'] >= 0 for p in populations)
            else 'PARTIAL')


def recovered_population_claims(registry, claims):
    """Deliver the one paged, fully recovered universe its answer never named.

    The model keeps choosing the scope; the controller only refuses to let a
    recovered population stay invisible. Restricted to exactly one paged
    population, so competing lists still fail closed instead of being guessed.
    """
    from .claim_evidence import clean
    recovered = {result_id: value for result_id, value in
                 getattr(registry, 'population_recovery', {}).items()
                 if value.get('complete') and value.get('pages')}
    if len(recovered) != 1:
        return []
    result_id = next(iter(recovered))
    if any(isinstance(claim, dict) and claim.get('result_id') == result_id for claim in claims):
        return []
    entry = getattr(registry, 'entries', {}).get(result_id)
    if not entry or not entry[3]:
        return []
    manifest, _, _, visible_rows, node, _ = entry
    groups = node.get('group_expressions') or ()
    indexes = [index for index, expression in enumerate(node.get('select_list') or ())
               if any(clean(expression) == clean(group) for group in groups)]
    columns = [manifest.columns[index] for index in indexes if index < len(manifest.columns)]
    if not columns:
        return []
    row_ids = list(manifest.row_ids)[:min(len(visible_rows), 10)]
    return [dict(kind='executed_cell', result_id=result_id, column_id=column.column_id,
                 row_id=row_id) for row_id in row_ids for column in columns]


async def run(report, save, *, luna=None, executor_factory=AdaptiveExecutor, wall_seconds=None,
              question=QUESTION, conversation=(), context=None, system=SYSTEM,
              registry_factory=None, progress=lambda event: None, cancel=None, required_measure=None,
              allow_query_batches=False, compact_evidence_ids=False, business_knowledge=None,
              effective_scope=None):
    start = time.monotonic()
    context = context or context_for_run()
    authorize(context)
    catalog = context.catalog
    scope_state = (effective_scope or {}).get('state') or {}
    if scope_state.get('branches') or scope_state.get('entity_mention'):
        # This is a generic contract guard, not an entity or amount shortcut:
        # the published crosswalk resolves membership and both line sources
        # must use the same period/status/currency predicates.
        system = ('''TERRITORIAL CONTRACT OVERRIDE: The confirmed scope contains a
business location. Do not ask whether to use document totals or line amounts.
Answer with accredited commercial-line net: SUM(sales_line.line_total) minus
SUM(credit_memo_line.line_total). Resolve the named location only through the
published warehouse_business_location relation and its exact warehouse_code
join. Your first query action must be a batch containing the two independent
aggregates (invoice lines and credit-memo lines); do not spend a query on
coverage or a mapping sample first. Each aggregate must use the identical
location mapping predicates, active status, BS currency and [start,end) dates.
Never use sales_document.doc_total or credit_memo_document.doc_total,
never aggregate all warehouses, and never finalize a query whose SQL does not
show the authorized mapping relation and all requested filters.
''' + system)
    luna = luna or LunaSQL(system=system, max_output_tokens=8192)
    progress('Verificando modelo y autorización DEV')
    report.update(identifier='TELCHIAI_ADAPTIVE_BUSINESS_RESEARCH_V1', question=question,
        universe='catalog-authorized population' if registry_factory else ['L02822', 'L02823', 'L03658', 'L03649'], publication=context.publication, snapshot=context.snapshot,
        code_digest=code_digest(), catalog=asdict(catalog), system_prompt=system,
        budget=asdict(context.effective_budget), wall_seconds=None, status='PARTIAL',
        turns=[], model_events=[], reference_queries=[], model_configuration=dict(model='gpt-5.6-luna',
        reasoning='medium', fallback=False, store=False, provider='OpenAI Responses direct',
        max_output_tokens=8192, calls_cap=16),
        limits=['local supervised DEV identity, not Console RBAC', 'no OS isolation accreditation',
                'DuckDB memory limit is not a process RSS limit', 'attachment setup is not OS-preemptible',
                'no historical classification or complete-month certification', 'narrative is not certified by arithmetic'])
    report['business_knowledge'] = business_knowledge or {}
    report['required_measure'] = required_measure
    history = []
    # Reserve observation headroom. Large authorized publications expose their
    # complete index first, not an oversized schema blob on every model call.
    progressive_catalog = False
    if registry_factory:
        # The source index is the durable catalog authority. Start with no
        # schemas and discover only selected sources; retransmitting metadata
        # on every observation is not evidence and can exhaust the fixed budget.
        progressive_catalog = True
    discovered_sources = set()
    # Territorial line reconciliations have a closed, backend-accredited join
    # contract. Preload only those existing schemas when the service-owned scope
    # already contains a location; this avoids spending model turns rediscovering
    # the very mapping required to preserve the user's filter and keeps the
    # observation payload within its existing budget.
    scope_state = (effective_scope or {}).get('state') or {}
    if scope_state.get('branches') or scope_state.get('entity_mention'):
        territorial_sources = {'sales_line', 'credit_memo_line',
                               'warehouse_business_location'}
        discovered_sources.update({table.name for table in catalog.tables
                                   if table.name in territorial_sources})
    premature_final_feedback = False
    verification_repairs = 0
    rejected_fingerprints = set()
    attempted_queries = set()
    query_attempts = 0
    execution_closed = False
    pending_queries = []
    verification_seconds = 0.0
    wire_ids = EvidenceWireIds() if compact_evidence_ids else None
    save(report)
    try:
        # Minimal real API/auth/quota/model probe; no commercial rows or historical answers.
        probe = LunaSQL(system='Return exactly a JSON object {"ready":true}.')
        report['model_preflight'] = await probe.next({'purpose': 'authorized DEV model preflight'}, timeout=45)
        report['model_preflight_calls'] = probe.calls
        if report['model_preflight'] != {'ready': True}:
            raise RuntimeError('model_preflight_failed')
        save(report)
        # Independent phase uses its own bounded executor, never sends control
        # rows, amounts, seller names or previous findings to Luna.
        with executor_factory(context, authorized=True) as controls:
            results = []
            for p in (() if registry_factory else reference_proposals()):
                # A technical SQL/resource guard may stop an operation, but no
                # elapsed-time budget terminates the business investigation.
                decision, result = controls.execute(p, context)
                report['reference_queries'].append(dict(proposal=asdict(p), decision=asdict(decision), result=asdict(result)))
                save(report)
                if result.status != 'COMPLETED' or result.truncated:
                    raise RuntimeError('independent_reference_blocked:' + decision.reason)
                results.append(result)
        if registry_factory:
            tables, summary = {}, {'state': 'PER_RESULT_BOUNDED_REFERENCE', 'full_population_reconciled': False}
            registry = registry_factory(context)
            registry.question = question  # Intent context only; never source authority.
        else:
            tables, summary = reconstruct(context, results)
            registry = EvidenceRegistry(context, tables, (START, END))
        report['identifier'] = 'TELCHIAI_ANALYTICAL_CLAIM_VERIFICATION_V1'
        report['independent_business_reconciliation'] = summary
        save(report)
        with executor_factory(context, authorized=True) as executor:
            for call in range(16):
                if executor.cancel.is_set() or (cancel and cancel.is_set()):
                    raise RuntimeError('research_cancelled_by_operator')
                authorize(context)  # Includes live revocation for issued phase-B contexts.
                progress('Analizando observaciones con Luna')
                payload = dict(question=question, current_date=datetime.now(timezone.utc).date().isoformat(),
                               conversation=list(conversation), required_measure=required_measure,
                               requested_calculations=(sorted(registry.requested_calculations())
                                   if hasattr(registry, 'requested_calculations') else []),
                               requested_scope=(sorted(registry.requested_scope())
                                   if hasattr(registry, 'requested_scope') else []),
                               effective_scope=effective_scope or {},
                               business_knowledge=business_knowledge or {},
                               catalog=(discovery_catalog(catalog, discovered_sources)
                                        if progressive_catalog else asdict(catalog)), observations=list(history),
                               current_observed_turns=[o['turn'] for o in history if 'turn' in o],
                               evidence_namespace='THIS investigation only; conversation contains NO reusable evidence IDs or turn numbers.',
                               execution_closed=execution_closed, query_limits=asdict(context.effective_budget),
                               remaining_query_budget=0 if execution_closed else context.effective_budget.queries-query_attempts)
                if pending_queries:
                    value = pending_queries.pop(0)
                else:
                    if wire_ids:
                        payload = wire_ids.payload(payload)
                    budget = {}
                    try:
                        territorial_wire_budget = 65536 if (
                            (effective_scope or {}).get('state', {}).get('branches') or
                            (effective_scope or {}).get('state', {}).get('entity_mention')) else None
                        payload = bounded_payload(payload, budget,
                                                   wire_budget=territorial_wire_budget)
                    except RuntimeError:
                        # Report the measured cause, never discard it: the exit is
                        # a resource limit, not a business or authorization result.
                        report['observation_budget'] = dict(
                            limit=budget.get('limit', 32768), reason='observation_byte_budget',
                            call=call + 1, stages=budget.get('stages'),
                            measured_bytes=budget.get('stages', {}).get('input'),
                            components=budget.get('components'))
                        save(report)
                        raise
                    report.setdefault('model_input_sizes', []).append(len(canonical(payload).encode()))
                    report.setdefault('observation_budget_stages', []).append(budget.get('stages'))
                    # 90s is an operation deadline for one provider call, not
                    # a deadline for the investigation. Durable replay resumes
                    # from the last persisted checkpoint after a technical fault.
                    value = await asyncio.wait_for(luna.next(payload, timeout=90), 90)
                    authorize(context)  # Model latency must not preserve a revoked scope.
                    report['model_calls'] = luna.calls
                    report['model_events'].append(value)
                    save(report)
                    if value.get('action') == 'queries' and allow_query_batches:
                        batch = value.get('queries')
                        try:
                            if (set(value) != {'action', 'queries'} or not isinstance(batch, list)
                                    or not 1 <= len(batch) <= context.effective_budget.queries-query_attempts
                                    or execution_closed):
                                raise ValueError('invalid_query_batch')
                            # Independent proposals only: none may cite a result
                            # that has not been observed before this model call.
                            for item in batch:
                                model_proposal(item)
                                if any(r > len(report['turns']) for r in item.get('evidence_turns', [])):
                                    raise ValueError('unobserved_batch_dependency')
                        except (ValueError, TypeError, KeyError):
                            history.append(dict(status='INVALID_QUERY', reason='invalid_query_batch',
                                guidance='Submit independent ordinary query actions; no SQL was executed.'))
                            continue
                        value, *pending_queries = batch
                if value.get('action') == 'discover' and progressive_catalog:
                    names = value.get('requested_sources')
                    available = {t.name for t in catalog.tables}
                    if (set(value) != {'action', 'requested_sources'} or not isinstance(names, list)
                            or not names or any(not isinstance(n, str) or n not in available for n in names)):
                        history.append(dict(status='INVALID_DISCOVERY', reason='request_existing_source_names'))
                        continue
                    selected = set(names)
                    trial = discovery_catalog(catalog, selected)
                    try:
                        bounded_payload(dict(catalog=trial, observations=list(history)))
                    except RuntimeError:
                        history.append(dict(status='INVALID_DISCOVERY', reason='schema_byte_budget',
                            guidance=('The requested schema set exceeds the observation envelope. Keep the schemas '
                                      'already loaded, do not request additional discovery, and emit the independent '
                                      'query using the loaded authorized sources.')))
                        continue
                    newly_selected = selected - discovered_sources
                    if not newly_selected:
                        history.append(dict(status='DISCOVERY_ALREADY_LOADED', sources=sorted(selected),
                            guidance='These source schemas are already loaded. Do not rediscover them; emit a query or clarify the concrete business gap.'))
                    else:
                        discovered_sources |= selected
                        history.append(dict(status='DISCOVERY_COMPLETE', sources=sorted(selected),
                            guidance='Requested source schemas are now loaded. Use their exact columns and emit an independent query.'))
                    report.setdefault('catalog_discoveries', []).append(sorted(selected))
                    save(report)
                    continue
                if value.get('action') == 'clarify':
                    text = value.get('question')
                    if not isinstance(text, str) or not 0 < len(text) <= 2000:
                        raise RuntimeError('invalid_clarification')
                    report.update(status='NEEDS_CLARIFICATION', clarification=text)
                    return
                if value.get('action') == 'final':
                    # A protocol repair, not a prescribed investigative route or
                    # artificial query minimum. Never reject an evidence-based
                    # final; only clarify an initial no-observations refusal once.
                    if not report['turns'] and not premature_final_feedback:
                        premature_final_feedback = True
                        history.append(dict(status='PROTOCOL_FEEDBACK', reason=(
                            'No query has been attempted and no execution failure has occurred. '
                            'The reader is available. If evidence you need can be obtained with it, '
                            'emit your chosen query action, not a recommendation to execute it later. '
                            'Choose the SQL yourself. You may finalize if the available context suffices '
                            'or you can identify a concrete evidence gap the authorized reader cannot resolve.')))
                        report['protocol_repairs'] = ['initial_no_observation_final_clarification']
                        continue
                    if not isinstance(value.get('answer'), str) or not value['answer'].strip():
                        raise RuntimeError('invalid_final_answer')
                    claims = value.get('claims', [])
                    if not isinstance(claims, list):
                        raise RuntimeError('invalid_final_claims')
                    if len(claims) > 60:
                        feedback = dict(status='INVALID_FINAL', reason='final_claim_budget',
                            guidance='At most 60 top-level claims. Group identities are rendered automatically; '
                            'do not duplicate code/name dimensions. Select material amount/count cells and coverage; '
                            'the controller pages delivery and retains full executed rows. No new SQL is needed.')
                        history.append(feedback)
                        report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                        save(report)
                        continue
                    if wire_ids:
                        claims = wire_ids.claims(claims)
                    report['model_answer'] = None
                    report['model_conclusions'] = []
                    progress('Verificando afirmaciones independientemente')
                    verification_started = time.monotonic()
                    if registry_factory:
                        synthesized = [claim for claim in recovered_population_claims(registry, claims)
                                       if registry.verify(claim).get('match')]
                        if synthesized:
                            claims = list(claims) + synthesized
                            report['population_claims'] = len(synthesized)
                        # The State Engine owns completion of composite business
                        # measures. Luna may omit the numeric cells after the
                        # deterministic counterpart query has run; that prose
                        # omission must not turn accredited evidence into PARTIAL.
                        if required_measure == 'territorial_line_net':
                            from .business_measure import deterministic_claims
                            contract_claims = deterministic_claims(registry, required_measure)
                            if contract_claims:
                                claims = list(claims) + [claim for claim in contract_claims
                                                         if claim not in claims]
                                report['deterministic_contract_completion'] = {
                                    'measure': 'commercial_line_net_amount.v1',
                                    'claims_added': len(contract_claims),
                                    'source': 'state_engine_executed_cells',
                                }
                    report['claim_verifications'] = [registry.verify(c) for c in claims]
                    verification_seconds += time.monotonic()-verification_started
                    checks = report['claim_verifications']
                    report.setdefault('final_reviews', []).append(dict(
                        proposed_answer=value, claim_verifications=checks,
                        proposed_answer_state='UNVERIFIED_MODEL_PROPOSAL_NOT_EVIDENCE'))
                    mismatches = [c for c in checks if not c['match']]
                    fingerprint = canonical([c['claim'] for c in mismatches])
                    coverage_feedback = (registry.final_feedback(claims, net_required=required_measure in {'net_document', 'territorial_line_net'})
                        if hasattr(registry, 'final_feedback') else None)
                    # A demonstrated scope contradiction outranks a numeric
                    # repair: the numbers of a rejected interpretation are not
                    # the real gap. Both messages stay in the audit history.
                    if coverage_feedback:
                        history.append(dict(status='BUSINESS_SCOPE_FEEDBACK', reason=coverage_feedback))
                        report.setdefault('controller_feedback', []).append(dict(call=call+1,
                            status='BUSINESS_SCOPE_FEEDBACK', reason=coverage_feedback))
                    if mismatches and verification_repairs < 3 and fingerprint not in rejected_fingerprints:
                        rejected_fingerprints.add(fingerprint)
                        verification_repairs += 1
                        feedback = verification_feedback(checks)
                        history.append(feedback)
                        report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                        save(report)
                        continue
                    complete = not registry_factory or value.get('coverage') == 'COMPLETE'
                    # Population accounting is controller evidence, never a model label.
                    # It does not certify the calendar or the entire business question.
                    report['population_coverage'] = population_coverage(registry, checks)
                    report['temporal_coverage'] = 'NOT_CERTIFIED'
                    report['business_interpretation'] = 'NOT_INDEPENDENTLY_CERTIFIED'
                    # PARTIAL is an honest terminal outcome, not a request to
                    # repeat final actions until the model claims COMPLETE.
                    # Concrete missing evidence (e.g. net components) still
                    # receives feedback; publication/classification limits
                    # cannot be repaired with repeated SQL or final summaries.
                    if registry_factory and (not checks or coverage_feedback) and not execution_closed and query_attempts < context.effective_budget.queries:
                        feedback = dict(status='INCOMPLETE_FINAL', reason=coverage_feedback or
                            'Final lacks complete requested evidence. Continue investigation/correct SQL; discovery alone is not the requested amount.')
                        history.append(feedback)
                        report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                        save(report)
                        continue
                    complete = complete and not coverage_feedback
                    report['question_coverage'] = 'MODEL_DECLARED_COMPLETE_NOT_INDEPENDENTLY_CERTIFIED' if complete else 'PARTIAL'
                    observed_only = checks and all(c['state'] == 'EXECUTOR_OBSERVED_WITH_LIMITATIONS' for c in checks)
                    report['status'] = (('EXECUTOR_OBSERVED_WITH_LIMITATIONS' if observed_only else 'VERIFIED_WITH_LIMITATIONS')
                        if checks and not mismatches and complete else 'PARTIAL')
                    render_started = time.monotonic()
                    report['business_answer'] = registry.render(checks)
                    # Preserve proposed prose only as explicitly unverified input,
                    # never as an accepted answer/conclusion in an audit summary.
                    report['model_answer_state'] = 'DETERMINISTIC_EVIDENCE_RENDER_NOT_MODEL_PROSE'
                    report['model_answer'] = report['business_answer']
                    report['model_conclusions'] = []
                    report['presentation_pages'] = getattr(registry, 'presentation_pages', {})
                    report['population_pages'] = getattr(registry, 'population_pages', {})
                    report['population_recovery'] = getattr(registry, 'population_recovery', {})
                    report['deterministic_render_seconds'] = time.monotonic()-render_started
                    if not complete:
                        report['business_answer'] += '\nLa pregunta tiene partes pendientes; las cifras anteriores son solo una respuesta parcial.'
                    report['evidence_manifests'] = (registry.manifests() if hasattr(registry, 'manifests')
                        else [asdict(entry[0]) for entry in registry.entries.values()])
                    report['narrative_state'] = 'RAW_MODEL_PROSE_AUDIT_ONLY; delivered facts rendered from verified evidence'
                    report['unresolved_claim_count'] = len(mismatches)
                    report['hypothesis_revision'] = dict(reviews=len(report['final_reviews']),
                        rejected_claims=sum(not c['match'] for review in report['final_reviews'] for c in review['claim_verifications']),
                        repeated_without_progress=bool(mismatches and fingerprint in rejected_fingerprints))
                    report['final_observation_interpretation'] = None
                    return
                if execution_closed:
                    raise RuntimeError('query_phase_closed_no_further_sql')
                if value.get('action') not in {'query', 'final', 'clarify'}:
                    feedback = dict(status='INVALID_ACTION', reason='explicit_action_required',
                        guidance='Every response MUST include action. For a completed answer emit '
                        '{"action":"final","coverage":"COMPLETE|PARTIAL","answer":"concise audit text","claims":[...]} '
                        'with the already observed evidence IDs. A missing action is not executable. '
                        'For SQL emit action=query with the documented query fields.')
                    history.append(feedback)
                    report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                    save(report)
                    continue
                try:
                    p = model_proposal(value)
                except (ValueError, TypeError, KeyError) as exc:
                    feedback = dict(status='INVALID_QUERY', reason=str(exc)[:100],
                        guidance='Query keys must be exactly action,sql,objective,justification,requested_sources,'
                        'expected_grain,expected_result,candidate_relations,hypothesis,prior_observation_interpretation,'
                        'hypothesis_state,evidence_turns. Remove extra top-level fields such as rationale.')
                    history.append(feedback)
                    report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                    save(report)
                    continue
                if any(r > len(report['turns']) for r in value.get('evidence_turns', [])):
                    feedback = dict(status='INVALID_QUERY', reason='unknown_evidence_turn', available_turns=len(report['turns']),
                        guidance='evidence_turns cites ONLY current_observed_turns in THIS investigation. Conversation is NOT an observation. Use evidence_turns=[] now and resubmit your query; no SQL was executed or query budget consumed.')
                    history.append(feedback)
                    report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                    save(report)
                    continue
                query_attempts += 1
                report['query_attempts'] = query_attempts
                if query_attempts > context.effective_budget.queries:
                    raise RuntimeError('query_attempt_budget_exhausted')
                decision, query = validate(p, context)
                fingerprint = canonical((query.generated_sql, query.parameters)) if query else None
                if fingerprint is not None and fingerprint in attempted_queries:
                    decision = SecurityDecision(Decision.INVALID_QUERY, 'repeated_query_without_progress', query.query_id)
                    result = ExploratoryQueryResult(query.query_id, limitations=('Repeated SQL does not add evidence on a pinned snapshot.',))
                else:
                    if fingerprint is not None: attempted_queries.add(fingerprint)
                    progress(f'Investigando: consulta {query_attempts}')
                    # SQL is blocking; run only this one query in a worker so SIGINT
                    # can set the existing interrupt/cancellation event.
                    if cancel is None:
                        decision, result = executor.execute(p, context)
                    else:
                        decision, result = await asyncio.to_thread(executor.execute, p, context, cancel=cancel)
                if result.status != 'COMPLETED' or decision.decision != Decision.ALLOW:
                    # Return failures to the model before executing further work.
                    pending_queries.clear()
                relations = [profile_relation(r, tables) for r in p.candidate_relations]
                rows = observation_rows(query, result)
                if cancel and cancel.is_set():
                    raise RuntimeError('cancelled_by_user')
                authorize(context)
                verification_started = time.monotonic()
                manifest = registry.register(query, result, rows)
                verification_seconds += time.monotonic()-verification_started
                if registry_factory:
                    report['independent_reference_audit'] = registry.audit
                progress('Resultados observados; comprobando evidencia')
                observation = dict(turn=len(report['turns'])+1, objective=p.objective, hypothesis=value['hypothesis'],
                    evidence_manifest=manifest,
                    decision=asdict(decision), schema=asdict(result)['schema'], rows=rows, status=result.status,
                    truncated=result.truncated or len(rows) < len(result.rows),
                    observed_result_rows=result.returned_count, disclosed_rows=len(rows),
                    ordered_prefix=bool(ordered_observation(query)),
                    sampling_guidance=(
                        'Exact prefix of the executed OUTER ORDER BY, applied before disclosure. '
                        'The undisclosed tail is incomplete, but cannot outrank these rows on that ordering. '
                        'A requested top row does not require disclosing the whole tail or repeating LIMIT 1. '
                        'Investigate ties if relevant. This does NOT accredit source completeness, classification or business meaning. '
                        'For metadata discovery ordered by code/name, this is only an incomplete entity prefix, NOT a ranking '
                        'or exhaustive family. Do not use just these codes as the full product universe. '
                        'Page by the last disclosed unique key, or inspect matching groups on the fact table; '
                        'repeating the query or changing LIMIT alone cannot disclose the tail.'
                        if ordered_observation(query) and (result.truncated or len(rows) < len(result.rows)) else
                        'Only a sample is disclosed, NOT the matching universe. Narrow the query or GROUP BY the necessary non-documentary metadata dimensions to inspect remaining entities within existing limits.'
                        if len(rows) < len(result.rows) else None),
                    publication=context.publication, snapshot=context.snapshot,
                    relationship_checks=relations,
                    independent_check='UNVERIFIED until scoped material final claims are independently reconstructed')
                report['turns'].append(dict(objective=p.objective, hypothesis=value['hypothesis'],
                    prior_observation_interpretation=value['prior_observation_interpretation'],
                    reason_for_next_query=p.justification, hypothesis_state=value['hypothesis_state'],
                    evidence_turns=value.get('evidence_turns', []), proposal=asdict(p),
                    authorized=asdict(query) if query else None, decision=asdict(decision),
                    result=asdict(result), execution_timing=getattr(executor, 'last_timing', {}),
                    model_observation=observation, independent_relationship_checks=relations))
                # A composite measure owns its pending components. Once the
                # sales-line component is observed, continue with the existing
                # investigator using the exact admitted predicates, rather than
                # relying on Luna to remember credit memos or accepting zero.
                if (required_measure == 'territorial_line_net'
                        and result.status == 'COMPLETED'
                        and ('sales_line' in p.requested_sources
                             or 'sales_line' in p.sql
                             or (manifest and manifest.get('source') == 'sales_line')
                             or (manifest and any(c.get('name') == 'line_total'
                                                   for c in manifest.get('columns', []))))
                        and not any('credit_memo_line' in (turn.get('proposal', {}).get('requested_sources') or [])
                                    for turn in report['turns'])):
                    from .business_measure import paired_component_proposal
                    # Reuse the already executed, accredited mapping observation
                    # when the sales query used an explicit warehouse predicate.
                    # Credit memo warehouse codes are not assumed identical to
                    # invoice codes; the published crosswalk supplies them.
                    mapping_codes = []
                    for mapping_manifest, _mq, _mr, mapping_rows, _mn, mapping_source in getattr(registry, 'entries', {}).values():
                        if mapping_source != 'warehouse_business_location':
                            continue
                        names = [column.name for column in mapping_manifest.columns]
                        try:
                            warehouse_index = names.index('warehouse_code')
                        except ValueError:
                            continue
                        for row in mapping_rows:
                            if isinstance(row, (list, tuple)) and warehouse_index < len(row):
                                value = row[warehouse_index]
                                if isinstance(value, str):
                                    mapping_codes.append(value)
                    scope_entity = ((effective_scope or {}).get('state') or {}).get('entity_mention')
                    if isinstance(scope_entity, dict):
                        scope_entity = scope_entity.get('text')
                    elif not isinstance(scope_entity, str):
                        scope_entity = None
                    if not scope_entity:
                        branches = ((effective_scope or {}).get('state') or {}).get('branches') or ()
                        scope_entity = branches[0] if branches else None
                    paired = paired_component_proposal(
                        p, required_measure, mapping_codes=mapping_codes,
                        territory_code=scope_entity)
                    if paired is not None:
                        report.setdefault('deterministic_continuations', []).append({
                            'component': 'credit_memo_line',
                            'source_query_turn': len(report['turns']),
                            'status': 'scheduled',
                        })
                        pending_queries.append(dict(
                            action='query', sql=paired.sql, objective=paired.objective,
                            justification=paired.justification,
                            requested_sources=list(paired.requested_sources),
                            expected_grain=paired.expected_grain,
                            expected_result=paired.expected_result,
                            candidate_relations=[asdict(r) for r in paired.candidate_relations],
                            hypothesis='Required credit-memo component of the confirmed territorial net measure',
                            prior_observation_interpretation='Sales component is already observed; execute only the pending counterpart.',
                            hypothesis_state='OPEN', evidence_turns=[]))
                history.append(observation)
                # Catch semantic contradictions while query budget remains,
                # not only after a final has exhausted it. Feedback does not
                # rewrite SQL, authorize sources or prescribe an execution.
                intent_feedback = (registry.final_feedback([], net_required=False)
                                   if hasattr(registry, 'final_feedback') else None)
                if intent_feedback:
                    feedback = dict(status='BUSINESS_SCOPE_FEEDBACK', reason=intent_feedback)
                    history.append(feedback)
                    report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                if result.status == 'COMPLETED' and 'time_to_first_useful_result_seconds' not in report:
                    report['time_to_first_useful_result_seconds'] = time.monotonic()-start
                save(report)
                if decision.decision in {Decision.DENY, Decision.RESOURCE_BLOCKED}:
                    from .authorized_foundation import binding_for
                    if decision.reason in {'join_pair_budget', 'query_deadline_or_cancel'} and binding_for(context) is not None and not (cancel and cancel.is_set()):
                        # A rejected composition is not an impossible business question.
                        history.append(dict(status='REFORMULATE', reason=decision.reason,
                            guidance='Reduce or aggregate authorized inputs within the existing budget; no authority or budget change.'))
                        continue
                    if decision.reason == 'join_pair_budget':
                        # Existing DEV precedent: summarize observed evidence,
                        # never execute an alternative route after the denial.
                        execution_closed = True
                        report['execution_closed_reason'] = decision.reason
                        terminal_rule = ('\nQuery phase is CLOSED by the join budget. Return action=final '
                                         'using only observations. Do not propose or execute any more SQL. '
                                         'State material limitations and unresolved hypotheses.')
                        luna.system = system + terminal_rule
                        report['terminal_prompt_rule'] = terminal_rule
                        continue
                    raise RuntimeError('execution_stopped:' + decision.reason)
            report['reason'] = 'model_call_budget_exhausted'
    except (RuntimeError, ValueError, asyncio.TimeoutError) as exc:
        reason = str(exc)[:180]
        report.update(status=terminal_status(reason), reason=reason)
    finally:
        authorization_lost = False
        try:
            authorize(context)
        except ValueError:
            authorization_lost = True
            # Do not disclose old observations, conversational facts or partially
            # verified results after revocation, even through error/finally paths.
            report.clear()
            report.update(status='BLOCKED', reason='authorization_changed', business_answer='',
                          publication=context.publication, snapshot=context.snapshot)
            if 'registry' in locals() and hasattr(registry, 'close'):
                registry.close()
        if not authorization_lost and registry_factory and 'registry' in locals():
            if not report.get('business_answer') and report.get('status') != 'NEEDS_CLARIFICATION':
                partial_claims = []
                for manifest, _, _, rows, _, _ in registry.entries.values():
                    for row_id, row in zip(manifest.row_ids, rows):
                        for col, amount in zip(manifest.columns, row):
                            if col.metric:
                                partial_claims.append(dict(kind='measure', result_id=manifest.result_id,
                                    column_id=col.column_id, row_id=row_id, metric=col.metric,
                                    value=str(amount), unit=col.unit, currency=col.currency, grain=col.grain,
                                    classification='observed', publication=manifest.publication,
                                    snapshot=manifest.snapshot, temporal_scope=list(manifest.temporal_scope)))
                checks = [registry.verify(c) for c in partial_claims[:60]]
                report['partial_claim_verifications'] = checks
                report['partial_verified_figures'] = sum(1 for c in checks if c.get('match'))
                if checks:
                    report['business_answer'] = ('Investigación incompleta. Resultados parciales:\n'
                                                 + registry.render(checks))
            report['evidence_manifests'] = (registry.manifests() if hasattr(registry, 'manifests')
                else [asdict(entry[0]) for entry in registry.entries.values()])
            report['independent_reference_audit'] = registry.audit
            registry.close()
        report['model_calls'] = luna.calls
        report['elapsed_seconds'] = time.monotonic()-start
        report['timing'] = dict(
            model_planning_seconds=sum(c.get('elapsed_seconds', 0) for c,v in zip(luna.calls, report.get('model_events', [])) if v.get('action') != 'final'),
            model_final_seconds=sum(c.get('elapsed_seconds', 0) for c,v in zip(luna.calls, report.get('model_events', [])) if v.get('action') == 'final'),
            executor_wall_seconds=sum(t.get('execution_timing', {}).get('total_seconds', t['result']['elapsed_seconds']) for t in report.get('turns', [])),
            sql_seconds=sum(t.get('execution_timing', {}).get('sql_seconds', 0) for t in report.get('turns', [])),
            iterations=len(report.get('model_events', [])), query_attempts=query_attempts,
            corrections=len(report.get('controller_feedback', [])),
            evidence_verification_seconds=verification_seconds,
            deterministic_render_seconds=report.get('deterministic_render_seconds', 0.0),
            model_preflight_seconds=sum(c.get('elapsed_seconds', 0) for c in report.get('model_preflight_calls', [])),
            total_seconds=report['elapsed_seconds'])
        report['resources'] = dict(peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            duckdb_threads=1, concurrency=1, duckdb_memory_limit_bytes=context.effective_budget.process_memory_bytes,
            spill_bytes=0, model_query_cap=context.effective_budget.queries, reference_query_cap=context.effective_budget.queries if registry_factory else len(reference_proposals()),
            query_timeout_seconds=context.effective_budget.query_seconds,
            per_phase_sql_seconds=context.effective_budget.total_seconds, observation_bytes_limit=32768,
            own_processes_left_running=0, unrelated_processes_terminated=0)
        report['cost'] = None  # No accredited pricing supplied; usage is retained per call.
        try:
            authorize(context)  # Reference reconstruction can itself take time.
        except ValueError:
            report.clear()
            report.update(status='BLOCKED', reason='authorization_changed', business_answer='')
        save(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-dev-io-exception', action='store_true', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(f'/tmp/telchi-exploratory-dev-{os.getuid()}.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with output.open('x'):
            pass
        def save(report):
            pending = output.with_suffix('.pending')
            pending.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+'\n')
            os.replace(pending, output)
        report = dict(timestamp=datetime.now(timezone.utc).isoformat(), environment='DEV',
                      owner_authorization='Mario: this test only; minimal business egress and bounded I/O-only exception',
                      host_preflight=host_read_preflight(), whatsapp='UNCHANGED / NOT_RUN', web='UNCHANGED / NOT_RUN')
        try:
            asyncio.run(run(report, save))
        except Exception as exc:
            report.update(status='BLOCKED', reason=type(exc).__name__+':'+str(exc)[:120])
            save(report)
        print(canonical(dict(status=report.get('status'), reason=report.get('reason'), output=str(output))))


if __name__ == '__main__':
    main()
