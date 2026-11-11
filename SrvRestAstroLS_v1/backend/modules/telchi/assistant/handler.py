"""Real MessageHandler. Messaging retains reception, execution fence and delivery."""
import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from time import perf_counter
from modules.telchi.datalake.query_profile import span

from modules.console.repositories import PermissionConsoleRepository
from modules.db.transaction import transaction
from modules.messaging.delivery_guard import guard_outbound
from modules.messaging.handlers import HandlerRegistration, MessageResult

from . import state_engine, business_scope
from .capabilities import SalesCapabilities, ProductResolutionError, format_result, business_date, business_money
from .luna import LunaError, LunaInterpreter
from .repository import ConversationRepository
from . import result_references
from modules.telchi.datalake.invoice_lines_query import CAPABILITY as INVOICE_LINES, PERMISSION as INVOICE_PERMISSION


@dataclass(frozen=True)
class BusinessPolicy:
    tenant_id: str
    workspace_id: str
    permission: str | None  # Legacy HTTP policy only; pilot access is not a commercial grant.
    module_enabled: bool = False
    whole_workspace_scope_verified: bool = False  # Unsupported scoped grants must fail closed.

    pilot_access_check: object = None
    pilot_approval_sha256: str | None = None
    pilot_user_id: str | None = None

    def __post_init__(self):
        if (not all((self.tenant_id, self.workspace_id)) or self.permission == ''
                or (self.permission is None and (not callable(self.pilot_access_check)
                                                 or not self.pilot_user_id))):
            raise ValueError('approved_business_policy_required')


class BusinessAuthorization:
    def __init__(self, policy):
        self.policy = policy

    def enterprise_context(self, context):
        """Label the module's company only within the resolved, authorized workspace.

        Called after effective authorization. Never derive tenant/aliases from text
        or semantic retrieval; this module has no company mapping for other tenants.
        """
        p, c, i = self.policy, context.channel, context.sender_identity
        if (i is None or p.tenant_id != 'telchi' or c.module != 'telchi'
                or c.tenant_id != p.tenant_id or c.workspace_id != p.workspace_id
                or i.tenant_id != c.tenant_id or i.workspace_id != c.workspace_id
                or i.environment != c.environment):
            return None
        return dict(source='authenticated_team360_workspace', tenant_id=c.tenant_id,
                    workspace_id=c.workspace_id, own_company={'name': 'Telchi', 'aliases': []})

    async def allowed(self, context, conn=None, *, required_permission=None):
        p, c, i = self.policy, context.channel, context.sender_identity
        if p.pilot_access_check is not None:
            try:
                p.pilot_access_check()
            except Exception:
                return False
        if (i is None or not i.user_id or (p.pilot_user_id is not None and i.user_id != p.pilot_user_id)
                or c.module != 'telchi' or c.environment != 'dev'
                or i.environment != c.environment or i.tenant_id != c.tenant_id
                or i.workspace_id != c.workspace_id or c.tenant_id != p.tenant_id
                or c.workspace_id != p.workspace_id or not p.module_enabled
                or not p.whole_workspace_scope_verified or context.public_capabilities
                or (p.permission is not None and p.permission not in i.permissions)):
            return False
        if required_permission is not None and (p.tenant_id != 'telchi' or required_permission not in i.permissions):
            return False
        # Live checks use the existing Console resolver; no WhatsApp-specific grants.
        if conn is not None:
            from modules.telchi.datalake.operational_query import PERMISSIONS as operational_permissions
            if required_permission in operational_permissions.values():
                from modules.telchi.provisioning.operational_repository import OperationalRegistrationRepository
                metric = next(m for m, p in operational_permissions.items() if p == required_permission)
                if not await OperationalRegistrationRepository().registered(conn, p.workspace_id, metric):
                    return False
            permissions = await PermissionConsoleRepository().list_effective_permissions(
                conn, p.workspace_id, i.user_id)
            return ((p.permission is None or p.permission in permissions)
                    and (required_permission is None or required_permission in permissions))
        return True


class PostgresConversationStore:
    def __init__(self, pool, repository=None):
        self.pool, self.repository = pool, repository or ConversationRepository()

    @asynccontextmanager
    async def turn(self, context):
        # Load and lock only the short state transition. Investigation is durable
        # work, not a conversation transaction: release the row/advisory locks
        # before Luna or exploratory SQL can run for minutes or hours.
        pool = self.pool() if callable(self.pool) else self.pool
        async with pool.connection() as conn:
            async with conn.transaction():
                turn = await self.repository.load(conn, context)
            yield turn

    async def save(self, context, turn, audit):
        # Authorization/interpreter reads may have opened an implicit transaction
        # after load. Close it before the atomic state/audit write.
        conn = turn['conn']
        await conn.commit()
        async with conn.transaction():
            await self.repository.save(conn, context, turn, audit)


