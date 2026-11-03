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


def bounded_payload(payload):
    """Compact prior samples, never expand the byte budget or hide truncation."""
    import copy
    compact = copy.deepcopy(payload)
    if len(canonical(compact).encode()) > 32768 and 'catalog' in compact:
        # Discovery can expose many published schemas. Compact redundant field
        # labels only; do not drop sources, columns, types or semantic limits.
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
    for observation in compact['observations']:
        if observation.get('evidence_manifest'):
            observation.pop('schema', None)  # schema is already in the manifest
    if len(canonical(compact).encode()) > 32768:
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
    if len(canonical(compact).encode()) > 32768:
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
        if len(canonical(compact).encode()) <= 32768:
            break
        rows = observation.get('rows', ())
        if len(rows) > 3 and observation.get('evidence_manifest'):
            observation['rows'] = rows[:3]
            observation['evidence_manifest']['row_ids'] = observation['evidence_manifest']['row_ids'][:3]
            observation['truncated'] = True
            observation['history_compacted'] = True
    if len(canonical(compact).encode()) > 32768:
        for observation in compact['observations']:
            if not observation.get('evidence_manifest'): continue
            # Model-authored rationale is already audited; it is not evidence.
            observation.pop('hypothesis', None)
            observation.pop('objective', None)
            if observation.get('decision', {}).get('decision') == 'ALLOW':
                observation['decision'] = {'decision': 'ALLOW'}
    if len(canonical(compact).encode()) > 32768:
        raise RuntimeError('observation_byte_budget')
    return compact


