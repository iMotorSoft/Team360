"""Free-analysis port for already-authenticated channels (WhatsApp first).

This is NOT a second engine, router or service. It adapts an existing WhatsApp
identity to the one existing researcher (`ConsoleResearchService.ask_scope`):
same Luna planning, same SQL validator/executor, same Foundation CURRENT binding,
same read-only controls, same PG audit. Only identity resolution differs, because
the channel already authenticated the sender and there is no bearer token.

No HTTP hop to Console and no dependency on the web server being up.
"""
import os
import asyncio
from dataclasses import asdict
from hashlib import sha256
import json

from modules.console.repositories import PermissionConsoleRepository
from .exploratory_sql.authorized_foundation import EffectiveScope, SourcePolicy
from .exploratory_sql.console_bridge import ConsoleResearchService
from .exploratory_sql.console_repository import ResearchConsoleRepository
from .exploratory_sql.contracts import Decision
from .exploratory_sql.validator import Rejected
from .research_repository import ResearchRecoveryRepository

# Presentation-safe fields only. Raw model prose, SQL, paths and evidence handles
# stay in the private evidence sink and PG audit, never in the channel answer.
PRESENTATION_FIELDS = ('status', 'business_answer', 'clarification', 'publication',
                       'snapshot', 'question_coverage', 'reason',
                       'model_calls', 'sql_executions',
                       # A declared processing limit: measured budget and cause,
                       # never SQL, prose or evidence handles.
                       'observation_budget', 'partial_verified_figures')


def presentation(report):
    result = {key: report.get(key) for key in PRESENTATION_FIELDS}
    # Research call logs include raw SQL/model prose. Keep those exclusively in
    # the private evidence sink, not in durable PG state or conversation audits.
    metrics = {'model', 'provider', 'elapsed_seconds', 'usage', 'fallback',
               'reasoning', 'reasoning_echo_verified', 'max_output_tokens'}
    result['model_calls'] = [{k: v for k, v in call.items() if k in metrics}
                             for call in (report.get('model_calls') or [])]
    if result['sql_executions'] is None:
        result['sql_executions'] = sum(t.get('result', {}).get('status') == 'COMPLETED'
                                       for t in report.get('turns', []))
    return result


