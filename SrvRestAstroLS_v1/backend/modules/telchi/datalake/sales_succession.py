"""Commercial accreditation inherited through canonical, validated succession.

Historical IDs below are accreditation roots, not a list of future releases.
Only the existing manifest ancestry can connect a successor to those roots.
No worker-supplied assertion is treated as evidence by the parent process.
"""
from contextlib import contextmanager
import hashlib

from .foundation_publication import FoundationPublicationStore, FoundationReaderError

SALES_ROOT = 'foundation_38680850adc058b1bb11887632b7b681'
PHYSICAL_ROOT = 'foundation_881005a5a694a25dc806233dcb3838ac'
ROOT_SNAPSHOT = 1408


def validate_successor(store, publication, snapshot, *, physical=False, category_legacy=False, _reader_validated=False):
    from .foundation_manifest import validate_manifest
    from .sales_facts_transition import KIND, verify_files
    from .reference_compatibility import KIND as REFERENCE_KIND
    from .independent_facts_succession import KIND as INDEPENDENT_KIND
    if not _reader_validated:
        validate_manifest(store, publication)
    root = PHYSICAL_ROOT if physical else SALES_ROOT
    # The original category-only accreditation predates the sealed-sales root.
    # It remains a historical endpoint, never a shortcut for future ancestry.
    if category_legacy and not physical and publication.foundation_publication_id == 'foundation_afd08d9eca6a725be53cdc3f9d5709c9':
        root = publication.foundation_publication_id
    current = publication
    seen = set()
    while current.foundation_publication_id != root:
        identity = current.foundation_publication_id
        if identity in seen or len(seen) >= 32:
            raise FoundationReaderError('Commercial succession ancestry invalid')
        seen.add(identity)
        m = current.manifest
        base = store.get(m.get('base_foundation_publication_id', ''))
        if base is None:
            raise FoundationReaderError('Commercial succession lineage missing')
        if m.get('candidate_kind') == KIND:
            if not m.get('sales_facts_revalidation', {}).get('incremental_plan'):
                raise FoundationReaderError('Commercial succession requires incremental reconciliation')
            if not _reader_validated:
                verify_files(m)
        elif m.get('candidate_kind') == INDEPENDENT_KIND:
            # Canonical validation above already replayed the changed stock and
            # proved sales, Reference, permissions and classification unchanged.
            pass
        elif m.get('candidate_kind') == REFERENCE_KIND:
            mutable = {'foundation_publication_id', 'update_run_id', 'candidate_kind',
                       'base_foundation_publication_id', 'reference_version', 'components',
                       'reference_compatibility', 'reference_compatibility_adapter',
                       'reference_data_snapshot_id', 'manifest_schema_version', 'precommit_validation'}
            if ({k:v for k,v in m.items() if k not in mutable} !=
                    {k:v for k,v in base.manifest.items() if k not in mutable}):
                raise FoundationReaderError('Commercial inherited contract changed')
            # The canonical Reference adapter permits physical re-observation.
            # Inherited accreditation is stricter: preserve all physical values.
            if physical:
                from .reference_update import read_parquet_rows, PHYSICAL_FIELDS
                from .ducklake import DATA_ROOT
                from .sales_reference_release import _projected_rows
                paths = [DATA_ROOT/'reference/_versions'/p.reference_version/'products/part-00000.parquet'
                         for p in (base, current)]
                old, new = [read_parquet_rows(p) for p in paths]
                if m.get('reference_compatibility_adapter'):
                    from .full_refresh_reference import ADAPTER
                    if m['reference_compatibility_adapter'] != ADAPTER:
                        raise FoundationReaderError('Commercial Reference adapter unsupported')
                    # Canonical append validation preserves every old row and
                    # derives additions from hash-verified captured masters.
                    old_keys = {(r['source_system'], r['source_native_id']) for r in old[2]}
                    new = (new[0], new[1], [r for r in new[2]
                           if (r['source_system'], r['source_native_id']) in old_keys])
                fields = ['source_system', 'source_native_id', *PHYSICAL_FIELDS]
                types = dict(zip(old[0], old[1]))
                if (any(f not in types or f not in new[0] for f in fields)
                        or _projected_rows(old[2], fields, [types[f] for f in fields]) !=
                           _projected_rows(new[2], fields, [types[f] for f in fields])):
                    raise FoundationReaderError('Commercial physical accreditation lost')
        else:
            raise FoundationReaderError('Commercial succession adapter unsupported')
        current = base
    if snapshot != ROOT_SNAPSHOT:
        raise FoundationReaderError('Commercial succession data snapshot changed')
    from .ducklake import DATA_ROOT
    from .category_line_amount_query import CROSSWALK_SHA256
    classification = DATA_ROOT/'crosswalk/_versions'/publication.reference_version/'product_business_type/part-00000.parquet'
    if hashlib.sha256(classification.read_bytes()).hexdigest() != CROSSWALK_SHA256:
        raise FoundationReaderError('Commercial category accreditation lost')
    if physical:
        from .commercial_line_amount_by_query import PHYSICAL_PRODUCTS_SHA256, PHYSICAL_CROSSWALK_SHA256
        paths = [(DATA_ROOT/'reference/_versions'/current.reference_version/'products/part-00000.parquet', PHYSICAL_PRODUCTS_SHA256),
                 (DATA_ROOT/'crosswalk/_versions'/current.reference_version/'product_crosswalk/part-00000.parquet', PHYSICAL_CROSSWALK_SHA256)]
        if any(hashlib.sha256(p.read_bytes()).hexdigest() != sha for p, sha in paths):
            raise FoundationReaderError('Commercial physical accreditation root changed')
    return publication