class TelchiHandler:
    # Result/state/audit commit atomically; replay revalidates live RBAC.
    durable_replay_safe = True

    def __init__(self, *, store, authorization, interpreter=None, capabilities=None,
                 turn_timeout_seconds=80, engine=state_engine.process, concept_resolver=None,
                 semantics_connection=None, researcher=None):
        self.store, self.authorization = store, authorization
        self.interpreter = interpreter or LunaInterpreter()
        self.capabilities = capabilities or SalesCapabilities()
        self.turn_timeout_seconds, self.engine = turn_timeout_seconds, engine
        self.concept_resolver = concept_resolver
        self.semantics_connection = semantics_connection
        # Optional in-process free-analysis port. Composition supplies it only
        # under an explicit DEV opt-in; absent, behavior is exactly as before.
        self.researcher = researcher

    async def handle(self, message, context):
        denied = MessageResult('No se pudo autorizar esta consulta de Telchi.', context.correlation_id, 'DENIED')
        async def process_turn():
            with span('authorization_initial'):
                allowed = await self.authorization.allowed(context)
            if not allowed:
                return denied  # zero LLM and capability calls
            async with self.store.turn(context) as turn:
                with span('authorization_transaction_revalidation'):
                    allowed = await self.authorization.allowed(context, turn.get('conn'))
                if not allowed:
                    return denied
                if turn.get('cached'):
                    cached = turn['cached']
                    if (cached.get('required_permission') and not await self.authorization.allowed(
                            context, turn.get('conn'), required_permission=cached['required_permission'])):
                        return denied
                    if cached.get('monetary_calculation') and not all([
                            await self._reference_allowed(cached['monetary_calculation'][key], context, turn.get('conn'))
                            for key in ('target', 'baseline')]):
                        return denied
                    if cached.get('business_rbac_verified') and not await self._operation_permissions_allowed(
                            cached['confirmed_state'], context, turn.get('conn')):
                        return denied
                    if cached.get('decision') == 'RESEARCH' or cached.get('research_reference'):
                        receipt = (cached.get('research') or {}).get('recovery')
                        if (not receipt or self.researcher is None
                                or not hasattr(self.researcher, 'revalidate')
                                or not await self.researcher.revalidate(context, receipt)):
                            return denied
                    response = cached['response_prepared']
                    return MessageResult(response['text'], context.correlation_id, response['classification'])
                result, audit = await self._process(message, context, turn)
                with span('conversation_audit_save'):
                    await self.store.save(context, turn, audit)
            return result
        try:
            # The legacy request deadline remains a technical admission guard for
            # the fast path. An accepted investigation is deliberately not inside
            # it: channel/request lifetime cannot cancel durable research.
            if self.researcher is not None or self.turn_timeout_seconds is None:
                return await process_turn()
            async with asyncio.timeout(self.turn_timeout_seconds):
                return await process_turn()
        except Exception:
            return MessageResult('No se pudo completar la consulta. No hay un resultado confirmado.',
                                 context.correlation_id, 'ERROR')

    async def _process(self, message, context, turn):
        from uuid import uuid4
        handler_started = perf_counter()
        command = message.text_body.strip().casefold()
        previous_turn = next(reversed(turn['history']), None)
        from .operational import unsupported_followup
        # A legacy shortcut describes a catalog limit, not a SourcePolicy veto.
        # With research enabled Luna must interpret the full question instead.
        unavailable = (unsupported_followup(message.text_body, turn['state'])
                       if self.researcher is None else None)
        if unavailable:
            result = MessageResult(unavailable, context.correlation_id, 'DIRECT_UNAVAILABLE')
            audit = dict(owner=turn['owner'], previous_state=deepcopy(turn['state']),
                interpretation_proposed=None, confirmed_state=deepcopy(turn['state']),
                decision='UNSUPPORTED_SUPPLIER_RANKING', execution_status='not_executed',
                execution_result=None, capability_calls=0, required_permission=None,
                response_prepared=dict(text=result.text, classification=result.classification))
            new = False
        elif command in {'continuar', 'nueva consulta'}:
            new = command == 'nueva consulta'
            state = deepcopy(state_engine.EMPTY if new else turn['state'])
            text = ('Empecemos una nueva consulta. ¿Qué querés analizar?'
                    if new else 'Conservo el contexto de este análisis. ¿Qué querés profundizar?')
            result = MessageResult(text, context.correlation_id, 'NEEDS_CLARIFICATION')
            audit = dict(owner=turn['owner'], previous_state=deepcopy(turn['state']),
                interpretation_proposed={'intent': 'NEW_QUERY' if new else 'CONTINUE'},
                confirmed_state=state, decision='NEW_QUERY' if new else 'CONTINUE',
                execution_status='not_executed', execution_result=None, capability_calls=0,
                required_permission=None, response_prepared=dict(text=text, classification=result.classification))
        else:
            result, audit = await self._process_business(message, context, turn)
            # Research is the normal path outside a fully represented accelerator.
            # No valid commercial contract is required. Actual denials and failed
            # authorization/integrity checks remain terminal, never fallbacks.
            if (audit.get('decision') not in {'DENIED', 'ERROR', 'LUNA_TECHNICAL_FAILURE'}
                    and not audit.get('business_rbac_verified')
                    and (audit.get('bmd') or {}).get('category') in RESEARCH_CATEGORIES):
                researched = await self._research_fallback(message, context, turn, audit)
                if researched is not None:
                    result = researched
            new = (audit.get('committed') is True
                   and audit.get('execution_status') != 'failed'
                   and audit.get('decision') not in {'DENIED', 'ERROR', 'EXECUTION_FORBIDDEN'}
                   and (audit.get('interpretation_proposed') or {}).get('intent') == 'NEW_QUERY')
        # One logical outbound: answer first, controls last, including a safe
        # unavailable/clarification response. Never assume native button support.
        from .conversation_controls import with_options
        # Rejected interpretations and unsupported comparisons must remain
        # terminal, not invite continuation of a plan that cannot be executed.
        terminal = (audit.get('decision') == 'EXECUTION_FORBIDDEN'
                    or (audit.get('bmd') or {}).get('category') in TERMINAL_CATEGORIES)
        text = result.text if terminal else with_options(result.text)
        result = MessageResult(text, result.correlation_id, result.classification)
        audit['response_prepared'] = dict(text=text, classification=result.classification)
        if new:
            if (command == 'nueva consulta' or turn['state'] != state_engine.EMPTY
                    or 'analysis_context_id' not in turn):
                turn['analysis_context_id'] = str(uuid4())
            turn['history'] = {}
            turn['result_reference'] = None
            turn['document_reference'] = None
            turn['monetary_comparison'] = None
        audit.update(conversation_id=context.conversation_id, turn_id=context.correlation_id,
            analysis_context_id=turn.get('analysis_context_id', context.conversation_id),
            parent_turn_id=None if new else previous_turn)
        audit.setdefault('timings', {})['handler_total_ms'] = (perf_counter() - handler_started) * 1000
        return result, audit

    async def _research_fallback(self, message, context, turn, audit):
        """Free analysis through the single existing investigator, in process.

        No HTTP hop to Console, no second engine, no per-question capability. The
        port owns fresh authorization (before execution and before disclosure),
        read-only SQL validation, Foundation CURRENT binding and audit. On any
        failure we keep the accredited capability-gap answer instead of inventing
        a result; the attempt stays auditable.
        """
        if self.researcher is None:
            return None
        phase = perf_counter()
        try:
            options = ({'analysis_context_id': turn.get('analysis_context_id', context.conversation_id)}
                       if hasattr(self.researcher, 'result_reference') else {})
            # The investigator receives the same effective scope receipt as the
            # capability path. It must not rebuild filters from the prior turn.
            # A representation gap may be routed to durable research after the
            # State Engine has validated a new scope.  Use that validated scope,
            # not the previously committed conversation state; otherwise a
            # clarification such as "Todos los canales" loses its territorial
            # entity before SQL planning begins.
            state = deepcopy(audit.get('validated_state') or
                             audit.get('confirmed_state') or turn.get('state') or {})
            contract = deepcopy(audit.get('business_scope') or state.get('scope_contract') or {})
            inherited = {
                key: state[key] for key in (
                    'metric', 'period', 'periods', 'period_mode', 'branches', 'sales_channel',
                    'product_target', 'customer_target', 'business_category', 'group_by',
                    'entity_mention')
                if state.get(key)
            }
            territorial = bool(state.get('branches') or state.get('entity_mention'))
            question = message.text_body
            if territorial and state.get('metric') == 'sales.net_amount':
                # The territorial contract is explicitly the accredited line
                # measure; header DocTotal cannot be attributed to a warehouse
                # grouping. Keep the conversational metric unchanged for
                # continuity, but make the research obligation unambiguous.
                question += ('\nContrato territorial confirmado: responder neto de líneas comerciales '
                             '(sales_line.line_total menos credit_memo_line.line_total), '
                             'no neto documental de cabeceras; no pedir una aclaración de medida.')
            audit.setdefault('scope_trace', []).append(
                business_scope.scope_audit_entry(contract, 'research_handoff', source='handler'))
            scope_payload = dict(question=message.text_body, effective_scope=contract,
                                 state=state, source='backend_confirmed_scope')
            if territorial and state.get('metric') == 'sales.net_amount':
                scope_payload['territorial_measure'] = 'commercial_line_net_amount'
                scope_payload['territorial_entity_required'] = True
            if inherited and contract.get('intent') not in {'NEW_QUERY'}:
                scope_payload['context'] = inherited
            import inspect
            researcher_call = getattr(self.researcher, '__call__', self.researcher)
            supports_scope = (hasattr(self.researcher, 'accepts_business_knowledge')
                              or 'effective_scope' in inspect.signature(researcher_call).parameters)
            if supports_scope:
                options['effective_scope'] = scope_payload
            elif inherited and contract.get('intent') not in {'NEW_QUERY'}:
                # Compatibility only for legacy in-process test doubles that
                # cannot consume the structured receipt. The real port always
                # receives effective_scope and must not reconstruct from prose.
                legacy_context = {key: (turn.get('state') or {}).get(key) for key in inherited
                                  if (turn.get('state') or {}).get(key)}
                question += '\nContexto previo confirmado (datos; solo para seguimientos, no para una consulta independiente): ' + json.dumps(legacy_context, ensure_ascii=False)
            if hasattr(self.researcher, 'accepts_business_knowledge'):
                # Reuse the authorized semantic receipt, except for territorial
                # line reconciliation: its published crosswalk and exact join
                # contract are the authoritative knowledge, while retransmitting
                # the broad resolver payload consumes the fixed observation wire
                # budget before Luna can issue the two required aggregates.
                territorial = bool(state.get('branches') or state.get('entity_mention'))
                options['business_knowledge'] = (
                    None if territorial and state.get('metric') == 'sales.net_amount'
                    else audit.get('business_semantics'))
            known_measure = getattr(self.researcher, 'execute_known_measure', None)
            if known_measure is not None and territorial and state.get('metric') == 'sales.net_amount':
                report = await known_measure(context, scope_payload)
                audit['research'] = {
                    'status': report.get('status'),
                    'reason': None,
                    'routing_category': 'KNOWN_TERRITORIAL_LINE_NET',
                    'publication': report.get('publication'),
                    'snapshot': report.get('snapshot'),
                    'question_coverage': 'VERIFIED_WITH_LIMITATIONS',
                    'model_calls': [],
                    'sql_executions': report.get('sql_executions'),
                    'elapsed_seconds': 0,
                    'required_measure': report.get('required_measure'),
                    'deterministic_continuations': [],
                    'deterministic_contract_completion': report.get('deterministic_contract_completion'),
                    'evidence': report.get('evidence'),
                }
                audit.update(
                    decision='EXECUTE', business_rbac_verified=True,
                    execution_status='executed',
                    known_measure_execution=True,
                    execution_result=report.get('deterministic_contract_completion'))
                return MessageResult(report['business_answer'], context.correlation_id,
                                     'DIRECT_AVAILABLE')
            report = await self.researcher(question, context.conversation_id, context, **options)
        except Exception:
            if getattr(self.researcher, 'recovery_repository', None) is not None:
                # Do not commit a catalog-gap answer over a recoverable research
                # failure. Roll back the turn; DurableWorker owns the retry.
                raise
            audit['timings']['research_ms'] = (perf_counter() - phase) * 1000
            audit['research'] = {'status': 'ERROR', 'reason': 'researcher_unavailable'}
            return None
        audit['timings']['research_ms'] = (perf_counter() - phase) * 1000
        status = report.get('status')
        text = report.get('business_answer') or report.get('clarification') or ''
        audit['research'] = {'status': status or 'BLOCKED', 'reason': report.get('reason', ''),
                             # Why free analysis was the path: the exact catalog
                             # category that could not express this question.
                             'routing_category': (audit.get('bmd') or {}).get('category'),
                             'publication': report.get('publication'),
                             'snapshot': report.get('snapshot'),
                             'question_coverage': report.get('question_coverage'),
                             'model_calls': report.get('model_calls'),
                             'sql_executions': report.get('sql_executions'),
                             'elapsed_seconds': report.get('elapsed_seconds'),
                             'required_measure': report.get('required_measure'),
                             'deterministic_continuations': report.get('deterministic_continuations'),
                             'deterministic_contract_completion': report.get('deterministic_contract_completion'),
                             'recovery': report.get('_recovery')}
        if status == 'BLOCKED' and report.get('reason') in {
                'execution_stopped:host_io_or_memory_pressure',
                'execution_stopped:query_deadline_or_cancel',
                'execution_stopped:research_budget_exhausted',
                'model_call_budget_exhausted'}:
            # A safe environmental stop is not a commercial catalog rejection.
            # No unverified partial figures, exception text or authority changes.
            audit.update(decision='RESEARCH_BLOCKED', committed=False,
                         execution_status='not_completed',
                         confirmed_state=deepcopy(audit.get('validated_state') or turn['state']))
            audit['bmd'] = {'category': 'RESEARCH_RESOURCE_BLOCKED'}
            return MessageResult('La investigación se detuvo por un límite de recursos o de ejecución. '
                                 'No tengo una respuesta completa acreditada; no es un rechazo '
                                 'por falta de una capability comercial.',
                                 context.correlation_id, 'DIRECT_UNAVAILABLE')
        if status == 'RESOURCE_LIMITED':
            # A real processing limit is classified as such: never a missing
            # capability, a denied source or an absent data period. A verified
            # partial result is delivered with its material limitation.
            limit = report.get('observation_budget') or {}
            audit.update(decision='RESEARCH_RESOURCE_LIMITED', committed=False,
                         execution_status='not_completed', required_permission=None,
                         confirmed_state=deepcopy(audit.get('validated_state') or turn['state']),
                         research_limit=dict(reason=report.get('reason'), **{
                             k: limit[k] for k in ('limit', 'measured_bytes') if k in limit}))
            audit['bmd'] = {'category': 'RESEARCH_RESOURCE_LIMITED'}
            limitation = ('La investigación alcanzó su límite de procesamiento por turno y no pudo completar '
                          'la respuesta. No es un rechazo de la capability comercial, ni una fuente no autorizada, '
                          'ni un dato inexistente.')
            verified = text.strip()
            return MessageResult((verified + '\n\n' if verified else '') + limitation,
                                 context.correlation_id, 'DIRECT_UNAVAILABLE')
        if status not in {'READY', 'VERIFIED_WITH_LIMITATIONS',
                          'EXECUTOR_OBSERVED_WITH_LIMITATIONS', 'PARTIAL',
                          'NEEDS_CLARIFICATION'} or not text.strip():
            return None
        clarification = status == 'NEEDS_CLARIFICATION'
        partial = status == 'PARTIAL'
        audit.update(decision='RESEARCH', committed=False,
                     execution_status='not_executed' if clarification else 'executed',
                     required_permission=None,
                     confirmed_state=deepcopy(audit.get('validated_state') or turn['state']))
        # Preserve the actual interpreter output and rejected plan for diagnosis.
        # Research never confers capability execution authority on that plan.
        audit['bmd'] = {'category': ('RESEARCH_CLARIFICATION' if clarification else
                                     'RESEARCH_PARTIAL' if partial else 'RESEARCH_ANSWER')}
        # A partial investigation (including one with no checked figures) is not
        # a correctly answered turn. Keep useful partial facts, never label it as
        # a completed business answer for delivery/quality metrics.
        return MessageResult(text, context.correlation_id,
                             'NEEDS_CLARIFICATION' if clarification else
                             'DIRECT_UNAVAILABLE' if partial else 'DIRECT_AVAILABLE')

    async def _process_business(self, message, context, turn):
        origin = perf_counter()
        timings = dict(interpretation_ms=0.0, state_engine_ms=0.0, capability_ms=0.0, response_format_ms=0.0)
        before = deepcopy(turn['state'])
        audit = dict(owner=turn['owner'], previous_state=before, interpretation_proposed=None,
                     validated_state=None, confirmed_state=before, decision='ERROR',
                     execution_status='not_executed', execution_result=None, capability_calls=0,
                     required_permission=None, bmd=None, timings=timings,
                     pilot_approval_sha256=self.authorization.policy.pilot_approval_sha256)
        if (self.researcher is not None and hasattr(self.researcher, 'has_recovery')
                and await self.researcher.has_recovery(context)):
            # The original inbox already chose research. Never spend another
            # interpretation/model call (or change routes) to recover its result.
            audit.update(decision='DIRECT_UNAVAILABLE', bmd={'category': 'CAPABILITY_MISSING'})
            return MessageResult('No hay un resultado confirmado.', context.correlation_id,
                                 'DIRECT_UNAVAILABLE'), audit
        classification, text = 'ERROR', 'No pude interpretar la consulta. No se ejecutó ninguna consulta.'
        phase = perf_counter()
        semantics = None
        technical_failure = None
        monetary_results = []
        try:
            from . import business_scope
            interpretation_args = dict(text=message.text_body, state=deepcopy(before),
                                       history=deepcopy(turn['history']), turn_id=context.correlation_id,
                                       enterprise_context=self.authorization.enterprise_context(context),
                                       business_scope=business_scope.scope(before))
            if self.concept_resolver is not None:
                from modules.business_semantics.resolver import luna_context
                async with self._semantics_turn(turn) as semantic_conn:
                    repo = self.concept_resolver.repository
                    scope = await repo.scope(semantic_conn, context.channel.workspace_id, context.channel.tenant_id)
                    semantics = await self.concept_resolver.resolve(semantic_conn,
                        organization_id=scope['organization_id'], workspace_id=context.channel.workspace_id,
                        module='telchi', actor_id=context.sender_identity.user_id, text=message.text_body,
                        context=before, observe_unknown=True)
                    if self.semantics_connection is not None:
                        # Evidence from the very connection used by retrieval,
                        # not inferred from a DSN or startup configuration.
                        semantics['connection'] = await repo.connection_identity(semantic_conn)
                if self.researcher is not None and hasattr(self.researcher, 'filter_business_knowledge'):
                    semantics = await self.researcher.filter_business_knowledge(semantics, context)
                audit['business_semantics'] = semantics
                interpretation_args['business_semantics'] = luna_context(semantics)
                # A semantic guard must not bypass Luna when the real research port
                # can consume the structured business scope and the user may need a
                # conversational clarification. Legacy test doubles retain the old
                # direct-research route for compatibility.
                if (self.researcher is not None
                        and not hasattr(self.researcher, 'filter_business_knowledge')
                        and semantics.get('semantic_guard', {}).get('requires_clarification')):
                    audit.update(committed=False, decision='RESEARCH_REQUESTED',
                                 bmd={'category': 'RESEARCH_REQUESTED',
                                      'reason': 'commercial_semantic_contract_unrepresentable'})
                    timings['interpretation_ms'] = (perf_counter() - phase) * 1000
                    return MessageResult('No hay un resultado de investigación confirmado.',
                                         context.correlation_id, 'DIRECT_UNAVAILABLE'), audit
                if (self.researcher is None
                        and semantics.get('semantic_guard', {}).get('requires_clarification')):
                    # Do not let Luna replace a rejected entity/direction with an
                    # unfiltered global plan. Preserve prior state, no pending plan
                    # or execution authority is fabricated by a lexical veto.
                    text = ('No puedo aplicar esa definición empresarial a la entidad o relación indicada. '
                            '¿Consultás ventas en sucursales, ventas de productos o a clientes; '
                            'o deuda que nos deben clientes frente a deuda que debemos pagar? '
                            'No se ejecutó ninguna consulta.')
                    result = MessageResult(text, context.correlation_id, 'NEEDS_CLARIFICATION')
                    timings['interpretation_ms'] = (perf_counter() - phase) * 1000
                    timings['total_processing_ms'] = (perf_counter() - origin) * 1000
                    audit.update(committed=False, decision='ASK', bmd={'category': 'SEMANTIC_SCOPE_CLARIFICATION'},
                                 response_prepared=dict(text=text, classification=result.classification))
                    return result, audit
            # Retrieve only after the live owner/RBAC checks, before interpretation.
            reference_result = None
            document_result = None
            if (isinstance(self.store, PostgresConversationStore)
                    and callable(getattr(self.store.repository, 'load_result', None)) and not turn.get('cached')):
                reference_result = await self.store.repository.load_result(turn['conn'], context, turn)
            if self.researcher is not None and hasattr(self.researcher, 'result_reference'):
                research_result = await self.researcher.result_reference(context, turn)
                if research_result is not None:
                    order = list(turn['history'])
                    research_position = (order.index(research_result['result_id'])
                                         if research_result['result_id'] in order else -1)
                    current_position = (order.index(reference_result['result_id'])
                                        if reference_result and reference_result['result_id'] in order else -1)
                    if reference_result is None or research_position >= current_position:
                        reference_result = research_result
            if reference_result is not None and not await self._reference_allowed(reference_result, context, turn.get('conn')):
                reference_result = None
            pointer = turn.get('result_reference') or {}
            selected = (pointer.get('selected_ordinal') if reference_result is not None
                        and pointer.get('result_id') == reference_result['result_id'] else None)
            document_pointer = turn.get('document_reference')
            if document_pointer and isinstance(self.store, PostgresConversationStore):
                document_result = await self.store.repository.load_result(turn['conn'], context,
                    dict(turn, result_reference=document_pointer, result_reference_initialized=True))
                if document_result is not None and not await self._reference_allowed(document_result, context, turn.get('conn')):
                    document_result = None
            elif reference_result is not None and reference_result['capability'] == 'sales.latest_documents.v1':
                document_result = reference_result
                document_pointer = dict(result_id=reference_result['result_id'], selected_ordinal=selected)
            if reference_result is not None:
                interpretation_args['result_context'] = dict(
                    result_references.interpreter_context(reference_result, selected),
                    active_focus=turn.get('reference_focus') != 'document')
            if document_result is not None:
                interpretation_args['document_context'] = dict(result_references.interpreter_context(
                    document_result, document_pointer.get('selected_ordinal')),
                    active_focus=turn.get('reference_focus') == 'document')
            if (isinstance(self.store, PostgresConversationStore)
                    and any(s.get('metric') == 'sales.net_amount' for s in turn['history'].values())):
                monetary_results = await self.store.repository.load_monetary_results(turn['conn'], context, turn)
                monetary_results = [r for r in monetary_results
                    if await self._reference_allowed(r, context, turn.get('conn'))]
            if monetary_results:
                from .monetary_comparison import descriptors
                interpretation_args['monetary_context'] = descriptors(monetary_results, turn.get('monetary_comparison'))
                audit['monetary_context_delivered'] = deepcopy(interpretation_args['monetary_context'])
            if self.researcher is not None:
                interpretation_args['research_available'] = True
            if reference_result is not None and reference_result.get('research_receipt'):
                audit['research_context_delivered'] = dict(
                    result_id=reference_result['result_id'],
                    rows=len(interpretation_args['result_context'].get('rows', [])),
                    context_bytes=len(json.dumps(interpretation_args['result_context'], ensure_ascii=False).encode()),
                    continuity_cells=len(reference_result['manifest'].get('continuity_cells', [])))
            proposal = await self.interpreter.interpret(**interpretation_args)
            audit['interpretation_proposed'] = deepcopy(proposal)
            if (proposal == {'intent': 'RESEARCH', 'action': 'INVESTIGATE'}
                    and self.researcher is not None and not before.get('pending')):
                state_engine.validate(before)
                audit.update(committed=False, decision='RESEARCH_REQUESTED',
                             bmd={'category': 'RESEARCH_REQUESTED'})
                timings['interpretation_ms'] = (perf_counter() - phase) * 1000
                timings['total_processing_ms'] = (perf_counter() - origin) * 1000
                return MessageResult('No hay un resultado de investigación confirmado.',
                                     context.correlation_id, 'DIRECT_UNAVAILABLE'), audit
            if (proposal == {'intent': 'RESEARCH', 'action': 'INVESTIGATE'}
                    and before.get('pending', {}).get('spec', {}).get('slot') == 'sales_channel'):
                # A pending channel choice is resolved by the user's explicit
                # answer before handing the turn to free research. Otherwise the
                # investigator receives the stale pending state and can spend its
                # whole budget re-asking a question already answered.
                from .commercial_continuity import normalized
                if 'todos los canales' in normalized(message.text_body):
                    proposed = deepcopy(before['pending']['proposed'])
                    proposal = dict(intent='REFINE', action='EXECUTE', clarification=None,
                                    state_delta={'set': {
                                        '/metric': proposed['metric'],
                                        '/period': proposed['period'],
                                        '/branches': proposed['branches'],
                                        '/sales_channel': None}, 'unset': []})
            proposal = documentary_request_contract(proposal, message.text_body)
            proposal = fixed_ranking_request_contract(proposal, message.text_body)
            from .commercial_continuity import request_contract
            proposal = request_contract(proposal, message.text_body, before, reference_result)
            from .product_routing import request_contract as product_customers_contract
            proposal = product_customers_contract(proposal, message.text_body, before, reference_result)
            if proposal != audit['interpretation_proposed']:
                audit['business_contract_proposal'] = deepcopy(proposal)
        except LunaError as failure:
            # A technical failure is never reported as a failure to understand.
            proposal = None
            technical_failure = failure
            audit['luna_failure'] = failure.audit()
        except Exception:
            proposal = None
        timings['interpretation_ms'] = (perf_counter() - phase) * 1000
        phase = perf_counter()
        if proposal is None and technical_failure is not None:
            classification = 'ERROR'
            text = technical_failure_text(technical_failure)
            audit.update(committed=False, decision='LUNA_TECHNICAL_FAILURE',
                         execution_status='not_executed',
                         bmd={'category': 'LUNA_TECHNICAL_FAILURE'})
            audit['response_prepared'] = dict(text=text, classification=classification)
            timings['total_processing_ms'] = (perf_counter() - origin) * 1000
            return MessageResult(text, context.correlation_id, classification), audit
        if isinstance(proposal, dict) and proposal.get('intent') == 'MONETARY_COMPARISON':
            from .monetary_comparison import calculate
            classification = 'NEEDS_CLARIFICATION'
            text = ('Necesito dos resultados anteriores autorizados y compatibles para comparar. '
                    'Las categorías requieren el mismo período y cobertura, además de moneda y métrica iguales; '
                    'no puedo comparar una consulta no ejecutada ni mezclar importes de líneas y cabeceras. '
                    '¿Qué dos resultados querés comparar?')
            if isinstance(proposal.get('comparison'), dict) and 'target_field' in proposal['comparison']:
                text = ('Necesito un resultado anterior autorizado con los componentes y la base solicitados. '
                        '¿Qué resultado y qué importes querés relacionar? No hice una nueva consulta.')
            audit.update(committed=False, decision='ASK')
            try:
                record, calculated_text = calculate(proposal, monetary_results, turn['owner'])
                if not all([await self._reference_allowed(record[k], context, turn.get('conn'))
                            for k in ('target', 'baseline')]):
                    classification, text = 'DENIED', 'No se pudo autorizar esta comparación.'
                    audit['decision'] = 'DENIED'
                else:
                    classification, text = 'DIRECT_AVAILABLE', calculated_text
                    audit.update(decision='LOCAL_CALCULATION', monetary_calculation=record,
                        required_permission=record['target']['required_permission'],
                        monetary_comparison_pointer={k: record[k] for k in
                            ('target_id', 'baseline_id', 'target_field', 'baseline_field') if k in record})
            except (ValueError, KeyError, TypeError, ArithmeticError):
                pass
            audit['response_prepared'] = dict(text=text, classification=classification)
            timings['total_processing_ms'] = (perf_counter() - origin) * 1000
            return MessageResult(text, context.correlation_id, classification), audit
        if isinstance(proposal, dict) and proposal.get('intent') == 'DOCUMENT_REFERENCE':
            return await self._document_turn(proposal, document_result, document_pointer, context, turn, audit, origin)
        if isinstance(proposal, dict) and (proposal.get('intent') == 'RESULT_REFERENCE'
                                         or proposal.get('action') == 'SELECT_RESULT'):
            # Independent contract: never feed selection into the query State Engine.
            classification = 'NEEDS_CLARIFICATION'
            try:
                ordinal, text = result_references.resolve(proposal, reference_result, selected,
                    turn['owner'], context.conversation_id,
                    calculator=getattr(self.researcher, 'calculate_result', None))
                if ordinal is not None:
                    if not await self._reference_allowed(reference_result, context, turn.get('conn')):
                        classification, text = 'DENIED', 'No se pudo autorizar esta operación.'
                        audit['decision'] = 'DENIED'
                    else:
                        classification = 'DIRECT_AVAILABLE'
                        audit.update(decision='SELECT_RESULT', business_rbac_verified=True,
                            required_permission=reference_result['required_permission'],
                            result_reference=dict(result_id=reference_result['result_id'], selected_ordinal=ordinal),
                            result_provenance=deepcopy(reference_result['source']),
                            selected_field=proposal['result_reference']['field'])
                        if reference_result.get('research_receipt'):
                            audit.update(research_reference=True,
                                research={'recovery': deepcopy(reference_result['research_receipt']),
                                          'sql_executions': 0})
                        if proposal['action'] == 'TRANSFORM_RESULT':
                            audit.update(decision='LOCAL_RESULT_TRANSFORM',
                                         result_transformation=deepcopy(proposal['transformation']))
                        audit['reference_focus'] = 'result'
                        if reference_result['capability'] == 'sales.latest_documents.v1':
                            audit['document_reference'] = deepcopy(audit['result_reference'])
                            audit['reference_focus'] = 'document'
                        row = reference_result['rows'][ordinal - 1]
                        audit['selected_document'] = {key: row[key] for key in
                            ('doc_entry', 'doc_num', 'line_num', 'item_code') if key in row}
                else:
                    audit['decision'] = 'ASK'
            except (ValueError, KeyError, TypeError):
                text = ('No puedo identificar ese elemento o campo en el resultado anterior acreditado. '
                        '¿Qué lista, posición o dato querés consultar?')
                audit['decision'] = 'ASK'
            audit.update(committed=False, response_prepared=dict(text=text, classification=classification))
            timings['total_processing_ms'] = (perf_counter() - origin) * 1000
            return MessageResult(text, context.correlation_id, classification), audit
        processed = self.engine(before, proposal, turn['history'], context.correlation_id)
        timings['state_engine_ms'] = (perf_counter() - phase) * 1000
        audit['contract_error'] = processed.get('contract_error')
        if processed.get('pending_lifecycle'):
            audit['pending_lifecycle'] = list(processed['pending_lifecycle'])
        audit['committed'] = processed['committed'] is True
        if processed['committed'] is not True:
            # NEVER use raw EXECUTE, rejected state_after, or the retained prior plan.
            audit['decision'] = 'EXECUTION_FORBIDDEN'
            reason = processed.get('researchable_contract_error')
            if self.researcher is not None and reason in state_engine.RESEARCHABLE_CONTRACT_ERRORS:
                audit.update(decision='FAST_PATH_UNREPRESENTABLE',
                             bmd={'category': 'CONTRACT_SCOPE_UNSUPPORTED', 'reason': reason})
                classification = 'DIRECT_UNAVAILABLE'
                text = 'El camino rápido no representa esta consulta. No se ejecutó el plan rechazado.'
        else:
            state, action = processed['state_after'], processed['output']['action']
            from modules.telchi.datalake.operational_query import OPERATIONS
            if action in {'DIRECT_UNAVAILABLE', 'ANALYSIS_UNAVAILABLE'}:
                # D1: an interpreter decision is never evidence of business
                # unavailability. Availability is a validated contract, not model
                # opinion; a contradiction is audited and resolved, never rendered
                # as an invented gap. It confers no permission either.
                available = self.capabilities.availability(state)
                if available.allowed:
                    audit['availability_inconsistency'] = dict(
                        proposed_action=action, allowed=True, metric=state.get('metric'),
                        breakdown_by=state.get('breakdown_by'),
                        periods=len(state.get('periods') or []),
                        channel=state.get('sales_channel'),
                        rule='interpreter_decision_is_not_availability_evidence')
                    if action == 'DIRECT_UNAVAILABLE':
                        # The committed state is fully representable: resolve it
                        # through the accredited operation instead of declaring a gap.
                        action = 'EXECUTE'
                        audit['availability_resolution'] = (
                            'AVAILABILITY_CONTRACT_CONSISTENT_EXECUTION; NOT_AUTHORIZATION')
                    else:
                        # No accredited operation represents an analysis; the
                        # authorized mechanism is the investigator, not a
                        # substitute measure.
                        audit['availability_resolution'] = (
                            'ANALYSIS_ROUTED_TO_AUTHORIZED_RESEARCH; NOT_AUTHORIZATION')
            # Materialize one service-owned effective scope before routing. The
            # same receipt is handed to capabilities and free research; the
            # latter must never reconstruct scope from turn['state'] alone.
            delta_sets = ((proposal.get('state_delta') or {}).get('set') or {})
            explicit_keys = {str(k).lstrip('/') for k in delta_sets}
            inherited_keys = {
                key: deepcopy(before.get(key)) for key in (
                    'metric', 'period', 'periods', 'period_mode', 'branches',
                    'sales_channel', 'comparison', 'group_by', 'business_category',
                    'product_target', 'customer_target')
                if before.get(key) and key not in explicit_keys
            }
            explicit_filters = {str(k).lstrip('/'): deepcopy(v) for k, v in delta_sets.items()}
            contract = business_scope.effective_scope(
                state, question=message.text_body,
                intent=processed['output'].get('intent'),
                resolution='pending_clarification' if state.get('pending') else 'confirmed',
                coverage='pending' if state.get('pending') else 'unverified')
            contract.update(explicit_filters=explicit_filters,
                            inherited_confirmed_filters=inherited_keys,
                            inherited_ambiguous_filters=(
                                {'sales_channel': before.get('sales_channel')}
                                if (state.get('pending') or {}).get('spec', {}).get('slot') == 'sales_channel'
                                else {}),
                            provenance={key: ('explicit' if key in explicit_keys else 'inherited')
                                        for key in set(explicit_filters) | set(inherited_keys)},
                            workspace=context.channel.workspace_id,
                            permissions=sorted(getattr(context.sender_identity, 'permissions', ()) or ()))
            # The audit is the durable receipt; keeping the operational state
            # schema unchanged preserves legacy replay and pending hashes.
            audit['business_scope'] = deepcopy(contract)
            audit.setdefault('scope_trace', []).append(
                business_scope.scope_audit_entry(contract, 'confirmed_state', source='state_engine'))
            audit['validated_state'] = deepcopy(state)
            audit['confirmed_state'] = deepcopy(state)  # confirmed request, NOT execution
            audit['decision'] = action
            relevant_concepts = []
            if semantics:
                if semantics['status'] == 'resolved' or (semantics['concepts'] and
                        all(c['match'] in {'code', 'alias'} for c in semantics['concepts'])):
                    relevant_concepts = semantics['concepts']
                elif processed['output']['intent'] != 'NEW_QUERY':
                    relevant_concepts = semantics.get('context_concepts', [])
                if relevant_concepts:
                    refs = [dict(concept_id=c['concept_id'], version=c['version']) for c in relevant_concepts]
                    state_engine.attach_semantic_references(state, refs)
                elif processed['output']['intent'] == 'NEW_QUERY':
                    state.pop('semantic_references', None)
                    if state.get('pending'):
                        state['pending']['base_state_hash'] = state_engine.state_hash(dict(state, pending=None))
                audit['validated_state'] = deepcopy(state)
                audit['confirmed_state'] = deepcopy(state)
            elif processed['output']['intent'] == 'NEW_QUERY':
                state.pop('semantic_references', None)
                if state.get('pending'):
                    state['pending']['base_state_hash'] = state_engine.state_hash(dict(state, pending=None))
                audit['validated_state'] = deepcopy(state)
                audit['confirmed_state'] = deepcopy(state)
            from .business_categories import category_code
            known_pending = any(c['operational_context'].get('capability_status') == 'pending' for c in relevant_concepts)
            if known_pending:
                limits = [limit for c in relevant_concepts for limit in c['operational_context'].get('limitations', [])]
                classification = 'DIRECT_UNAVAILABLE'
                text = (' '.join(c['definition'] for c in relevant_concepts) + ' ' + ' '.join(limits) +
                        ' Conozco esta definición empresarial, pero su operación todavía no está habilitada. '
                        'No se consultó Foundation ni se calcularon resultados.')
                audit.update(decision='DIRECT_UNAVAILABLE', bmd={'category': 'KNOWN_CONCEPT_CAPABILITY_PENDING'})
            elif (before.get('semantic_references') and processed['output']['intent'] != 'NEW_QUERY'
                  and not relevant_concepts):
                classification, text = 'DIRECT_UNAVAILABLE', (
                    'La definición referenciada ya no está publicada en este alcance. No ejecuté una consulta sustituta. '
                    'Iniciá una nueva consulta o solicitá revisión administrativa.')
                audit.update(decision='DIRECT_UNAVAILABLE', bmd={'category': 'CONCEPT_REFERENCE_UNAVAILABLE'})
            elif state.get('analysis_categories') and action == 'EXECUTE':
                classification, text = await self._category_analysis(state, context, turn, audit)
            elif (state.get('analysis_categories') and processed['output']['intent'] == 'EXPLAIN'
                  and isinstance(self.store, PostgresConversationStore)):
                previous = await self.store.repository.load_category_analysis(turn['conn'], context, turn, state)
                if previous and await self._operation_permissions_allowed(state, context, turn.get('conn')):
                    from .commercial_continuity import format_category_analysis, shares
                    analysis = previous['analysis']
                    components, denominator = analysis['components'], analysis['denominator']
                    text = format_category_analysis(state, components, denominator, shares(state, components, denominator))
                    text += '\n\nReutilizo el resultado anterior autorizado; no hice una nueva consulta. Su actualización no certifica cierre completo.'
                    classification = 'DIRECT_AVAILABLE'
                    audit.update(decision='EXPLAIN', execution_status='not_executed',
                                 category_analysis_reference=previous['result_id'], business_rbac_verified=True)
                else:
                    classification, text = 'DIRECT_UNAVAILABLE', 'No pude recuperar un análisis compatible y autorizado. No ejecuté una consulta sustituta.'
            elif (processed['output']['intent'] == 'EXPLAIN' and category_code(state)
                  and state.get('metric') in {'sales.net_amount', 'sales.product_line_amount_ranking'}):
                classification = 'DIRECT_AVAILABLE'
                text = ('El importe registrado en líneas comerciales excluye el IVA de línea y ya refleja '
                        'los descuentos propios. No descuenta notas de crédito ni incorpora ajustes globales. '
                        'El total de cabecera puede incluir IVA y otros componentes; tiene otra semántica. '
                        'No toda la diferencia residual se explica por IVA. No aplicamos conversiones automáticas '
                        'por 1,13 ni por 0,87. No es facturación documental neta ni monto cobrado.')
                audit.update(decision='EXPLAIN', execution_status='not_executed')
            elif unsupported_product_amount(state, message.text_body):
                classification, text = 'DIRECT_UNAVAILABLE', (
                    'El importe neto por producto no está acreditado: falta la asignación '
                    'de descuentos e impuestos de cabecera y notas de crédito al producto. '
                    'No ejecuté un total global como sustituto ni consulté Foundation.')
                audit.update(decision='DIRECT_UNAVAILABLE', bmd={'category': 'NET_PRODUCT_AMOUNT_UNRESOLVED'})
            elif (before.get('metric') == 'sales.latest_documents'
                    and state.get('metric') == 'sales.latest_documents'
                    and normalized_request(message.text_body) == 'y las anteriores'):
                classification = 'DIRECT_UNAVAILABLE'
                text = ('Conservo la consulta de las últimas facturas activas. '
                        'Esta operación no admite paginación: no puedo mostrar las diez anteriores '
                        'ni presentar otra vez la primera lista como una segunda página. No se consultó Foundation.')
                audit.update(decision='DIRECT_UNAVAILABLE', bmd={'category': 'PAGINATION_UNSUPPORTED'})
            elif action == 'ASK':
                pending = state['pending']
                classification, text = 'NEEDS_CLARIFICATION', pending['spec']['question']
                # A committed clarification is not execution authority. Do not ask
                # dates to unlock a definitively missing metric/filter/metadata.
                known = pending['proposed']
                available = self.capabilities.availability(known)
                if pending['spec']['slot'] == 'comparison' and known.get('metric') == 'sales.net_amount':
                    classification, text = 'DIRECT_UNAVAILABLE', (
                        'Todavía no puedo calcular automáticamente la diferencia de facturación entre períodos. '
                        'Puedo consultar cada período por separado, pero no voy a inventar una comparación.')
                    audit.update(decision='DIRECT_UNAVAILABLE', bmd={'category': 'COMPARISON_UNSUPPORTED'})
                elif pending['spec']['slot'] == 'period' and available.category in {
                        'METRIC_MISSING', 'MAPPING_MISSING', 'TEMPORAL_METADATA_MISSING', 'CATEGORY_CAPABILITY_UNAVAILABLE'}:
                    classification, text = 'DIRECT_UNAVAILABLE', unavailable_response(known, available)
                    audit.update(decision='DIRECT_UNAVAILABLE', bmd={'category': available.category})
            elif action in {'DIRECT_UNAVAILABLE', 'ANALYSIS_UNAVAILABLE'}:
                classification = action
                available = self.capabilities.availability(state)
                if action == 'ANALYSIS_UNAVAILABLE' and available.allowed:
                    # The measure is executable but the requested analysis is not
                    # an accredited operation. Research owns it when enabled; the
                    # text never claims the commercial data is unavailable.
                    text = ('No tengo una operación acreditada que responda ese análisis por sí sola. '
                            'La investigación autorizada no confirmó un resultado; no ejecuté una consulta '
                            'sustituta ni presenté una cifra parcial como respuesta al análisis.'
                            if self.researcher is not None else
                            'No tengo una operación acreditada que responda ese análisis. '
                            'Los datos comerciales del alcance sí están disponibles y puedo consultarlos '
                            'como importe, no como explicación de la causa.')
                else:
                    text = ('Esta funcionalidad de análisis todavía no está disponible. La ejecución diferida tampoco está habilitada.'
                            if action == 'ANALYSIS_UNAVAILABLE' else unavailable_response(state, available))
                audit['bmd'] = {'category': 'ANALYSIS_REQUESTED' if action == 'ANALYSIS_UNAVAILABLE' else (available.category or 'CAPABILITY_MISSING')}
                if semantics and semantics.get('ranking', {}).get('vector_eligible'):
                    candidate = next((c for c in semantics.get('interpretation_concepts', []) if c['match'] == 'vector'), None)
                    if candidate and candidate['operational_context'].get('capability_status') == 'pending':
                        text = ('La consulta podría referirse a «' + candidate['canonical_name'] + '». '
                                + candidate['definition'] + ' '
                                + ' '.join(candidate['operational_context'].get('limitations', []))
                                + ' La coincidencia es un candidato semántico, no una clasificación confirmada. '
                                'La operación no está habilitada; no se calcularon resultados ni se consultó Foundation.')
            elif action == 'EXECUTE':
                audit['required_permission'] = self.capabilities.required_permission(state) or self.authorization.policy.permission
                available = self.capabilities.availability(state)
                if not available.allowed:
                    # BUSINESS ANSWER FIRST: deliver the accredited part of the
                    # scope before declaring the whole request unavailable.
                    partial = await self._partial_scope_answer(state, available, context, turn, audit)
                    if partial is not None:
                        classification, text = 'DIRECT_AVAILABLE', partial
                        audit.update(decision='EXECUTE_PARTIAL',
                                     bmd={'category': available.category, 'partial': True})
                    else:
                        classification, text = 'DIRECT_UNAVAILABLE', unavailable_response(state, available)
                        audit.update(decision='DIRECT_UNAVAILABLE', bmd={'category': available.category})
                elif not await self.authorization.allowed(context, turn.get('conn')):
                    classification, text = 'DENIED', 'No se pudo autorizar esta consulta.'
                    audit.update(decision='DENIED', confirmed_state=before)
                elif not await self._operation_permissions_allowed(state, context, turn.get('conn')):
                    classification, text = 'DENIED', 'No se pudo autorizar esta operación: requiere un permiso comercial específico. No se consultó Foundation.'
                    audit.update(decision='DENIED', execution_status='not_executed')
                else:
                    phase = perf_counter()
                    try:
                        audit['capability_calls'] += 1
                        result = await self.capabilities.execute(state)
                        # The executed scope is projected into the persisted state so
                        # the next turn recovers product, customer, dimension and
                        # periods without the user repeating them.
                        from . import business_scope
                        business_scope.project(state, result)
                        state_engine.validate(state)
                        audit.update(business_rbac_verified=True,
                                     execution_result=result, execution_status='executed', decision='EXECUTE',
                                     confirmed_state=deepcopy(state))
                        if state['metric'] in OPERATIONS:
                            audit['business_scope'] = dict(domain=OPERATIONS[state['metric']][0],
                                metric=state['metric'], universe='CAPTURED_NATIVE_OBSERVATIONS',
                                datasets=list(result.get('source', {}).get('datasets', {})),
                                coverage=deepcopy(result.get('coverage', {})))
                        else:
                            audit['business_scope'] = business_scope.result_scope(state, result)
                        formatting = perf_counter()
                        text = format_result(result, audit.get('business_scope'))
                        timings['response_format_ms'] = (perf_counter() - formatting) * 1000
                        classification = 'DIRECT_AVAILABLE'
                    except ProductResolutionError as exc:
                        # The request is understood but no single accredited
                        # product was proved. Never guess an ItemCode or run a
                        # global/other-product query as a substitute.
                        candidates = [c for c in exc.candidates if isinstance(c, dict)]
                        if candidates:
                            shown = '; '.join(
                                f"{c.get('item_code')} — {str(c.get('description') or '').rstrip('.')}"
                                for c in candidates[:5])
                            classification = 'NEEDS_CLARIFICATION'
                            text = ('Encontré varios productos compatibles con ese nombre: ' + shown +
                                    '. ¿Cuál querés analizar? Podés indicar el código SAP o el nombre completo.')
                            audit.update(decision='ASK', execution_status='not_executed',
                                         confirmed_state=deepcopy(state),
                                         bmd={'category': 'PRODUCT_AMBIGUOUS'})
                        else:
                            classification = 'DIRECT_UNAVAILABLE'
                            text = ('No encontré un producto acreditado con ese nombre. '
                                    'No inventé un código ni ejecuté una consulta. '
                                    'Indicá el código SAP o un nombre más específico.')
                            audit.update(decision='DIRECT_UNAVAILABLE', execution_status='not_executed',
                                         confirmed_state=deepcopy(state),
                                         bmd={'category': 'PRODUCT_LOOKUP_UNRESOLVED'})
                        audit['product_resolution'] = {'reason': exc.reason,
                            'candidate_count': len(candidates),
                            'candidates': [{k: c.get(k) for k in ('item_code', 'description')}
                                           for c in candidates[:5]]}
                    except Exception as exc:
                        # Deterministic classification: the real Foundation family
                        # and cause are audited; the user never sees SQL, secrets or
                        # internal parameters and is never told to repeat a
                        # non-retryable failure.
                        failure = capability_failure(exc, state)
                        if getattr(exc, 'evidence', None) is not None:
                            audit['capability_failure_evidence'] = deepcopy(exc.evidence)
                        classification, text = failure['classification'], failure['text']
                        audit.update(
                            decision='DIRECT_UNAVAILABLE' if classification == 'DIRECT_UNAVAILABLE' else 'ERROR',
                            execution_status='not_executed' if classification == 'DIRECT_UNAVAILABLE' else 'failed',
                            confirmed_state=deepcopy(state) if failure['category'] == 'DATA_UNAVAILABLE' else before,
                            bmd={'category': failure['category']})
                        audit['capability_failure'] = dict(category=failure['category'],
                            reason=failure['reason'], metric=state.get('metric'),
                            capability_contract=failure.get('capability'),
                            retryable=False)
                    timings['capability_ms'] = (perf_counter() - phase) * 1000 - timings['response_format_ms']
        # The channel rejects a body longer than its limit. The accredited answer
        # is kept whole in the audit; the delivered text is always deliverable.
        decision = guard_outbound(text)
        if decision.applied:
            audit['accredited_response_text'] = decision.full_text
            audit['delivery_guard'] = decision.audit()
            text = decision.text
        result = MessageResult(text, context.correlation_id, classification)
        audit['response_prepared'] = dict(text=text, classification=classification)
        timings['total_processing_ms'] = (perf_counter() - origin) * 1000
        return result, audit

    async def _category_analysis(self, state, context, turn, audit):
        from .commercial_continuity import component_states, format_category_analysis
        components = {}
        # Each primitive is authorized independently; unavailable denominator
        # permission never conceals an authorized category amount.
        for code, part in component_states(state):
            if not await self._operation_permissions_allowed(part, context, turn.get('conn')):
                components[code] = {'status': 'denied'}
                continue
            try:
                if not self.capabilities.availability(part).allowed:
                    components[code] = {'status': 'unavailable'}
                    continue
                audit['capability_calls'] += 1
                components[code] = {'status': 'verified', 'result': await self.capabilities.execute(part)}
            except Exception as exc:
                from modules.telchi.datalake.category_line_amount_query import SAFE_ERRORS
                reason = str(exc) if str(exc) in SAFE_ERRORS else 'not_accredited'
                components[code] = {'status': reason}
                # The commercial primitive already accredits compatible BS lines
                # separately and quantifies excluded currencies. Do not hide
                # those amounts, or bypass a classification/integrity failure.
                if reason == 'category_currency_not_accredited':
                    fallback = deepcopy(part)
                    fallback.update(metric='sales.commercial_line_amount_by',
                        requested_metrics=['sales.commercial_line_amount_by'], group_by='sap_product', limit=1)
                    if await self._operation_permissions_allowed(fallback, context, turn.get('conn')):
                        try:
                            if self.capabilities.availability(fallback).allowed:
                                audit['capability_calls'] += 1
                                components[code] = {'status': 'partial', 'result': await self.capabilities.execute(fallback)}
                        except Exception:
                            pass
        denominator_state = deepcopy(state)
        denominator_state.update(analysis_categories=None, metric='sales.commercial_line_amount_by',
            requested_metrics=['sales.commercial_line_amount_by'], group_by='sap_product', limit=1)
        denominator = None
        denominator_allowed = await self._operation_permissions_allowed(denominator_state, context, turn.get('conn'))
        if denominator_allowed:
            try:
                if self.capabilities.availability(denominator_state).allowed:
                    audit['capability_calls'] += 1
                    denominator = await self.capabilities.execute(denominator_state)
            except Exception:
                pass
        from .commercial_continuity import shares, denominator_accredited
        percentages = shares(state, components, denominator)
        executed = bool(denominator or any(c.get('result') for c in components.values()))
        audit.update(decision='EXECUTE_PARTIAL', business_rbac_verified=True,
            execution_status='executed' if executed else 'not_executed',
            category_analysis={'components': components, 'denominator': denominator,
                'authorization': {'category_permission': 'telchi.sales.category_line_amount.read.v1',
                    'denominator_permission': 'telchi.sales.commercial_line_amount_by.read.v1',
                    'denominator_allowed': denominator_allowed},
                'percentages': percentages, 'denominator_status': 'VERIFIED' if denominator_accredited(state, denominator) else 'NOT_ACCREDITED'},
            bmd={'category': 'CATEGORY_COMPOSITION', 'partial': True})
        # No monolithic execution result: each component retains its own
        # parameters, source, reconciliation and authorization in this audit.
        return 'DIRECT_AVAILABLE', format_category_analysis(state, components, denominator, percentages)

    async def _partial_scope_answer(self, state, available, context, turn, audit):
        """The accredited part of a scope whose full request is not available.

        Never invents a figure: it reads the same measure, in the same scope,
        through the same capability and permission.
        """
        from . import business_scope
        from .business_plan import build, PlanError
        if state.get('metric') != 'sales.commercial_line_amount_by':
            return None
        if not state.get('product_target') or not state.get('period'):
            return None
        partial_state = dict(state, group_by='sap_product', customer_target=None, breakdown_by=None, limit=1)
        try:
            build(partial_state)
        except PlanError:
            return None
        if not await self._operation_permissions_allowed(partial_state, context, turn.get('conn')):
            return None
        try:
            audit['capability_calls'] += 1
            result = await self.capabilities.execute(partial_state)
            state_engine.validate(partial_state)
        except Exception:
            return None
        rows = result.get('rows') or []
        if not rows:
            return None
        audit['partial_result'] = deepcopy(result)
        periods = [dict(p) for p in (state.get('periods') or [])] or [dict(state['period'])]
        when = business_scope.period_label(periods)
        text = (f'Lo que sí está acreditado del alcance: {rows[0]["key"]} · {rows[0]["label"]} '
                f'registró Bs {business_money(rows[0]["amount"])} en {when} '
                '(importe en líneas comerciales en BS, sin IVA de línea y antes de notas de crédito). '
                f'{available.reason or "Esta parte de la consulta no está acreditada."} '
                f'{_next_step(state, available)}')
        return text

    async def _reference_allowed(self, result, context, conn):
        if result.get('research_receipt'):
            return (self.researcher is not None
                    and await self.researcher.revalidate(context, result['research_receipt']))
        expected = (INVOICE_PERMISSION if result['capability'] == INVOICE_LINES
                    else self.capabilities.required_permission(result['state']))
        return (expected is not None and result['required_permission'] == expected
                and await self.authorization.allowed(context, conn, required_permission=expected)
                and await self._operation_permissions_allowed(result['state'], context, conn))

    async def _document_turn(self, proposal, document, pointer, context, turn, audit, origin):
        classification = 'NEEDS_CLARIFICATION'
        text = '¿A qué factura de los resultados anteriores te referís?'
        audit.update(committed=False, decision='ASK')
        try:
            ordinal, options = result_references.document_selection(proposal, document,
                (pointer or {}).get('selected_ordinal'), turn['owner'], context.conversation_id)
            if not await self._reference_allowed(document, context, turn.get('conn')):
                classification, text = 'DENIED', 'No se pudo autorizar esta operación.'
                audit['decision'] = 'DENIED'
            else:
                audit.update(document_reference=dict(result_id=document['result_id'], selected_ordinal=ordinal),
                    required_permission=document['required_permission'], business_rbac_verified=True,
                    selected_document={k: options[k] for k in ('source_system', 'document_type', 'doc_entry', 'doc_num')},
                    result_provenance=deepcopy(document['source']))
                amount_requested = (proposal['action'] == 'SELECT_DOCUMENT'
                                    and proposal['result_reference']['field'] == 'amount')
                if amount_requested:
                    from modules.telchi.datalake.invoice_amount_query import PERMISSION, validate_result
                    audit.update(required_permission=PERMISSION, reference_focus='document')
                    if not await self.authorization.allowed(context, turn.get('conn'), required_permission=PERMISSION):
                        classification, text = 'DENIED', 'No se pudo autorizar la consulta del importe de esta factura.'
                        audit['decision'] = 'DENIED'
                    else:
                        try:
                            audit['capability_calls'] = 1
                            started = perf_counter()
                            result = await self.capabilities.invoice_amount(options)
                            validate_result(options, result)
                            audit['timings']['capability_ms'] = (perf_counter() - started) * 1000
                            text, classification = format_result(result), 'DIRECT_AVAILABLE'
                            audit.update(decision='READ_AMOUNT', execution_status='executed', execution_result=result)
                        except Exception:
                            classification = 'DIRECT_UNAVAILABLE'
                            text = (f"La factura N.º {options['doc_num']} está identificada, pero no pude verificar su importe "
                                    'en la publicación original. No reconstruí el total sumando productos.')
                            audit.update(decision='READ_AMOUNT_UNAVAILABLE', execution_status='failed')
                elif proposal['action'] == 'SELECT_DOCUMENT':
                    field = proposal['result_reference']['field']
                    text = f"Factura N.º {options['doc_num']}. "
                    text += (f"Fecha: {options['doc_date'][:10]}." if field == 'doc_date' else
                             'El cliente no está disponible en la cabecera conservada; no hay una operación habilitada para recuperarlo.' if field == 'client' else
                             f"Fecha: {options['doc_date'][:10]}.")
                    text += f" Información actualizada al {business_date(document['source']['updated_at'])}."
                    classification, audit['decision'] = 'DIRECT_AVAILABLE', 'SELECT_DOCUMENT'
                    audit['reference_focus'] = 'document'
                elif not await self.authorization.allowed(context, turn.get('conn'), required_permission=INVOICE_PERMISSION):
                    classification, text = 'DENIED', f"La factura N.º {options['doc_num']} está identificada, pero no se pudo autorizar la consulta de sus productos."
                    audit.update(decision='DENIED', required_permission=INVOICE_PERMISSION)
                else:
                    audit['required_permission'] = INVOICE_PERMISSION
                    try:
                        from modules.telchi.datalake.invoice_lines_query import parameters, validate_result
                        parameters(options)
                        audit['capability_calls'] = 1
                        started = perf_counter()
                        result = await self.capabilities.invoice_lines(options)
                        audit['timings']['capability_ms'] = (perf_counter() - started) * 1000
                        # Defense in depth for injected adapters, not only the worker.
                        validate_result(options, result)
                        text = format_result(result)
                        classification = 'DIRECT_AVAILABLE'
                        audit.update(decision='READ_LINES', execution_status='executed', execution_result=result,
                                     reference_focus='result')
                    except Exception:
                        classification = 'DIRECT_UNAVAILABLE'
                        text = (f"La factura N.º {options['doc_num']} está identificada, pero no pude verificar sus líneas "
                                'en la publicación original. No consulté otras facturas como sustituto.')
                        audit.update(decision='READ_LINES_UNAVAILABLE', execution_status='failed')
        except (ValueError, TypeError, KeyError):
            pass
        audit['response_prepared'] = dict(text=text, classification=classification)
        audit['timings']['total_processing_ms'] = (perf_counter() - origin) * 1000
        return MessageResult(text, context.correlation_id, classification), audit

    @asynccontextmanager
    async def _semantics_turn(self, turn):
        if self.semantics_connection is None:
            # Existing explicitly injected handlers/tests retain their connection port.
            yield turn['conn']
        else:
            async with self.semantics_connection() as conn:
                yield conn

    async def _operation_permissions_allowed(self, state, context, conn):
        method = getattr(self.capabilities, 'required_permissions', None)
        permissions = method(state) if method else [self.capabilities.required_permission(state)]
        if self.authorization.policy.permission is None and (not permissions or any(not p for p in permissions)):
            return False  # No capability may execute without an explicit commercial contract.
        for permission in permissions:
            if permission is not None and not await self.authorization.allowed(context, conn, required_permission=permission):
                return False
        return True


