"""Opt-in DEV Foundation discovery and backend-owned authorization binding.

No default business grants. SourcePolicy is approved server configuration, NEVER
model input. The terminal's local identity is intentionally not upgraded here.
"""
from dataclasses import dataclass, replace
from types import MappingProxyType
import re
import weakref

from .contracts import (AuthorizedExecutionContext, Budget, Catalog, Column,
                        LogicalTable, Decision, ExploratoryQueryResult, SecurityDecision)
from .executor import ResearchBudget
from .foundation import FoundationReadonlyExecutor
from .validator import Rejected, context_digest, identifier


@dataclass(frozen=True)
class EffectiveScope:
    user_id: str
    organization: str
    workspace: str
    permissions: frozenset[str]
    active: bool = True


@dataclass(frozen=True)
class SourcePolicy:
    """An existing permission's approved data contract, not a new permission.

    Partial row scopes are withheld: this phase has no row-policy compiler.
    columns=None explicitly approves all discovered columns for this source.
    """
    source: str
    permission: str
    organization: str
    workspace: str
    columns: tuple[str, ...] | None = None
    whole_dataset: bool = False


@dataclass(frozen=True)
class DiscoveredSource:
    name: str
    relation: str  # private trusted reference; never placed in model metadata
    columns: tuple[Column, ...]
    limitations: tuple[str, ...]


def discover(db, access, *, allowed_sources=None):
    """Metadata only, through existing reader contracts; no SELECT population.

    Reader's contract map is authoritative, not a second business-table list.
    New manifest datasets are attempted through relation(); unsupported contracts
    are reported as gaps, never guessed as physical SQL paths.
    """
    from ..datalake.foundation_reader import _COMPONENT_TABLES, FoundationReaderError
    from ..datalake.product_commercial_semantics import COMPONENT as SEMANTICS_COMPONENT
    sources, gaps = [], []
    components = access.manifest.get('components', {})
    candidates = []
    for component, entry in sorted(components.items()):
        datasets = entry.get('datasets', {}) if isinstance(entry, dict) else {}
        if component == 'reference':
            # Immutable publication directory, not arbitrary host discovery.
            for path in sorted(access.reference_path.iterdir()):
                if path.is_dir() and re.fullmatch(r'[a-z_][a-z0-9_]{0,48}', path.name):
                    name = 'ref_' + path.name
                    if allowed_sources is not None and name not in allowed_sources:
                        continue
                    physical = str(access.reference(path.name)).replace("'", "''")
                    candidates.append((name, f"read_parquet('{physical}')"))
            continue
        names = set(_COMPONENT_TABLES.get(component, ())) | set(datasets)
        if not names and allowed_sources is None:
            gaps.append(component + ':no_reader_dataset_contract')
        for name in sorted(names):
            if allowed_sources is not None and name not in allowed_sources:
                continue
            try:
                identifier(name)
                relation = (access.product_semantics_relation(name) if component == SEMANTICS_COMPONENT
                            else access.relation(component, name))
            except (FoundationReaderError, Rejected, ValueError):
                # File-backed extensions already carry immutable file hashes in
                # the selected publication. Do not guess Atomic table names.
                try:
                    relation = published_file_relation(access, component, name)
                except (FoundationReaderError, ValueError, OSError, KeyError, TypeError):
                    gaps.append(component + ':' + name + ':unsupported_reader_contract')
                    continue
            candidates.append((name, relation))
    for candidates_name, relation in candidates:
        schema = db.execute(f'DESCRIBE SELECT * FROM {relation}').fetchall()
        columns, projections = [], []
        for row in schema:
            # Generic SAP CamelCase -> logical snake_case, preserving the exact
            # physical identifier only inside the trusted projection.
            name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', row[0]).lower()
            try:
                identifier(name)
            except Rejected:
                continue
            typ = row[1].upper()
            # Trusted schemas can include nested/extension types; do not expose
            # unsupported types or interpolate them into projection SQL.
            if re.fullmatch(r'(VARCHAR|BOOLEAN|DATE|TIMESTAMP|BIGINT|INTEGER|SMALLINT|DOUBLE|FLOAT|DECIMAL\([0-9]+,[0-9]+\))', typ):
                columns.append(Column(name, typ, row[2] == 'YES'))
                original = '"' + row[0].replace('"', '""') + '"'
                projections.append(original + ' AS ' + identifier(name))
        if len({c.name for c in columns}) != len(columns):
            raise ValueError('ambiguous_normalized_column')
        relation = '(SELECT ' + ','.join(projections) + ' FROM ' + relation + ')'
        sources.append(DiscoveredSource(candidates_name, relation, tuple(columns), (
            'Schema discovery is not business semantic accreditation.',
            'Grain, relationships, currencies, units and calendar coverage are unaccredited unless independently checked.',
            'Published classification may be current, not historical; customer identifiers do not establish final DMS buyer.',
            'Line amounts are not automatically net billing or collections; credit memos require separate reconciliation.',
        )))
    if len({s.name for s in sources}) != len(sources):
        raise ValueError('ambiguous_published_dataset')
    return tuple(sources), tuple(gaps)


