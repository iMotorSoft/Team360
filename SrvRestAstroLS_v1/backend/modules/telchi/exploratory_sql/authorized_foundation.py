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

# Columns that SAP publishes as VARCHAR but are monetary/quantity in nature.
# Mapping them to a logical DECIMAL type lets the view cast at query time
# without the model emitting CAST (unsupported by the V1 validator).
LOGICAL_NUMERIC_COLUMNS = frozenset({
    'doc_total', 'doc_total_system', 'doc_total_foreign',
    'line_total', 'quantity', 'price',
})


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
    # Receipts for existing backend projections, not a second join catalog.
    projection_contracts: tuple[dict, ...] = ()


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
    # Operational observations are published parquet files under a separate
    # reader contract, not Atomic latest. Their physical path and hash are in
    # the manifest; the reader already validates them via FoundationReader.
    from ..datalake.operational_domains import GROUPS as OBS_GROUPS
    dataset_to_domain = {}
    for domain, datasets in OBS_GROUPS.items():
        for dataset in datasets:
            dataset_to_domain[dataset] = domain
    operational = access.manifest.get('operational_observations', {})
    for dataset, entry in sorted((operational.get('datasets') or {}).items()):
        domain = dataset_to_domain.get(dataset)
        if domain is None:
            continue
        name = 'observed_' + dataset
        if allowed_sources is not None and name not in allowed_sources:
            continue
        identifier(name)
        candidates.append((name, access.operational_observation(domain, dataset)))
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
            # SAP publishes monetary and quantity columns as VARCHAR. Trust a
            # conservative logical type so the view can cast them at query time
            # without the model needing CAST in its SQL.
            if name in LOGICAL_NUMERIC_COLUMNS:
                typ = 'DECIMAL(38,6)'
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


def classify_authorized_products(db, sources, policies, scope):
    """Reuse the canonical kernel over authorized published evidence, in memory.

    No taxonomy/rules or business queries are defined here. Both full input
    contracts must be granted; column/row-restricted policies never gain derived
    information. The small crosswalk is bounded and immutable for this binding.
    """
    names = {'ref_products', 'material_supply_status'}
    approved = [p for p in policies if p.source in names and p.whole_dataset
                and p.columns is None and p.organization == scope.organization
                and p.workspace == scope.workspace and p.permission in scope.permissions]
    by_name = {s.name: s for s in sources}
    if {p.source for p in approved} != names or not names <= by_name.keys():
        return sources, ()
    products, materials = (by_name[n] for n in ('ref_products', 'material_supply_status'))
    required = {'item_code', 'sap_item_name', 'sap_itms_grp_cod', 'sap_invnt_item',
                'sap_sell_item', 'sap_prchse_item', 'sap_valid_for', 'source_system'}
    if (not required <= {c.name for c in products.columns}
            or not {'item_code', 'is_raw_material'} <= {c.name for c in materials.columns}):
        return sources, ('product_classification:missing_published_evidence_columns',)
    facts = db.execute(f'''SELECT p.item_code,p.sap_item_name,p.sap_itms_grp_cod,
        p.sap_invnt_item,p.sap_sell_item,p.sap_prchse_item,p.sap_valid_for,m.is_raw_material
        FROM {products.relation} p JOIN
        (SELECT DISTINCT item_code,is_raw_material FROM {materials.relation}) m
        ON p.item_code=m.item_code WHERE p.source_system='SAP_HANA' LIMIT 5001''').fetchall()
    if len(facts) > 5000 or len({r[0] for r in facts}) != len(facts):
        return sources, ('product_classification:bounded_unique_evidence_required',)
    if not facts:
        return sources, ('product_classification:no_published_evidence',)
    from ..datalake.product_business_classification import ProductFacts, classify_product
    rows = []
    for code, name, group, inv, sell, purchase, active, leaf in facts:
        try:
            group = int(group) if group is not None else None
        except (ValueError, TypeError):
            group = None
        classified = classify_product(ProductFacts(code, name, group, None,
            inv == 'Y', sell == 'Y', purchase == 'Y', active == 'Y',
            is_bom_component=leaf is True))
        rows.append((code, classified.product_business_type, classified.status,
                     classified.rule_id, classified.evidence))
    fields = ('item_code', 'product_business_type', 'classification_status',
              'classification_rule_id', 'classification_evidence')
    if set(fields[1:]) & {c.name for c in products.columns}:
        return sources, ('product_classification:existing_columns_not_overridden',)
    # Values are trusted kernel outputs / published identifiers, never model SQL.
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    values = ','.join('(' + ','.join(quote(v) for v in row) + ')' for row in rows)
    crosswalk = "(SELECT *, 'SAP_HANA' AS source_system FROM (VALUES " + values + ') AS v(' + ','.join(fields) + ')) AS b'
    derived = replace(products,
        relation='(SELECT p.*, ' + ','.join('b.' + f for f in fields[1:])
            + f' FROM {products.relation} p LEFT JOIN {crosswalk}'
            + " ON p.item_code=b.item_code AND p.source_system=b.source_system)",
        columns=products.columns + tuple(Column(f, 'VARCHAR', True) for f in fields[1:]),
        projection_contracts=products.projection_contracts + (dict(
            origin='classify_authorized_products',
            version='TELCHI_PRODUCT_BUSINESS_CLASSIFICATION_V1',
            sources=sorted(names), authority='CHECKED_BACKEND_PROJECTION_ONLY',
            relationship='ref_products.item_code = material_supply_status.item_code; SAP_HANA products only',
            checks=['bounded unique product evidence', 'all input sources and columns authorized'],
            limitations=['Current published evidence, not historical classification or a general join grant.']),),
        limitations=products.limitations + (
            'product_business_type uses existing TELCHI_PRODUCT_BUSINESS_CLASSIFICATION_V1 '
            'on published SAP groups plus material_supply_status structural evidence; '
            'not the legacy BOM leaf flag alone. NULL means unclassified, not OTHER. '
            'Coverage is limited to published evidence, not historical classification.',))
    return tuple(derived if s.name == products.name else s for s in sources), ()