class WhatsAppResearchPort:
    accepts_business_knowledge = True

    def __init__(self, *, service, organization, workspace, policies, evidence_sink_factory,
                 identities=None, permissions=None, recovery_repository=None):
        self.service = service
        self.organization, self.workspace = organization, workspace
        self.policies = tuple(policies)
        self.evidence_sink_factory = evidence_sink_factory
        self.identities = identities or ResearchConsoleRepository()
        self.permissions = permissions or PermissionConsoleRepository()
        self.recovery_repository = recovery_repository

    async def _resolve_scope(self, identity):
        """Fresh effective scope on EVERY access; never cached from the message.

        The channel already bound this sender. The PG identity row is authoritative
        for organization/workspace UUIDs, so it must agree with the composed research
        scope; channel slugs are never compared to Console ids or expanded here.
        """
        if identity is None or identity.environment != 'dev' or not identity.user_id:
            raise Rejected('whatsapp_identity_out_of_scope', Decision.DENY)
        async with self.service.pool.connection() as conn:
            async with conn.transaction():
                row = await self.identities.identity(conn, identity.user_id)
                if not row or (row['organization'], row['workspace']) != (
                        self.organization, self.workspace):
                    raise Rejected('whatsapp_identity_out_of_scope', Decision.DENY)
                effective = await self.permissions.list_effective_permissions(
                    conn, self.workspace, identity.user_id)
                enabled = await self.identities.enabled_permissions(conn, self.workspace)
                return EffectiveScope(identity.user_id, self.organization, self.workspace,
                                      frozenset(effective) & enabled)

    def _permitted(self, scope):
        # Same closed condition as the Console route: an approved whole-dataset
        # contract whose permission the identity actually holds. No expansion.
        return any(p.organization == scope.organization and p.workspace == scope.workspace
                   and p.whole_dataset and p.permission in scope.permissions
                   for p in self.policies)

    def _receipt(self, scope):
        return dict(user_id=scope.user_id, organization=scope.organization,
                    workspace=scope.workspace, permissions=sorted(scope.permissions),
                    policies_sha256=sha256(json.dumps([asdict(p) for p in self.policies],
                        sort_keys=True).encode()).hexdigest())

    async def revalidate(self, context, receipt):
        """Cached answers have no executor: explicitly recheck before disclosure."""
        scope = await self._resolve_scope(context.sender_identity)
        if not self._permitted(scope) or receipt.get('authorization') != self._receipt(scope):
            raise Rejected('recovery_authorization_changed', Decision.DENY)

        def current():
            with self.service.reader.connector.session(read_only=True) as db:
                access = self.service.reader.resolve_on(db)
                return dict(publication=access.foundation_publication_id,
                            snapshot=str(access.ducklake_snapshot_id))

        worker = asyncio.create_task(asyncio.to_thread(current))
        try:
            actual = await asyncio.shield(worker)
        except BaseException:
            # Metadata reads also own a reader connection: don't detach it when
            # the enclosing durable turn is interrupted or times out.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not worker.cancelled():
                worker.exception()
            raise
        if actual != receipt.get('binding'):
            raise Rejected('recovery_publication_changed', Decision.DENY)
        # Publication I/O must not preserve a grant revoked in the meantime.
        if self._receipt(await self._resolve_scope(context.sender_identity)) != receipt['authorization']:
            raise Rejected('recovery_authorization_changed', Decision.DENY)
        return True

    @staticmethod
    def calculate_result(*args, **kwargs):
        """Expose the existing verifier through the research port, not V1 imports."""
        from .exploratory_sql.ask_verifier import AskRegistry
        return AskRegistry.calculate_pair(*args, **kwargs)

    async def result_reference(self, context, turn):
        """Recover executed records, not the channel's truncated prose."""
        if self.recovery_repository is None:
            return None
        scope = await self._resolve_scope(context.sender_identity)
        async with self.service.pool.connection() as conn:
            async with conn.transaction():
                saved = await self.recovery_repository.for_analysis(
                    conn, scope, context, turn.get('analysis_context_id', context.conversation_id))
        if not saved:
            return None
        await self.revalidate(context, saved['receipt'])
        from .assistant.result_references import research_presentation
        return research_presentation(saved, turn['owner'], context.conversation_id)

    async def has_recovery(self, context):
        """Route an interrupted inbox turn back to research without another LLM."""
        if self.recovery_repository is None:
            return False
        scope = await self._resolve_scope(context.sender_identity)
        async with self.service.pool.connection() as conn:
            async with conn.transaction():
                return await self.recovery_repository.load(conn, scope, context) is not None

    async def filter_business_knowledge(self, resolution, context):
        from .exploratory_sql.authorized_foundation import authorized_business_resolution
        scope = await self._resolve_scope(context.sender_identity)
        if not self._permitted(scope):
            raise PermissionError('research_scope_denied')
        return authorized_business_resolution(resolution, scope, self.policies)

    async def __call__(self, question, conversation_id, context, *, analysis_context_id=None,
                       business_knowledge=None):
        identity = context.sender_identity
        scope = await self._resolve_scope(identity)
        if not self._permitted(scope):
            raise Rejected('no_authorized_source', Decision.DENY)

        async def resolve():
            return await self._resolve_scope(identity)

        # Backend-only resolver output. Scope is issued here from live identity,
        # not from inbound metadata or model-proposed permissions.
        knowledge = dict(scope=self._receipt(scope), resolution=business_knowledge) if business_knowledge else None
        repo = self.recovery_repository
        if repo is None:
            report = await self.service.ask_scope(
                resolve, question, self.evidence_sink_factory(),
                conversation_id='whatsapp:' + str(conversation_id), business_knowledge=knowledge)
            return presentation(report)

        async def read(method):
            async with self.service.pool.connection() as conn:
                async with conn.transaction():
                    return await method(conn, scope, context)

        saved = await read(repo.load)
        if saved:
            if (saved.get('question') != question
                    or saved.get('conversation_id') != str(conversation_id)
                    or saved.get('channel_id') != str(context.channel.channel_id)):
                raise Rejected('recovery_owner_mismatch', Decision.DENY)
            await self.revalidate(context, saved['receipt'])
            if saved['state'] == 'COMPLETED':
                return dict(saved['result'], _recovery=saved['receipt'])
        else:
            previous = (await read(lambda conn, scope, ctx: repo.for_analysis(
                conn, scope, ctx, analysis_context_id)) if analysis_context_id is not None
                else await read(repo.previous))
            if previous:
                await self.revalidate(context, previous['receipt'])
            saved = dict(state='RUNNING', question=question,
                conversation_id=str(conversation_id), channel_id=str(context.channel.channel_id),
                conversation_input=previous.get('conversation_output', {}) if previous else {},
                receipt=dict(authorization=self._receipt(scope)))

        async def persist():
            async with self.service.pool.connection() as conn:
                async with conn.transaction():
                    await repo.save(conn, scope, context, saved)

        async def checkpoint(binding):
            saved['receipt']['binding'] = binding
            await persist()

        recovery = dict(saved['conversation_input'], binding=saved['receipt'].get('binding'))
        report = await self.service.ask_scope(resolve, question, self.evidence_sink_factory(),
            conversation_id='whatsapp:' + str(conversation_id),
            recovery=recovery, checkpoint=checkpoint, business_knowledge=knowledge)
        result = presentation(report)
        await self.revalidate(context, saved['receipt'])
        saved.update(state='COMPLETED', result=result,
                     full_result=dict(
                         question=question, evidence_manifests=report.get('evidence_manifests', []),
                         presentation_pages=report.get('presentation_pages', {}),
                         population_pages=report.get('population_pages', {}),
                         population_recovery=report.get('population_recovery', {}),
                         claim_verifications=report.get('claim_verifications', []),
                         business_knowledge=report.get('business_knowledge', {}),
                         results=[{k: t['result'].get(k) for k in
                             ('query_id', 'schema', 'rows', 'truncated', 'status')}
                             for t in report.get('turns', []) if t.get('result')]),
                     conversation_output=report.get('_recovery_conversation', {}))
        await persist()  # Survives loss of the enclosing assistant transaction.
        return dict(result, _recovery=saved['receipt'])


