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
from .contracts import Decision
from .validator import Rejected


class ConsoleResearchService:
    def __init__(self, *, pool, public_keys_by_id, organization, workspace, policies,
                 reader, enabled=False, environment='', issuer='team360',
                 repository=None, permissions=None, sessions=None):
        if not enabled or environment not in {'dev', 'development'}:
            raise ValueError('research_dev_feature_disabled')
        if not public_keys_by_id:
            raise ValueError('explicit_console_public_keys_required')
        self.pool, self.keys, self.issuer = pool, dict(public_keys_by_id), issuer
        self.organization, self.workspace = organization, workspace
        self.policies, self.reader = tuple(policies), reader
        self.repository = repository or ResearchConsoleRepository()
        self.permissions = permissions or PermissionConsoleRepository()
        self.sessions = sessions or ConsoleLoginRepository()
        # Service-local admission, not a replacement for existing SQL/host guards.
        self._slot = asyncio.Lock()

    async def resolve(self, token):
        try:
            return await asyncio.wait_for(self._resolve(token), timeout=10)
        except Exception:
            raise Rejected('console_authorization_denied', Decision.DENY) from None

    async def _resolve(self, token):
        try:
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

    async def ask(self, token, question, save, *, progress=lambda event: None):
        """Internal backend consumer. Token is verified, never recorded or modeled.

        save is the backend-owned private evidence sink, NOT a response callback.
        Only business_answer/clarification in the final return are presentation
        fields; other fields (including raw model prose) remain audit-only. No
        persistent resume is enabled; previous investigations are not model input.
        """
        async with self._slot:
            scope = await self.resolve(token)
            investigation_id = str(uuid4())
            await self._audit(scope, investigation_id, 'STARTED')  # fail closed
            loop = asyncio.get_running_loop()
            cancel = threading.Event()

            def fresh_scope():
                # This function is ONLY used by the worker, never by loop thread.
                future = asyncio.run_coroutine_threadsafe(self.resolve(token), loop)
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
                        policies=self.policies, investigation_id=investigation_id)
                    executor = lambda ctx, **kw: AuthorizedFoundationExecutor(ctx, reader=self.reader, **kw)
                    session = Session(authorized_binding=binding, cancel=cancel, progress=progress)
                    report = asyncio.run(session.ask(question, save, executor_factory=executor))
                    binding.present(report, binding.context)
                    report['reader_contract_gaps'] = gaps
                    return report
                finally:
                    if binding is not None:
                        binding.close()

            worker = asyncio.create_task(asyncio.to_thread(investigate))
            try:
                report = await asyncio.shield(worker)
                current = await self.resolve(token)
                if current != scope:
                    raise Rejected('authorization_changed', Decision.DENY)
                await self._audit(scope, investigation_id, report.get('status', 'BLOCKED'))
                # Audit latency must not preserve revoked access either.
                if await self.resolve(token) != scope:
                    raise Rejected('authorization_changed', Decision.DENY)
                return report
            except BaseException:
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