def enrich_authorized_sales_lines(db, sources, policies, scope):
    """Existing sales-operation projection pattern, without new operations/grants.

    Document/product/customer dimensions are many-to-one, checked before exposure.
    Keep the original line population and amount; never project header money onto
    lines. Full input contracts are required, as for product classification.
    """
    names = {'sales_line', 'sales_document', 'ref_products', 'ref_customers'}
    approved = {p.source for p in policies if p.source in names and p.whole_dataset
                and p.columns is None and p.organization == scope.organization
                and p.workspace == scope.workspace and p.permission in scope.permissions}
    by_name = {s.name: s for s in sources}
    if approved != names or not names <= by_name.keys():
        return sources, ()
    line, doc, product, customer = (by_name[n] for n in
        ('sales_line', 'sales_document', 'ref_products', 'ref_customers'))
    dimensions = (
        (doc, 'd', 'doc_entry', "source_system='SAP_B1_HANA' AND source_table='OINV'",
         ('doc_date', 'doc_month', 'card_code', 'canceled', 'sales_channel_code')),
        (product, 'p', 'item_code', "source_system='SAP_HANA'",
         ('sap_item_name', 'product_business_type', 'classification_status', 'classification_rule_id')),
        (customer, 'c', 'code', "source_system='SAP_HANA'", ('name',)),
    )
    extra, projections, relations = [], [], {}
    aliases = {'sap_item_name': 'product_name', 'name': 'customer_name'}
    existing = {c.name for c in line.columns}
    for source, alias, key, predicate, fields in dimensions:
        columns = {c.name: c for c in source.columns}
        if not {key, 'source_system'} <= columns.keys():
            return sources, ('sales_line_dimensions:missing_keys',)
        relation = f'(SELECT * FROM {source.relation} WHERE {predicate})'
        if db.execute(f'SELECT {key} FROM {relation} GROUP BY {key} HAVING count(*)>1 LIMIT 1').fetchone():
            return sources, ('sales_line_dimensions:nonunique_' + source.name,)
        # Source identity is a join KEY, not a left-only residual in ON.
        # DuckDB otherwise chooses BLOCKWISE_NL_JOIN for these LEFT joins.
        if alias == 'd':
            month = ', substr(doc_date,1,7) AS doc_month' if 'doc_date' in columns else ''
            relation = f"(SELECT *, 'INV1' AS _line_source_table{month} FROM {relation})"
            if month:
                columns['doc_month'] = Column('doc_month', 'VARCHAR', True)
        elif alias == 'p':
            relation = f"(SELECT *, 'SAP_B1_HANA' AS _line_source_system FROM {relation})"
        relations[alias] = relation
        for field in fields:
            name = aliases.get(field, field)
            if field in columns and name not in existing:
                extra.append(replace(columns[field], name=name, nullable=True))
                projections.append(f'{alias}.{identifier(field)} AS {identifier(name)}')
    if not extra:
        return sources, ()
    relation = ('(SELECT l.*,' + ','.join(projections) + f' FROM {line.relation} l'
        + f" LEFT JOIN {relations['d']} d ON l.doc_entry=d.doc_entry"
        + " AND l.source_system=d.source_system AND l.source_table=d._line_source_table"
        + f" LEFT JOIN {relations['p']} p ON l.item_code=p.item_code"
        + " AND l.source_system=p._line_source_system"
        + f" LEFT JOIN {relations['c']} c ON d.card_code=c.code)")
    enriched = replace(line, relation=relation, columns=line.columns + tuple(extra),
        projection_contracts=line.projection_contracts + (dict(
            origin='enrich_authorized_sales_lines', version='1', sources=sorted(names),
            authority='CHECKED_BACKEND_PROJECTION_ONLY',
            relationships=[
                'sales_line -> sales_document: doc_entry + source_system; INV1 -> OINV only',
                'sales_line -> ref_products: item_code; SAP_B1_HANA -> SAP_HANA only',
                'sales_document -> ref_customers: card_code -> code; SAP_HANA customers only'],
            cardinality='LEFT many-to-one; right keys checked unique in this binding',
            measure='line_total unchanged; never sum header doc_total after joining lines',
            grain='Original sales_line population retained; missing dimensions remain NULL',
            checks=['right-key uniqueness after source predicates', 'all input sources and columns authorized'],
            limitations=['Use projected columns directly; not accreditation of arbitrary raw-source joins.',
                         'No complete calendar, historical classification or net-billing accreditation.']),),
        limitations=line.limitations + (
            'Document/product/customer columns are many-to-one published SAP dimensions '
            'with checked key uniqueness; unmatched rows retain NULL dimensions. '
            'Filter canceled=N, source_table=INV1 and currency explicitly. '
            'line_total remains commercial line money BEFORE credit memos, not net billing.',))
    return tuple(enriched if s.name == line.name else s for s in sources), ()


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
        # The canonical reader has already checked the publisher's receipt.
        # Legacy publications without a receipt retain physical verification.
        if not getattr(access, 'read_binding', None):
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