def normalized_request(text):
    import unicodedata
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', text.lower())
                           if not unicodedata.combining(c) and c not in '¿?¡!.').split())


# Deterministic capability failures are terminal: they never invite a retry of
# an operation that cannot succeed without a change of source or scope.
TERMINAL_CATEGORIES = {'PUBLICATION_INCOMPATIBLE', 'CAPABILITY_UNAVAILABLE',
                       'DATA_UNAVAILABLE', 'EXECUTION_ERROR', 'COMPARISON_UNSUPPORTED',
                       'PRODUCT_AMBIGUOUS', 'PRODUCT_LOOKUP_UNRESOLVED'}
# Representation limits can route the ORIGINAL question, never the rejected
# plan. Missing source accreditation, integrity failures, stale references,
# unproved net-product semantics and permission denials are intentionally absent.
# A genuine ASK remains a clarification, not a reason to query behind the user.
# The single researcher owns fresh SourcePolicy/RBAC and evidence verification.
RESEARCH_CATEGORIES = frozenset({
    'RESEARCH_REQUESTED', 'CONTRACT_SCOPE_UNSUPPORTED',
    'CAPABILITY_MISSING', 'COMPARISON_UNSUPPORTED', 'ANALYSIS_REQUESTED',
    'MAPPING_MISSING', 'METRIC_MISSING', 'TEMPORAL_METADATA_MISSING',
    'CATEGORY_CAPABILITY_UNAVAILABLE', 'RANKING_UNAVAILABLE',
    'OPERATIONAL_SCOPE_UNAVAILABLE', 'DIMENSION_NOT_ACCREDITED',
    'PERIOD_SET_UNSUPPORTED', 'PERIOD_PARAMETER_UNSUPPORTED', 'COVERAGE_GAP',
    'PAGINATION_UNSUPPORTED', 'PRODUCT_AMBIGUOUS', 'PRODUCT_LOOKUP_UNRESOLVED',
    # An incomplete interpretation, an unaccredited channel for that operation and
    # a rejected scope correspondence are representation gaps: the original
    # question may still be answerable by the authorized investigator.
    'INTENT_INCOMPLETE', 'CHANNEL_NOT_ACCREDITED', 'MEASURE_SCOPE_MISMATCH',
    'AVAILABILITY_CONTRACT_INCONSISTENCY',
})
_PUBLICATION_FAILURES = {
    'product_binding_changed', 'product_result_binding_mismatch',
    'FOUNDATION_READ_BINDING_INVALID', 'FOUNDATION_READ_BINDING_CURRENT_CHANGED',
    'Commercial publication accreditation missing',
    'Commercial succession manifest mismatch', 'Commercial succession ancestry invalid',
    'Commercial succession lineage missing',
    'Commercial succession requires incremental reconciliation',
    'Commercial succession adapter unsupported', 'Commercial inherited contract changed',
    'Commercial physical accreditation lost', 'Commercial category accreditation lost',
    'Commercial physical accreditation root changed', 'commercial_result_binding_mismatch',
    'category_accreditation_binding_changed', 'PUBLICATION_INCOMPATIBLE'}