def published_file_relation(access, component, dataset):
    """Manifest-sealed files only, within DATA_ROOT; no latest/glob fallback."""
    import hashlib
    from pathlib import Path
    from ..datalake.ducklake import DATA_ROOT
    from ..datalake.foundation_publication import FoundationReaderError
    entry = access.manifest['components'][component]['datasets'][dataset]
    paths, hashes = entry['file_references'], entry['file_hashes']
    if not paths or len(paths) != len(hashes):
        raise FoundationReaderError('incomplete_published_file_contract')
    sealed = []
    for raw, expected in zip(paths, hashes):
        path = Path(raw).resolve()
        if DATA_ROOT.resolve() not in path.parents or path.suffix != '.parquet':
            raise FoundationReaderError('published_file_outside_data_root')
        sha = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                sha.update(chunk)
        if sha.hexdigest() != expected:
            raise FoundationReaderError('published_file_hash_mismatch')
        sealed.append("'" + str(path).replace("'", "''") + "'")
    return 'read_parquet([' + ','.join(sealed) + '], union_by_name=true)'


# Only contexts actually issued by backend composition pass the existing AST
# validator. Equality with caller-created metadata is not an authorization seal.
_BINDINGS = {}


def binding_for(context):
    entry = _BINDINGS.get(id(context))
    if entry is None or entry[0]() is not context:
        return None
    return entry[1]


class ResearchBinding:
    def __init__(self, *, resolve_scope, scope, publication, snapshot, sources,
                 policies, investigation_id, budget=None):
        """resolve_scope reuses backend effective authorization on EVERY access.

        It must return a fresh EffectiveScope (including current identity/tenant
        validity), not token-cached permissions. Fixtures use the identical port.
        No Console login, role interpretation or permission expansion occurs here.
        """
        self.resolve_scope = resolve_scope
        self.scope = scope
        self.policies = tuple(policies)
        selected, projections = [], {}
        for source in sources:
            matches = [p for p in self.policies if p.source == source.name
                       and p.organization == scope.organization and p.workspace == scope.workspace
                       and p.permission in scope.permissions and p.whole_dataset]
            if not matches:
                continue
            if len(matches) != 1:
                raise ValueError('ambiguous_source_policy')
            p = matches[0]
            columns = tuple(c for c in source.columns if p.columns is None or c.name in p.columns)
            if not columns:
                continue
            selected.append(LogicalTable(source.name, columns, p.permission, (), 1000000, source.limitations))
            projections[source.name] = source.relation
        self.projections = MappingProxyType(projections)
        catalog = Catalog('telchi_authorized_foundation_dev_v1', scope.organization,
                          scope.workspace, publication, str(snapshot), tuple(selected), (), False)
        self.context = AuthorizedExecutionContext(scope.user_id, scope.organization,
            scope.workspace, 'dev', scope.permissions, catalog, tuple(projections), publication,
            str(snapshot), budget or Budget(), investigation_id)
        key = id(self.context)
        # Weak reference avoids retaining another user's context through a global
        # catalog. Binding lifecycle must be explicitly closed by the caller.
        self._digest = context_digest(self.context)
        def release(_):
            _BINDINGS.pop(key, None)
        _BINDINGS[key] = (weakref.ref(self.context, release), weakref.ref(self, release))
        self.check()

    def check(self):
        try:
            current = self.resolve_scope()
        except Exception:
            raise Rejected('authorization_unavailable', Decision.DENY) from None
        if not isinstance(current, EffectiveScope):
            raise Rejected('authorization_unavailable', Decision.DENY)
        if (not current.active or (current.user_id, current.organization, current.workspace) !=
                (self.scope.user_id, self.scope.organization, self.scope.workspace)
                or not self.scope.permissions <= current.permissions):
            raise Rejected('authorization_changed', Decision.DENY)
        return current

    def close(self):
        _BINDINGS.pop(id(self.context), None)

    def present(self, value, context):
        """Also gates prior evidence/resume. Never return stale protected content."""
        if context is not self.context:
            raise Rejected('evidence_owner_mismatch', Decision.DENY)
        authorize_issued(context)
        return value