# Adapter from the existing published dimension projections to workspace meanings.
# No definitions, grants or join rules live here; unknown mappings are withheld.
DIMENSION_CONTRACTS = {
    'commercial_channel': {
        'sales_document': ('sales_channel_code', 'sales_channel_name'),
        'credit_memo_document': ('sales_channel_code', 'sales_channel_name')},
    'product_business_type': {
        'ref_products': ('product_business_type', 'classification_status', 'classification_rule_id')},
}


def authorized_business_resolution(resolution, scope, policies, available_sources=None):
    """Filter BEFORE interpreter/audit as well as before investigator transport."""
    from copy import deepcopy
    result = deepcopy(resolution or {})
    for key in ('concepts', 'interpretation_concepts', 'context_concepts'):
        selected = []
        for concept in result.get(key, []):
            if (concept.get('approval_status') != 'published'
                    or concept.get('workspace_id') not in (None, scope.workspace)):
                continue
            dimension = concept.get('operational_context', {}).get('dimension')
            contracts = DIMENSION_CONTRACTS.get(dimension, {})
            allowed = []
            for source, columns in contracts.items():
                if available_sources is not None and (source not in available_sources
                        or not set(columns) <= {c.name for c in available_sources[source].columns}):
                    continue
                matches = [p for p in policies if p.source == source
                    and p.organization == scope.organization and p.workspace == scope.workspace
                    and p.whole_dataset and p.permission in scope.permissions
                    and (p.columns is None or set(columns) <= set(p.columns))]
                if len(matches) == 1:
                    allowed.append(source)
            if not allowed:
                continue
            concept.pop('related_evidence', None)  # No accredited entity/rule source mapping.
            concept['source_applicability'] = dict(dimension=dimension, sources=sorted(allowed),
                authority='Published workspace meaning on authorized dimensions; not historical data or join accreditation')
            selected.append(concept)
        result[key] = selected
    if not result.get('interpretation_concepts') and not result.get('context_concepts'):
        result.update(status='unknown', ambiguous=False)
    # Preserve the original veto without disclosing rejected contract identities.
    result['semantic_guard'] = dict(requires_clarification=bool(
        (resolution or {}).get('semantic_guard', {}).get('requires_clarification')))
    return result