_CAPABILITY_FAILURES = {
    'product_worker_error', 'product_query_unavailable', 'category_amount_worker_error',
    'ranking_worker_error', 'commercial_amount_worker_error', 'datalake_busy',
    'operational_worker_error', 'CAPABILITY_UNAVAILABLE'}
_DATA_FAILURES = {
    'item_code_absent_from_catalog', 'duplicate_catalog_item_code',
    'duplicate_product_documents', 'duplicate_product_lines', 'orphan_product_lines',
    'commercial_quantity_unaccredited', 'commercial_reconciliation_failed',
    'ranking_reconciliation_failed', 'ranking_catalog_integrity_failed',
    'commercial_catalog_integrity_failed', 'category_currency_not_accredited',
    'category_unaccredited_rows_or_lineage', 'category_key_integrity_failed',
    'category_classification_provisional', 'category_classification_changed',
    'period_breakdown_not_reconciled', 'DATA_UNAVAILABLE'}
# A technically executable result that does not correspond to the requested
# measure, channel, period set or breakdown. It is never delivered as an answer.
_SCOPE_FAILURES = {'capability_scope_mismatch', 'invalid_monetary_result',
                   'invalid_monetary_period_coverage', 'invalid_monetary_channel',
                   'unexpected_monetary_channel', 'invalid_period_reconciliation'}