def authorize_issued(context):
    ref = binding_for(context)
    binding = ref() if ref else None
    if binding is None or context_digest(context) != binding._digest:
        raise Rejected('unauthorized_context', Decision.DENY)
    binding.check()
    return binding


class AuthorizedFoundationExecutor(FoundationReadonlyExecutor):
    """Same investigator executor, AST, deadlines and resource guard, new views."""
    def __init__(self, context, *, reader=None, authorized=False):
        self.binding = authorize_issued(context)
        self.context, self.reader = context, reader
        self.budget = ResearchBudget(context.effective_budget)
        self._execution_seconds, self._closed = 0.0, False
        self.last_preflight = None
        import threading
        self.cancel = threading.Event()

    def _prepare_connection(self, db, context):
        binding = authorize_issued(context)
        if db.execute("SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'").fetchone() != (True,):
            raise ValueError('foundation_not_readonly')
        access = self.reader.resolve_on(db)
        if (access.foundation_publication_id, str(access.ducklake_snapshot_id)) != (context.publication, context.snapshot):
            raise ValueError('foundation_binding_changed')
        for table in context.catalog.tables:
            projection = ','.join(identifier(c.name) for c in table.columns)
            db.execute(f'CREATE TEMP VIEW {identifier(table.name)} AS SELECT {projection} FROM {binding.projections[table.name]}')
        db.execute("SET schema='main'")

    def execute(self, proposal, context, *, cancel=None):
        try:
            authorize_issued(context)
        except Rejected as exc:
            return SecurityDecision(Decision.DENY, exc.reason), ExploratoryQueryResult('', status='NOT_EXECUTED')
        decision, result = super().execute(proposal, context, cancel=cancel or self.cancel)
        try:
            authorize_issued(context)
        except Rejected:
            return SecurityDecision(Decision.DENY, 'authorization_changed'), ExploratoryQueryResult('', status='NOT_EXECUTED')
        return decision, replace(result, source=context.catalog.dataset,
            publication=context.publication, snapshot=context.snapshot)


def open_binding(*, reader, resolve_scope, policies, investigation_id, budget=None):
    """Resolve one publication and discover its actual schemas, guarded before I/O."""
    from .foundation import host_read_preflight
    scope = resolve_scope()
    if not scope.active:
        raise Rejected('unauthorized_identity', Decision.DENY)
    if not host_read_preflight()['safe']:
        raise Rejected('host_io_or_memory_pressure', Decision.RESOURCE_BLOCKED)
    policies = tuple(policies)
    allowed_sources = {p.source for p in policies if p.organization == scope.organization
                       and p.workspace == scope.workspace and p.whole_dataset
                       and p.permission in scope.permissions}
    with reader.connector.session(read_only=True) as db:
        access = reader.resolve_on(db)
        sources, gaps = discover(db, access, allowed_sources=allowed_sources)
        binding = ResearchBinding(resolve_scope=resolve_scope, scope=scope,
            publication=access.foundation_publication_id, snapshot=access.ducklake_snapshot_id,
            sources=sources, policies=policies, investigation_id=investigation_id, budget=budget)
    return binding, gaps


async def console_scope(conn, principal, *, organization, workspace, validate_identity, repository=None):
    """Backend adapter; authenticated ConsolePrincipal plus live identity check.

    validate_identity is the existing consumer's organization/workspace/active
    identity validation. Effective permissions alone do not prove tenant binding.
    Async service callers must supply a fresh synchronous resolver to the DEV
    executor (e.g. a backend-owned worker bridge); the CLI does not impersonate it.
    """
    from modules.console.repositories import PermissionConsoleRepository
    if not await validate_identity(conn, principal, organization, workspace):
        raise Rejected('unauthorized_identity', Decision.DENY)
    permissions = await (repository or PermissionConsoleRepository()).list_effective_permissions(
        conn, workspace, principal.user_id)
    return EffectiveScope(principal.user_id, organization, workspace, frozenset(permissions))