def selected_business_knowledge(envelope, scope, publication, snapshot):
    """Transport the EXISTING resolver's selected meanings, not a SQL authority.

    The semantics repository authorizes published meanings at workspace scope.
    Its entity/rule evidence has no SourcePolicy mapping today: withhold that
    evidence rather than leak source-specific IDs or promote it to known joins.
    Publication applicability must still be established by the investigator.
    """
    if not envelope:
        return {}
    receipt = envelope.get('scope', {})
    if any(receipt.get(k) != v for k, v in (
            ('user_id', scope.user_id), ('organization', scope.organization),
            ('workspace', scope.workspace), ('permissions', sorted(scope.permissions)))):
        raise Rejected('knowledge_scope_mismatch', Decision.DENY)
    resolution = envelope.get('resolution') or {}
    selected, seen = [], set()
    for concept in (resolution.get('interpretation_concepts', [])
                    + resolution.get('context_concepts', [])):
        key = (concept.get('concept_id'), concept.get('version'))
        if key in seen or concept.get('approval_status') != 'published':
            continue
        if concept.get('workspace_id') not in (None, scope.workspace):
            raise Rejected('knowledge_scope_mismatch', Decision.DENY)
        seen.add(key)
        selected.append({k: concept[k] for k in (
            'concept_id', 'semantic_code', 'version', 'canonical_name', 'definition',
            'concept_type', 'source', 'approval_status', 'operational_context',
            'match', 'score', 'selection_reason', 'source_applicability') if k in concept})
        if len(selected) == 6:
            break
    if not selected:
        return {}
    result = dict(concepts=selected, publication=publication, snapshot=str(snapshot),
        authority='Published workspace business meanings; not Foundation dataset accreditation or SQL authority.',
        limitations=[
            'Approximate matches remain candidates; resolve ambiguity against the question and observed data.',
            'Entity/rule evidence withheld: no accredited SourcePolicy/column mapping in the semantic repository.',
            'Do not infer historical validity, source coverage, measures or permitted joins from a business definition.',
            'Exploratory findings never become permanent business rules automatically.'])
    from .validator import canonical
    if len(canonical(result).encode()) > 12000:
        raise Rejected('knowledge_context_budget', Decision.DENY)
    return result