def capability_failure(exc, state):
    """Classify a capability failure by family and cause, never exposing detail.

    Uses the existing error contracts (TelchiQueryError codes, Commercial amount
    reasons) instead of introducing a second taxonomy. The returned text never
    contains SQL, parameters, credentials or driver messages.
    """
    reason = getattr(exc, 'code', None) or str(exc) or type(exc).__name__
    if not isinstance(reason, str) or len(reason) > 120:
        reason = type(exc).__name__
    if reason in _PUBLICATION_FAILURES:
        category, classification = 'PUBLICATION_INCOMPATIBLE', 'ERROR'
        text = ('La publicación de datos vigente no es compatible con esta operación '
                'acreditada. No ejecuté una consulta sobre una base no verificada. '
                'No es un problema de la forma en que preguntaste. Podés iniciar otra consulta.')
    elif reason in _CAPABILITY_FAILURES:
        category, classification = 'CAPABILITY_UNAVAILABLE', 'ERROR'
        text = ('La operación no está disponible en este momento por una falla de la capacidad. '
                'No se obtuvo un resultado verificable. Podés iniciar otra consulta.')
    elif reason in _DATA_FAILURES:
        category, classification = 'DATA_UNAVAILABLE', 'DIRECT_UNAVAILABLE'
        text = ('No pude acreditar los datos de ese alcance ni presentar cifras sin verificar. '
                'No es un problema de la fecha ni de la forma de preguntar. '
                'Podés iniciar otra consulta con otro producto o período.')
    elif reason in _SCOPE_FAILURES:
        # Executable but not the requested representation: never delivered.
        category, classification = 'MEASURE_SCOPE_MISMATCH', 'DIRECT_UNAVAILABLE'
        text = ('La operación se ejecutó, pero el resultado no corresponde a la medida, el canal, los períodos '
                'o el desglose solicitados, así que no lo presento como respuesta. '
                'No es una indisponibilidad de la capability comercial ni un dato inexistente.')
    else:
        category, classification = 'EXECUTION_ERROR', 'ERROR'
        text = ('No hay un resultado Foundation verificable: la operación no se pudo completar. '
                'No es un problema de la forma en que preguntaste. Podés iniciar otra consulta.')
    metric = state.get('metric')
    return dict(category=category, classification=classification, reason=reason, text=text,
                retryable=False,
                capability=(metric + '.v1') if isinstance(metric, str) else None)


