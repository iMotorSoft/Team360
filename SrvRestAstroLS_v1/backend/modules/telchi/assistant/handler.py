"""Real MessageHandler. Messaging retains reception, execution fence and delivery."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from time import perf_counter
from modules.telchi.datalake.query_profile import span

from modules.console.repositories import PermissionConsoleRepository
from modules.db.transaction import transaction
from modules.messaging.delivery_guard import guard_outbound
from modules.messaging.handlers import HandlerRegistration, MessageResult

from . import state_engine
from .capabilities import SalesCapabilities, format_result, business_date, business_money
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
        # Deliberately serializes turns across processes. Bounded processing avoids
        # unbounded pool occupation; crash rolls back, Messaging fence forbids replay.
        pool = self.pool() if callable(self.pool) else self.pool
        async with transaction(pool) as conn:
            turn = await self.repository.load(conn, context)
            yield turn

    async def save(self, context, turn, audit):
        await self.repository.save(turn['conn'], context, turn, audit)


class TelchiHandler:
    # Result/state/audit commit atomically; replay revalidates live RBAC.
    durable_replay_safe = True

    def __init__(self, *, store, authorization, interpreter=None, capabilities=None,
                 turn_timeout_seconds=80, engine=state_engine.process, concept_resolver=None,
                 semantics_connection=None):
        self.store, self.authorization = store, authorization
        self.interpreter = interpreter or LunaInterpreter()
        self.capabilities = capabilities or SalesCapabilities()
        self.turn_timeout_seconds, self.engine = turn_timeout_seconds, engine
        self.concept_resolver = concept_resolver
        self.semantics_connection = semantics_connection

    async def handle(self, message, context):
        denied = MessageResult('No se pudo autorizar esta consulta de Telchi.', context.correlation_id, 'DENIED')
        try:
            async with asyncio.timeout(self.turn_timeout_seconds):
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
                        response = cached['response_prepared']
                        return MessageResult(response['text'], context.correlation_id, response['classification'])
                    result, audit = await self._process(message, context, turn)
                    with span('conversation_audit_save'):
                        await self.store.save(context, turn, audit)
                # Return only after state/result/response transaction commit.
                return result
        except Exception:
            return MessageResult('No se pudo completar la consulta. No hay un resultado confirmado.',
                                 context.correlation_id, 'ERROR')

    async def _process(self, message, context, turn):
        from uuid import uuid4
        command = message.text_body.strip().casefold()
        previous_turn = next(reversed(turn['history']), None)
        from .operational import unsupported_followup
        unavailable = unsupported_followup(message.text_body, turn['state'])
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
            new = (audit.get('committed') is True
                   and audit.get('execution_status') != 'failed'
                   and audit.get('decision') not in {'DENIED', 'ERROR', 'EXECUTION_FORBIDDEN'}
                   and (audit.get('interpretation_proposed') or {}).get('intent') == 'NEW_QUERY')
        # One logical outbound: answer first, controls last, including a safe
        # unavailable/clarification response. Never assume native button support.
        from .conversation_controls import with_options
        text = with_options(result.text)
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
        return result, audit

    async def _process_business(self, message, context, turn):
        origin = perf_counter()
        timings = dict(interpretation_ms=0.0, state_engine_ms=0.0, capability_ms=0.0, response_format_ms=0.0)
        before = deepcopy(turn['state'])
        audit = dict(owner=turn['owner'], previous_state=before, interpretation_proposed=None,
                     validated_state=None, confirmed_state=before, decision='ERROR',
                     execution_status='not_executed', execution_result=None, capability_calls=0,
                     required_permission=None, bmd=None, timings=timings,
                     pilot_approval_sha256=self.authorization.policy.pilot_approval_sha256)
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
                audit['business_semantics'] = semantics
                interpretation_args['business_semantics'] = luna_context(semantics)
                if semantics.get('semantic_guard', {}).get('requires_clarification'):
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
            if reference_result is not None and not await self._reference_allowed(reference_result, context, turn.get('conn')):
                reference_result = None
            selected = (turn.get('result_reference') or {}).get('selected_ordinal')
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
            proposal = await self.interpreter.interpret(**interpretation_args)
            audit['interpretation_proposed'] = deepcopy(proposal)
            proposal = documentary_request_contract(proposal, message.text_body)
            proposal = fixed_ranking_request_contract(proposal, message.text_body)
            from .commercial_continuity import request_contract
            proposal = request_contract(proposal, message.text_body, before)
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
                        monetary_comparison_pointer={k: record[k] for k in ('target_id', 'baseline_id')})
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
                    turn['owner'], context.conversation_id)
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
        audit['committed'] = processed['committed'] is True
        if processed['committed'] is not True:
            # NEVER use raw EXECUTE, rejected state_after, or the retained prior plan.
            audit['decision'] = 'EXECUTION_FORBIDDEN'
        else:
            state, action = processed['state_after'], processed['output']['action']
            from modules.telchi.datalake.operational_query import OPERATIONS
            if (action == 'DIRECT_UNAVAILABLE' and state.get('metric') in OPERATIONS
                    and self.capabilities.availability(state).allowed):
                # The interpreter does not decide catalog availability. Only a
                # committed, compatible request may use this route; the normal
                # base + specific live RBAC checks still precede execution below.
                action = 'EXECUTE'
                audit['availability_resolution'] = 'REGISTERED_OPERATIONAL_ROUTE; NOT_AUTHORIZATION'
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
                    except Exception as exc:
                        from modules.telchi.datalake.product_line_amount_ranking_query import SAFE_ERRORS
                        if getattr(exc, 'evidence', None) is not None:
                            audit['capability_failure_evidence'] = deepcopy(exc.evidence)
                        reason = str(exc)
                        if category_code(state) and reason in SAFE_ERRORS:
                            classification = 'DIRECT_UNAVAILABLE'
                            text = ({'category_currency_not_accredited':
                                'El período contiene monedas documentales o de precio que no están acreditadas para esta métrica BS. No las sumé ni convertí.',
                                'ranking_reconciliation_failed':
                                'No pude verificar la consistencia del ranking monetario. No presento productos ni importes sin confirmar.',
                                'ranking_catalog_integrity_failed':
                                'No pude confirmar los productos del ranking monetario. No presento un resultado sin verificar.',
                                'category_classification_provisional':
                                'La categoría contiene clasificación provisional o insuficiente. No presento ese importe como validado.'}.get(reason,
                                'No pude acreditar la integridad o la procedencia de las líneas de esta consulta. No calculé un importe sustituto.'))
                            audit.update(decision='DIRECT_UNAVAILABLE', execution_status='not_executed',
                                confirmed_state=deepcopy(state), bmd={'category': reason})
                        else:
                            classification, text = 'ERROR', 'No hay un resultado Foundation verificable. Intentá nuevamente.'
                            audit.update(decision='ERROR', execution_status='failed', confirmed_state=before)
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
    reason = available.reason or 'Esta consulta todavía no está disponible.'
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
    if state.get('temporal_reference') and available.category != 'TEMPORAL_METADATA_MISSING':
        reason += ' Tampoco tengo metadata habilitada para resolver el último mes por entidad y métrica.'
    return summary + '. ' + reason + ' ' + _next_step(state, available)


def _next_step(state, available):
    """The next useful step: concrete, and never a query of its own."""
    if available.category in {'PERIOD_UNRESOLVED', 'PERIOD_SET_UNSUPPORTED'}:
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
    return 'Podés reformular la consulta con los datos que ya tenemos, o indicarme el período faltante.'


def registration(handler):
    permission = handler.authorization.policy.permission
    return HandlerRegistration(handler, required_permissions=frozenset({permission}) if permission else frozenset())