async def run(report, save, *, luna=None, executor_factory=AdaptiveExecutor, wall_seconds=1200,
              question=QUESTION, conversation=(), context=None, system=SYSTEM,
              registry_factory=None, progress=lambda event: None, cancel=None):
    start = time.monotonic()
    context = context or context_for_run()
    authorize(context)
    catalog = context.catalog
    luna = luna or LunaSQL(system=system, max_output_tokens=8192)
    progress('Verificando modelo y autorización DEV')
    report.update(identifier='TELCHIAI_ADAPTIVE_BUSINESS_RESEARCH_V1', question=question,
        universe='catalog-authorized population' if registry_factory else ['L02822', 'L02823', 'L03658', 'L03649'], publication=context.publication, snapshot=context.snapshot,
        code_digest=code_digest(), catalog=asdict(catalog), system_prompt=system,
        budget=asdict(context.effective_budget), wall_seconds=wall_seconds, status='PARTIAL',
        turns=[], model_events=[], reference_queries=[], model_configuration=dict(model='gpt-5.6-luna',
        reasoning='medium', fallback=False, store=False, provider='OpenAI Responses direct',
        max_output_tokens=8192, calls_cap=16),
        limits=['local supervised DEV identity, not Console RBAC', 'no OS isolation accreditation',
                'DuckDB memory limit is not a process RSS limit', 'attachment setup is not OS-preemptible',
                'no historical classification or complete-month certification', 'narrative is not certified by arithmetic'])
    history = []
    premature_final_feedback = False
    verification_repairs = 0
    rejected_fingerprints = set()
    attempted_queries = set()
    query_attempts = 0
    execution_closed = False
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
                if time.monotonic() - start >= wall_seconds:
                    raise RuntimeError('research_wall_budget')
                decision, result = controls.execute(p, context)
                report['reference_queries'].append(dict(proposal=asdict(p), decision=asdict(decision), result=asdict(result)))
                save(report)
                if result.status != 'COMPLETED' or result.truncated:
                    raise RuntimeError('independent_reference_blocked:' + decision.reason)
                results.append(result)
        if registry_factory:
            tables, summary = {}, {'state': 'PER_RESULT_BOUNDED_REFERENCE', 'full_population_reconciled': False}
            registry = registry_factory(context)
        else:
            tables, summary = reconstruct(context, results)
            registry = EvidenceRegistry(context, tables, (START, END))
        report['identifier'] = 'TELCHIAI_ANALYTICAL_CLAIM_VERIFICATION_V1'
        report['independent_business_reconciliation'] = summary
        save(report)
        with executor_factory(context, authorized=True) as executor:
            for call in range(16):
                remaining = wall_seconds - (time.monotonic() - start)
                if remaining <= 0 or executor.cancel.is_set() or (cancel and cancel.is_set()):
                    raise RuntimeError('research_deadline_or_memory_pressure')
                authorize(context)  # Includes live revocation for issued phase-B contexts.
                progress('Analizando observaciones con Luna')
                payload = dict(question=question, current_date=datetime.now(timezone.utc).date().isoformat(),
                               conversation=list(conversation), catalog=asdict(catalog), observations=list(history),
                               execution_closed=execution_closed,
                               remaining_query_budget=0 if execution_closed else context.effective_budget.queries-query_attempts)
                payload = bounded_payload(payload)
                report.setdefault('model_input_sizes', []).append(len(canonical(payload).encode()))
                value = await asyncio.wait_for(luna.next(payload, timeout=min(90, remaining)), remaining)
                authorize(context)  # Model latency must not preserve a revoked scope.
                report['model_calls'] = luna.calls
                report['model_events'].append(value)
                save(report)
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
                    if not isinstance(claims, list) or len(claims) > 60:
                        raise RuntimeError('invalid_final_claims')
                    report['model_answer'] = value['answer']
                    report['model_conclusions'] = value.get('conclusions', [])
                    progress('Verificando afirmaciones independientemente')
                    report['claim_verifications'] = [registry.verify(c) for c in claims]
                    checks = report['claim_verifications']
                    report.setdefault('final_reviews', []).append(dict(
                        proposed_answer=value, claim_verifications=checks))
                    mismatches = [c for c in checks if not c['match']]
                    fingerprint = canonical([c['claim'] for c in mismatches])
                    if mismatches and verification_repairs < 3 and fingerprint not in rejected_fingerprints:
                        rejected_fingerprints.add(fingerprint)
                        verification_repairs += 1
                        feedback = verification_feedback(checks)
                        history.append(feedback)
                        report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                        save(report)
                        continue
                    complete = not registry_factory or value.get('coverage') == 'COMPLETE'
                    report['question_coverage'] = 'MODEL_DECLARED_COMPLETE_NOT_INDEPENDENTLY_CERTIFIED' if complete else 'PARTIAL'
                    report['status'] = ('VERIFIED_WITH_LIMITATIONS' if checks and not mismatches and complete else 'PARTIAL')
                    report['business_answer'] = registry.render(checks)
                    if not complete:
                        report['business_answer'] += '\nLa pregunta tiene partes pendientes; las cifras anteriores son solo una respuesta parcial.'
                    report['evidence_manifests'] = [asdict(entry[0]) for entry in registry.entries.values()]
                    report['narrative_state'] = 'RAW_MODEL_PROSE_AUDIT_ONLY; delivered facts rendered from verified evidence'
                    report['unresolved_claim_count'] = len(mismatches)
                    report['hypothesis_revision'] = dict(reviews=len(report['final_reviews']),
                        rejected_claims=sum(not c['match'] for review in report['final_reviews'] for c in review['claim_verifications']),
                        repeated_without_progress=bool(mismatches and fingerprint in rejected_fingerprints))
                    report['final_observation_interpretation'] = value.get('prior_observation_interpretation')
                    return
                if execution_closed:
                    raise RuntimeError('query_phase_closed_no_further_sql')
                query_attempts += 1
                report['query_attempts'] = query_attempts
                if query_attempts > context.effective_budget.queries:
                    raise RuntimeError('query_attempt_budget_exhausted')
                try:
                    p = model_proposal(value)
                except (ValueError, TypeError, KeyError) as exc:
                    feedback = dict(status='INVALID_QUERY', reason=str(exc)[:100])
                    history.append(feedback)
                    report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                    save(report)
                    continue
                if any(r > len(report['turns']) for r in value.get('evidence_turns', [])):
                    feedback = dict(status='INVALID_QUERY', reason='unknown_evidence_turn', available_turns=len(report['turns']))
                    history.append(feedback)
                    report.setdefault('controller_feedback', []).append(dict(call=call+1, **feedback))
                    save(report)
                    continue
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
                relations = [profile_relation(r, tables) for r in p.candidate_relations]
                rows = observation_rows(query, result)
                if cancel and cancel.is_set():
                    raise RuntimeError('cancelled_by_user')
                authorize(context)
                manifest = registry.register(query, result, rows)
                if registry_factory:
                    report['independent_reference_audit'] = registry.audit
                progress('Resultados observados; comprobando evidencia')
                observation = dict(turn=len(report['turns'])+1, objective=p.objective, hypothesis=value['hypothesis'],
                    evidence_manifest=manifest,
                    decision=asdict(decision), schema=asdict(result)['schema'], rows=rows, status=result.status,
                    truncated=result.truncated or len(rows) < len(result.rows),
                    publication=context.publication, snapshot=context.snapshot,
                    relationship_checks=relations,
                    independent_check='UNVERIFIED until scoped material final claims are independently reconstructed')
                report['turns'].append(dict(objective=p.objective, hypothesis=value['hypothesis'],
                    prior_observation_interpretation=value['prior_observation_interpretation'],
                    reason_for_next_query=p.justification, hypothesis_state=value['hypothesis_state'],
                    evidence_turns=value.get('evidence_turns', []), proposal=asdict(p),
                    authorized=asdict(query) if query else None, decision=asdict(decision),
                    result=asdict(result), model_observation=observation, independent_relationship_checks=relations))
                history.append(observation)
                if result.status == 'COMPLETED' and 'time_to_first_useful_result_seconds' not in report:
                    report['time_to_first_useful_result_seconds'] = time.monotonic()-start
                save(report)
                if decision.decision in {Decision.DENY, Decision.RESOURCE_BLOCKED}:
                    from .authorized_foundation import binding_for
                    if decision.reason == 'join_pair_budget' and binding_for(context) is not None:
                        # A rejected composition is not an impossible business question.
                        history.append(dict(status='REFORMULATE', reason='join_pair_budget',
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
        report.update(status='BLOCKED', reason=str(exc)[:180])
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
            if 'registry' in locals():
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
                report['business_answer'] = 'Investigación incompleta. Resultados parciales:\n' + registry.render(checks)
            report['evidence_manifests'] = [asdict(entry[0]) for entry in registry.entries.values()]
            report['independent_reference_audit'] = registry.audit
            registry.close()
        report['model_calls'] = luna.calls
        report['elapsed_seconds'] = time.monotonic()-start
        report['resources'] = dict(peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            duckdb_threads=1, concurrency=1, duckdb_memory_limit_bytes=context.effective_budget.process_memory_bytes,
            spill_bytes=0, model_query_cap=12, reference_query_cap=context.effective_budget.queries if registry_factory else len(reference_proposals()),
            query_timeout_seconds=120, per_phase_sql_seconds=900, observation_bytes_limit=32768,
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