def technical_failure_text(failure):
    """Explain a technical failure in plain words, without blaming the user.

    The cause is technical: a transport, a provider or a contract failure of
    the interpreter. It is never reported as "I did not understand you".
    """
    code = getattr(failure, 'code', 'interpretation_unavailable')
    status = getattr(failure, 'status', None)
    kind = getattr(failure, 'kind', 'technical')
    detail = f'código {code}' + (f', estado {status}' if status else '')
    if kind == 'interpretation':
        return ('El intérprete devolvió una respuesta que no pude leer '
                f'({detail}). No se ejecutó ninguna consulta ni se modificó tu conversación. '
                'Podés repetir la pregunta.')
    return ('Hubo una falla técnica del intérprete '
            f'({detail}). No se ejecutó ninguna consulta ni se modificó tu conversación. '
            'No es un problema de la forma en que preguntaste: '
            'podés repetirla en un momento.')


def documentary_request_contract(proposal, text):
    """Narrow documentary-purpose correction; still validated by the State Engine.

    A latest-date request is coverage, not a document list. Never repair rejected
    proposals, invent filters, broaden grants or infer net/monetary semantics.
    Raw interpreter output remains in the audit; no model/prompt changes.
    """
    import re
    if (not isinstance(proposal, dict) or proposal.get('action') != 'EXECUTE'
            or proposal.get('intent') != 'NEW_QUERY'):
        return proposal
    delta = proposal.get('state_delta')
    if not isinstance(delta, dict) or not isinstance(delta.get('set'), dict):
        return proposal
    fields = delta['set']
    if (fields.get('/metric') != 'sales.latest_documents'
            or fields.get('/requested_metrics', ['sales.latest_documents']) != ['sales.latest_documents']
            or fields.get('/limit', 10) not in (1, 10)
            or not re.fullmatch(r'(?:cual es )?la ultima fecha de (?:ventas|facturas(?: de venta)?) registrad[ao]s?', normalized_request(text))):
        return proposal
    try:
        state_engine.patch(state_engine.EMPTY, delta)
    except (ValueError, TypeError, KeyError):
        return proposal  # Never remove a conflicting/invalid path to repair raw.
    corrected = deepcopy(proposal)
    fields = corrected['state_delta']['set']
    fields['/metric'] = 'sales.coverage'
    fields['/requested_metrics'] = ['sales.coverage']
    fields.pop('/limit', None)
    return corrected