class ResearchBinding:
    def __init__(self, *, resolve_scope, scope, publication, snapshot, sources,
                 policies, investigation_id, budget=None, business_knowledge=None):
        """resolve_scope reuses backend effective authorization on EVERY access.

        It must return a fresh EffectiveScope (including current identity/tenant
        validity), not token-cached permissions. Fixtures use the identical port.
        No Console login, role interpretation or permission expansion occurs here.
        """
        self.resolve_scope = resolve_scope
        self.scope = scope
        self.policies = tuple(policies)
        if business_knowledge:
            business_knowledge = dict(business_knowledge, resolution=authorized_business_resolution(
                business_knowledge.get('resolution'), scope, self.policies,
                available_sources={s.name: s for s in sources}))
        self.business_knowledge = selected_business_knowledge(
            business_knowledge, scope, publication, snapshot)
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
            # Conservative source estimate: result_rows bounds output, not rows
            # scanned or join work. Derived LIMITs can prove smaller bounds.
            selected.append(LogicalTable(source.name, columns, p.permission, (), 1000000, source.limitations))
            projections[source.name] = source.relation
        # A projection receipt may mention several sources: expose it only if
        # EVERY dependency has one full, currently authorized SourcePolicy.
        # Serialize on the selected table so progressive discovery supplies only
        # relevant receipts, never unrelated source names or physical relations.
        import hashlib
        import inspect
        from .validator import canonical
        # Version the transport separately from business accreditation. Pin the
        # actual existing projection implementation, not an invented rule version.
        projection_versions = {f.__name__: hashlib.sha256(inspect.getsource(f).encode()).hexdigest()
            for f in (classify_authorized_products, enrich_authorized_sales_lines)}
        full_sources = {s.name for s in sources if len([p for p in self.policies
            if p.source == s.name and p.organization == scope.organization
            and p.workspace == scope.workspace and p.permission in scope.permissions
            and p.whole_dataset and p.columns is None]) == 1}
        source_map = {s.name: s for s in sources}
        selected = [replace(t, semantic_constraints=t.semantic_constraints + tuple(
            'Backend projection receipt: ' + canonical(dict(receipt,
                publication=publication, snapshot=str(snapshot),
                implementation_sha256=projection_versions.get(receipt['origin'])))
            for receipt in source_map[t.name].projection_contracts
            if t.name in full_sources and set(receipt['sources']) <= full_sources))
            for t in selected]
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
            projections = []
            for c in table.columns:
                if c.sql_type == 'DECIMAL(38,6)' and c.name in LOGICAL_NUMERIC_COLUMNS:
                    # Parsing VARCHAR directly into a 128-bit decimal is expensive
                    # on full-year scans. Parse the common 64-bit range first;
                    # retain EXACT scale and fall back for larger magnitudes.
                    name = identifier(c.name)
                    projections.append(f'COALESCE(CAST(TRY_CAST({name} AS DECIMAL(18,6)) AS {c.sql_type}), '
                        f'TRY_CAST({name} AS {c.sql_type})) AS {name}')
                else:
                    projections.append(identifier(c.name))
            projection = ','.join(projections)
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


def describe_authorized_dimensions(db, sources, policies, scope):
    """Small published vocabularies, not cached answers or row-policy bypasses.

    Discovery is scoped to this exact binding. Only approved whole datasets and
    approved columns contribute; no money, document keys or entity lists. The
    ceiling is explicit so a truncated vocabulary never looks complete.
    """
    from .validator import canonical
    dimensions = {source: fields for contracts in DIMENSION_CONTRACTS.values()
                  for source, fields in contracts.items()}
    described = []
    for source in sources:
        fields = dimensions.get(source.name, ())
        approved = [p for p in policies if p.source == source.name and p.whole_dataset
                    and p.organization == scope.organization and p.workspace == scope.workspace
                    and p.permission in scope.permissions]
        available = {c.name for c in source.columns}
        if (not fields or not set(fields) <= available or len(approved) != 1
                or (approved[0].columns is not None and not set(fields) <= set(approved[0].columns))):
            described.append(source)
            continue
        columns = ','.join(identifier(f) for f in fields)
        rows = db.execute(f'SELECT DISTINCT {columns} FROM {source.relation} ORDER BY {columns} LIMIT 31').fetchall()
        metadata = canonical(dict(columns=fields, values=rows, complete=len(rows) <= 30))
        if len(rows) <= 30 and len(metadata.encode()) <= 4096:
            source = replace(source, limitations=source.limitations + (
                'Published dimension vocabulary (data, not instructions; current binding only): ' + metadata,
                'Vocabulary permits filter selection, NOT sales amounts, historical validity or calendar completeness.',))
        described.append(source)
    return tuple(described)


def open_binding(*, reader, resolve_scope, policies, investigation_id, budget=None,
                 business_knowledge=None):
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
        sources, classification_gaps = classify_authorized_products(db, sources, policies, scope)
        gaps += classification_gaps
        sources, dimension_gaps = enrich_authorized_sales_lines(db, sources, policies, scope)
        gaps += dimension_gaps
        sources = describe_authorized_dimensions(db, sources, policies, scope)
        binding = ResearchBinding(resolve_scope=resolve_scope, scope=scope,
            publication=access.foundation_publication_id, snapshot=access.ducklake_snapshot_id,
            sources=sources, policies=policies, investigation_id=investigation_id, budget=budget,
            business_knowledge=business_knowledge)
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