def admit(access, connection, *, physical=False, category_legacy=False):
    """Use the caller's read-only catalog session and already-resolved reader."""
    @contextmanager
    def same():
        yield connection
    store = FoundationPublicationStore(same)
    publication = store.get(access.foundation_publication_id)
    if publication is None or publication.manifest != access.manifest:
        raise FoundationReaderError('Commercial succession manifest mismatch')
    # FoundationReader has just validated the entire canonical ancestry and
    # physical facts on this connection. Reuse that guarantee, not a second
    # full master projection scan. No external result can set this flag.
    validate_successor(store, publication, access.ducklake_snapshot_id,
                       physical=physical, category_legacy=category_legacy, _reader_validated=True)
    return physical_metadata(access) if physical else None


def physical_metadata(access):
    """Hashes of the canonical Reference, after ancestry/preservation validation."""
    from .ducklake import DATA_ROOT
    products = access.reference('products')
    crosswalk = DATA_ROOT/'crosswalk/_versions'/access.foundation.reference_version/'product_crosswalk/part-00000.parquet'
    return dict(reference=access.foundation.reference_version,
                products_sha256=hashlib.sha256(products.read_bytes()).hexdigest(),
                crosswalk_sha256=hashlib.sha256(crosswalk.read_bytes()).hexdigest())


def source_metadata(access):
    """Publication identity and source cutoff are distinct from master refresh."""
    result = dict(publication_id=access.foundation_publication_id,
                  snapshot_id=access.ducklake_snapshot_id, updated_at=access.foundation_data_as_of)
    ledger = getattr(access, 'manifest', {}).get('sales_coverage', [])
    if ledger:
        result.update(reference_version=access.foundation.reference_version,
            sales_cutoff=max(access.manifest['components'][d]['source_as_of'] for d in ('sales', 'credit_memo')),
            coverage_start=min(w['start'] for w in ledger),
            coverage_end_exclusive=min(max(w['end'] for w in ledger if w['domain'] == d and w.get('complete'))
                                       for d in ('sales', 'credit_memo')))
    return result


def result_binding(source, *, physical=False):
    """Re-resolve CURRENT for a new binding; never trust a self-attested receipt.

    Legacy exact bindings remain checked by each adapter. New result envelopes
    must match the canonical current publication, snapshot AND update instant.
    A concurrent promotion causes a safe rejection/retry, not mixed results.
    """
    from .ducklake import DuckLakeConnector
    from .foundation_reader import FoundationReader
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as con:
        con.execute('SET threads=1')
        con.execute("SET memory_limit='512MB'")
        access = FoundationReader(connector).resolve_on(con)
        expected = source_metadata(access)
        if source != expected:
            raise ValueError('commercial_result_binding_mismatch')
        return admit(access, con, physical=physical)


class _AdmittedResult(dict):
    """Process-local result of parent validation; JSON cannot carry this type."""


def mark_result(result):
    marked = _AdmittedResult(result)
    marked.admitted_source = dict(result['source'])
    physical = result.get('physical_classification')
    marked.physical_binding = ({k:physical[k] for k in ('reference', 'products_sha256', 'crosswalk_sha256')}
                               if physical else None)
    return marked


def admitted_source(result):
    if isinstance(result, _AdmittedResult) and result.get('source') == result.admitted_source:
        return result.admitted_source
    return None


def accepts_result(source, legacy, *, physical=False, _admitted=None):
    if _admitted is not None and source == _admitted:
        return True
    if (source.get('publication_id'), source.get('snapshot_id')) in legacy:
        return True
    # Arbitrary names cannot trigger catalog I/O or become an accreditation.
    identity = source.get('publication_id', '')
    if (not isinstance(identity, str) or len(identity) != 43 or not identity.startswith('foundation_')
            or any(c not in '0123456789abcdef' for c in identity[11:])):
        return False
    try:
        result_binding(source, physical=physical)
        return True
    except Exception:
        return False