def unsupported_product_amount(state, text):
    """Reject an unrepresentable grouping; never replace it with a global total."""
    import re
    metrics = state.get('requested_metrics') or [state.get('metric')]
    return (state.get('metric') != 'sales.by_products' and 'sales.net_amount' in metrics and
            bool(re.search(r'\bpor (?:producto|articulo|sku|item)', normalized_request(text))))


def fixed_ranking_request_contract(proposal, text):
    """Bind only the exact generic ranking question to its registered fixed scope.

    No supplied period/filter is rewritten. Invalid proposals remain rejected;
    raw output and this registry binding are separately retained in the audit.
    """
    if (normalized_request(text) != 'cuales son los productos mas vendidos'
            or not isinstance(proposal, dict) or proposal.get('intent') != 'NEW_QUERY'
            or proposal.get('action') not in {'EXECUTE', 'ASK', 'DIRECT_UNAVAILABLE'}):
        return proposal
    if proposal['action'] == 'ASK':
        spec = proposal.get('clarification')
        if (not isinstance(spec, dict) or set(spec) != {'slot', 'question'} or spec['slot'] != 'period'
                or not isinstance(spec['question'], str) or not 0 < len(spec['question']) <= 300):
            return proposal
    elif proposal.get('clarification') is not None:
        return proposal
    try:
        state = state_engine.patch(state_engine.EMPTY, proposal['state_delta'])
    except (ValueError, TypeError, KeyError):
        return proposal
    if (state['metric'] != 'sales.source_top_items'
            or (state.get('requested_metrics') or [state['metric']]) != ['sales.source_top_items']
            or state['branches'] or state['sales_channel'] or state['comparison']
            or state.get('entity_mention') or state.get('temporal_reference')):
        return proposal
    from modules.telchi.datalake.messaging_sales_query import PERIOD_FROM, PERIOD_TO_EXCLUSIVE
    corrected = deepcopy(proposal)
    corrected['state_delta']['unset'] = [p for p in corrected['state_delta']['unset']
                                          if p.strip().lstrip('/') != 'period']
    corrected['state_delta']['set'] = {p: v for p, v in corrected['state_delta']['set'].items()
                                      if p.strip().lstrip('/') != 'period'}
    corrected['state_delta']['set']['/period'] = dict(start=PERIOD_FROM, end_exclusive=PERIOD_TO_EXCLUSIVE)
    corrected['action'], corrected['clarification'] = 'EXECUTE', None
    return corrected


