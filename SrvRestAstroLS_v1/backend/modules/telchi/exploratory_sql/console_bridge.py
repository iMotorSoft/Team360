"""Opt-in internal Console -> existing researcher bridge. No route or CLI login.

Backend composition supplies its pool, public verification keys, approved data
contracts and destination. Never construct these from model/request arguments.
The backend event loop owns every PG operation; the existing synchronous SQL
investigator runs in one worker and asks that loop for fresh authorization.
"""
import asyncio
import threading
from uuid import uuid4

from modules.console.auth import verify_console_access_token
from modules.console.login_repository import ConsoleLoginRepository
from modules.console.repositories import PermissionConsoleRepository

from .authorized_foundation import EffectiveScope, AuthorizedFoundationExecutor, open_binding
from .console_repository import ResearchConsoleRepository
from .contracts import Decision, DevResearchBudget
from .validator import Rejected


class ConsoleResearchService:
    def __init__(self, *, pool, public_keys_by_id, organization, workspace, policies,
                 reader, enabled=False, environment='', issuer='team360',
                 repository=None, permissions=None, sessions=None):
        if not enabled or environment not in {'dev', 'development'}:
            raise ValueError('research_dev_feature_disabled')
        # Empty keys fail closed in resolve(): the token adapter needs them, an
        # already-authenticated in-process channel supplies its own scope resolver.
        self.pool, self.keys, self.issuer = pool, dict(public_keys_by_id or {}), issuer
        self.organization, self.workspace = organization, workspace
        self.policies, self.reader = tuple(policies), reader
        self.repository = repository or ResearchConsoleRepository()
        self.permissions = permissions or PermissionConsoleRepository()
        self.sessions = sessions or ConsoleLoginRepository()
        # Service-local admission, not a replacement for existing SQL/host guards.
        self._slot = asyncio.Lock()
        # Bounded in-process conversation only; no token, raw prose or evidence
        # handles survive a request. Every turn gets a fresh authorized binding.
        self._conversations = {}

    async def resolve(self, token):
        try:
            return await asyncio.wait_for(self._resolve(token), timeout=10)
        except Exception:
            raise Rejected('console_authorization_denied', Decision.DENY) from None

    async def _resolve(self, token):
        try:
            if not self.keys:
                raise ValueError('console_public_keys_required')
            # Reverify signature/expiry on EVERY read, not just investigation start.
            principal = verify_console_access_token(token, public_keys_by_id=self.keys,
                issuer=self.issuer, leeway_seconds=0)
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    identity = await self.repository.identity(conn, principal.user_id)
                    if not identity or (identity['organization'], identity['workspace']) != (
                            self.organization, self.workspace):
                        raise ValueError('inactive_or_wrong_scope_identity')
                    claims = principal.claims
                    if claims.get('workspace_id', self.workspace) != self.workspace:
                        raise ValueError('wrong_workspace_session')
                    if 'amr' in claims:
                        if (claims['amr'] != ['pwd'] or type(claims.get('credential_version')) is not int
                                or not await self.sessions.session_active(conn, principal.user_id,
                                    self.workspace, claims['credential_version'])):
                            raise ValueError('inactive_session')
                    effective = await self.permissions.list_effective_permissions(
                        conn, self.workspace, principal.user_id)
                    enabled = await self.repository.enabled_permissions(conn, self.workspace)
                    return EffectiveScope(principal.user_id, self.organization, self.workspace,
                                          frozenset(effective) & enabled)
        except Exception:
            raise Rejected('console_authorization_denied', Decision.DENY) from None

    async def _audit(self, scope, investigation_id, state):
        await asyncio.wait_for(self._write_audit(scope, investigation_id, state), timeout=10)

    async def _write_audit(self, scope, investigation_id, state):
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await self.repository.audit(conn, scope, investigation_id, state)

    async def ask(self, token, question, save, *, progress=lambda event: None, conversation_id='default'):
        """Signed Console-token adapter over the single channel-neutral core."""
        return await self.ask_scope(lambda: self.resolve(token), question, save,
            progress=progress, conversation_id=conversation_id)

    async def ask_scope(self, scope_resolver, question, save, *,
                        progress=lambda event: None, conversation_id='default',
                        recovery=None, checkpoint=None, business_knowledge=None,
                        effective_scope=None):
        """Same investigator for ANY already-authenticated channel.

        scope_resolver is an async callable returning a fresh EffectiveScope. It is
        invoked before investigation, before every executor access and before
        disclosure. A channel (Console token, WhatsApp identity) supplies only that
        resolver; researcher, catalog, SQL controls and audit stay identical.
        Token is verified, never recorded or modeled.

        save is the backend-owned private evidence sink, NOT a response callback.
        Only business_answer/clarification in the final return are presentation
        fields; other fields (including raw model prose) remain audit-only. No
        internal SQL checkpoints are enabled. An authenticated durable adapter may
        supply recovery conversation and an expected publication/snapshot; its
        checkpoint callback commits the binding before investigative SQL. Otherwise
        conversation stays in memory. Previous evidence handles are never reused.
        """
        if not isinstance(conversation_id, str) or not 0 < len(conversation_id) <= 128:
            raise ValueError('invalid_conversation_id')
        async with self._slot:
            scope = await scope_resolver()
            key = (scope.user_id, scope.organization, scope.workspace, conversation_id)
            previous = (self._conversations.get(key) if recovery is None else
                        (scope, recovery.get('history', []), recovery.get('required_measure')))
            if previous and previous[0] != scope:
                self._conversations.pop(key, None)
                previous = None
            conversation_state = []
            investigation_id = str(uuid4())
            await self._audit(scope, investigation_id, 'STARTED')  # fail closed
            loop = asyncio.get_running_loop()
            cancel = threading.Event()

            def fresh_scope():
                # This function is ONLY used by the worker, never by loop thread.
                future = asyncio.run_coroutine_threadsafe(scope_resolver(), loop)
                try:
                    return future.result(timeout=10)
                except BaseException:
                    future.cancel()
                    raise

            def investigate():
                from .ask import Session
                binding = None
                try:
                    binding, gaps = open_binding(reader=self.reader, resolve_scope=fresh_scope,
                        policies=self.policies, investigation_id=investigation_id,
                        budget=DevResearchBudget(), business_knowledge=business_knowledge)
                    if recovery is not None:
                        expected = recovery.get('binding')
                        actual = dict(publication=binding.context.publication,
                                      snapshot=binding.context.snapshot)
                        if expected and expected != actual:
                            raise Rejected('recovery_publication_changed', Decision.DENY)
                        # Commit the binding BEFORE the first investigative SQL.
                        if checkpoint is not None:
                            future = asyncio.run_coroutine_threadsafe(checkpoint(actual), loop)
                            try:
                                future.result(timeout=10)
                            except BaseException:
                                future.cancel()
                                raise
                    executor = lambda ctx, **kw: AuthorizedFoundationExecutor(ctx, reader=self.reader, **kw)
                    session = Session(authorized_binding=binding, cancel=cancel, progress=progress)
                    if previous:
                        session.history = list(previous[1])
                        session.required_measure = previous[2]
                    report = asyncio.run(session.ask(question, save, executor_factory=executor,
                                                      effective_scope=effective_scope))
                    binding.present(report, binding.context)
                    report['reader_contract_gaps'] = gaps
                    conversation_state.extend((list(session.history), session.required_measure))
                    return report
                finally:
                    if binding is not None:
                        binding.close()

            worker = asyncio.create_task(asyncio.to_thread(investigate))
            try:
                report = await asyncio.shield(worker)
                current = await scope_resolver()
                if current != scope:
                    raise Rejected('authorization_changed', Decision.DENY)
                await self._audit(scope, investigation_id, report.get('status', 'BLOCKED'))
                # Audit latency must not preserve revoked access either.
                if await scope_resolver() != scope:
                    raise Rejected('authorization_changed', Decision.DENY)
                if conversation_state and report.get('status') != 'BLOCKED':
                    if len(self._conversations) >= 32 and key not in self._conversations:
                        self._conversations.pop(next(iter(self._conversations)))
                    self._conversations[key] = (scope, *conversation_state)
                else:
                    self._conversations.pop(key, None)
                if recovery is not None and conversation_state:
                    report['_recovery_conversation'] = dict(
                        history=conversation_state[0], required_measure=conversation_state[1])
                return report
            except BaseException:
                self._conversations.pop(key, None)
                cancel.set()
                # Keep loop alive for pending worker authorization requests and
                # await its cleanup; never leave a detached SQL worker running.
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except asyncio.CancelledError:
                        continue  # repeated disconnect must not detach the worker
                    except Exception:
                        break
                if not worker.cancelled():
                    worker.exception()  # retrieve any worker failure after cleanup
                save({'status': 'BLOCKED', 'reason': 'authorization_or_execution_interrupted',
                      'business_answer': ''})
                await self._audit(scope, investigation_id, 'BLOCKED')
                raise