class _LazyPool:
    """Composition may run before the shared lifespan opens the existing pool."""

    def __init__(self, resolve):
        self.resolve = resolve

    def connection(self):
        return self.resolve().connection()


def build_researcher(*, pool, config, environment=None):
    """Explicit DEV opt-in; returns None unless the operator enabled it.

    Reuses the reviewed private Console configuration (policies, optional operator
    publication pin, evidence directory) but never starts the HTTP runtime.
    """
    if os.getenv('TEAM360_TELCHI_FREE_ANALYSIS') != '1':
        return None
    environment = environment or os.getenv('TEAM360_ENV', '')
    if environment not in {'dev', 'development'}:
        raise ValueError('free_analysis_is_dev_only')
    from .console_http import AccreditedReader, evidence_directory, evidence_sink
    policies = tuple(SourcePolicy(**p) for p in config['policies'])
    service = ConsoleResearchService(
        pool=_LazyPool(pool) if callable(pool) else pool, public_keys_by_id={},
        organization=config['organization'],
        workspace=config['workspace'], policies=policies,
        reader=AccreditedReader(config.get('foundation_publication_id')),
        enabled=True, environment=environment)
    return WhatsAppResearchPort(service=service, organization=config['organization'],
        workspace=config['workspace'], policies=policies,
        evidence_sink_factory=lambda: evidence_sink(evidence_directory(config)),
        recovery_repository=(ResearchRecoveryRepository()
            if os.getenv('TEAM360_TELCHI_DURABLE') == '1' else None))