def unavailable_response(state, available):
    """Render the validated intention, the exact gap and the next useful step.

    BUSINESS ANSWER FIRST: the scope is restated with every period in it, the
    gap is named concretely and the next step is offered. No business value is
    ever invented here.
    """
    from .business_categories import unavailable_text, scope_period_text
    category_response = unavailable_text(state, available.category)
    if category_response is not None:
        return category_response + ' ' + _next_step(state, available)
    if state.get('metric') == 'sales.by_products' and available.allowed:
        return ('No hay una unidad física y factor de conversión acreditados por línea para sumar presentaciones. '
                'Tampoco está acreditado el importe neto por producto. Puedo mostrar movimientos y cantidades '
                'documentales por ItemCode, sin mezclar unidades ni repartir DocTotal.')
    metrics = state.get('requested_metrics') or ([state['metric']] if state['metric'] else [])
    labels = {'sales.net_amount': 'importe de ventas', 'sales.source_top_items': 'cantidades documentales por producto',
              'sales.latest_documents': 'últimas facturas por fecha documental', 'sales.coverage': 'cobertura de facturas activas',
              'products.search': 'productos del catálogo', 'sales.by_products': 'líneas de ventas por producto',
              'sales.product_line_amount_ranking': 'ranking de productos por importe acumulado vendido',
              'sales.commercial_line_amount_by': 'desglose de importe por producto o por cliente facturado'}
    parts = [labels.get(m, m) for m in metrics]
    summary = 'Entendí que pedís ' + ', luego '.join(parts) if parts else 'Entendí la consulta'
    if state.get('entity_mention'):
        summary += ' para «' + state['entity_mention']['text'] + '»'
    when = scope_period_text(state)
    if when:
        summary += f' en {when}'
    elif state.get('temporal_reference'):
        summary += ' durante el último mes registrado'
    reason = available.reason or ('No tengo una operación acreditada que represente exactamente esta consulta; '
                                  'no ejecuté una consulta sustituta.')
    if available.category == 'INTENT_INCOMPLETE':
        reason = ('No pude determinar qué medida u operación acreditada responde esta pregunta, '
                  'así que no ejecuté una consulta sustituta ni presenté una cifra parcial como respuesta.')
    if available.category == 'CHANNEL_NOT_ACCREDITED':
        reason = ('El canal que pedís no tiene una clasificación acreditada para esa operación en particular. '
                  'No lo reemplacé por otro canal ni por un total sin canal.')
    if available.category == 'MAPPING_MISSING':
        reason = ('Todavía no puedo consultar las ventas de esa entidad con los filtros solicitados.'
                  if state.get('entity_mention') else
                  'Todavía no puedo consultar las ventas con esos filtros de sucursal, canal o producto.')
        if when:
            reason += ' No es un problema con la fecha elegida.'
    if available.category == 'DIMENSION_NOT_ACCREDITED':
        reason = ('La dimensión que pedís no tiene una operación acreditada todavía. '
                  'El importe, el período y los filtros que ya tengo se conservan.')
    if available.category == 'PERIOD_SET_UNSUPPORTED':
        reason = ('No puedo desglosar por mes sin el conjunto de períodos. '
                  'El resto del alcance se conserva.')
    if available.category == 'MEASURE_SCOPE_MISMATCH':
        reason = ('El resultado ejecutado no coincide con la medida, el canal, los períodos o el desglose '
                  'solicitados. No lo presento como respuesta.')
    if state.get('temporal_reference') and available.category != 'TEMPORAL_METADATA_MISSING':
        reason += ' Tampoco tengo metadata habilitada para resolver el último mes por entidad y métrica.'
    return summary + '. ' + reason + ' ' + _next_step(state, available)


def _next_step(state, available):
    """The next useful step: concrete, and never a query of its own."""
    # A period that already exists in the confirmed scope is never requested again.
    has_period = bool(state.get('period') or state.get('periods') or state.get('comparison'))
    if available.category in {'PERIOD_UNRESOLVED', 'PERIOD_SET_UNSUPPORTED'} and not has_period:
        return 'Indicame el mes o los meses concretos y lo consulto.'
    if available.category == 'DIMENSION_NOT_ACCREDITED':
        return ('Puedo mostrar el importe por producto o por cliente facturado dentro del mismo alcance; '
                'decime cuál de las dos dimensiones querés.')
    if available.category == 'CATEGORY_CAPABILITY_UNAVAILABLE':
        return 'Indicame la categoría acreditada y el período, y lo consulto.'
    if available.category == 'COMPARISON_UNSUPPORTED':
        return ('Puedo consultarte cada período por separado y comparar los importes consultados; '
                'decime los períodos.')
    if available.category in {'MAPPING_MISSING', 'METRIC_MISSING'}:
        return ('Decime qué información necesitás (producto, cliente, período o categoría) y consulto la parte '
                'que sí está acreditada.')
    if available.category == 'CHANNEL_NOT_ACCREDITED':
        return ('Puedo consultarte la facturación neta documental por período con el canal horizontal acreditado, '
                'o el importe de líneas comerciales por producto o por cliente sin filtro de canal; decime cuál.')
    if available.category == 'CAPABILITY_MISSING':
        # A real gap gets a concrete path that the catalog can actually run: a
        # reformulation must never send the user back to the same rejection.
        return ('Si lo que querés es un ranking por producto, puedo darte el importe vendido y la cantidad '
                'documental de cada producto en un período concreto, ordenado por importe o por cantidad: '
                'decime el período y el criterio.')
    return ('Podés reformular la consulta con los datos que ya tenemos.' if has_period else
            'Podés reformular la consulta con los datos que ya tenemos, o indicarme el período faltante.')


def registration(handler):
    permission = handler.authorization.policy.permission
    return HandlerRegistration(handler, required_permissions=frozenset({permission}) if permission else frozenset())
