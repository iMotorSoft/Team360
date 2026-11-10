"""Versioned sales facts transition, retaining immutable historical derivations.

Only a fully reconciled cycle can build this envelope. It is not a permission
to activate a candidate. Independent datasets remain pinned to their original
source snapshots, cutoffs and fingerprints; they are not recertified as current
October collections, stock, purchasing or Material Supply.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from . import sales_incremental as inc
from .sales_continuity_candidate import TABLES
from .foundation_publication import ComponentReference, FoundationPublication, FoundationReaderError
from .foundation_manifest import _hash

KIND='SALES_FACTS_TRANSITION_V1'
NAMES={'reference','sales','credit_memo','oinm','oitw','material_supply','purchasing','receivables_collections'}


def uses_sealed_sales(manifest):
    """Dispatch only after canonical manifest validation, never as a validator.

    Reference-only successors preserve the exact sales contracts and provenance
    of their validated ancestor. They must keep using those sealed relations.
    """
    from .reference_compatibility import KIND as REFRESH_KIND
    from .independent_facts_succession import KIND as INDEPENDENT_KIND
    from .foundation_manifest import EXTENSIBLE_KIND
    kind = manifest.get('candidate_kind')
    return (kind == KIND or (kind in {REFRESH_KIND, INDEPENDENT_KIND, EXTENSIBLE_KIND}
            and isinstance(manifest.get('sales_facts_revalidation'), dict)))


def _identity(stable):
    return _hash(stable)


def make_candidate(base, report_path, capture_root):
    from . import sales_continuity as cap
    report=inc.read_json(report_path)
    with inc.locked(capture_root):
        plan,receipts,commits,cursors,finished=cap.recover(capture_root)
    material_replay=report.get('material_revalidation')
    material_valid=report['material_supply']['unchanged'] or (material_replay and material_replay['status']=='REPLAY_PASS')
    if (report['blockers'] or not material_valid
            or len(finished)!=len(plan['windows']) or any(report['reference_missing'].values())
            or report['base_publication']!=base.foundation_publication_id
            or report['capture_plan_sha256']!=inc.file_hash(capture_root/'plan.json')):
        raise FoundationReaderError('Sales facts transition prerequisites not satisfied')
    if set(base.manifest['components'])!=NAMES:
        raise FoundationReaderError('Sales facts transition requires the accredited eight-component base')
    coverage=[]
    for window in plan['windows']:
        units=[c for c in commits if c['window']==window['id']]
        coverage.append(dict(window,complete=True,documents=sum(u['metrics']['documents'] for u in units),
                             lines=sum(u['metrics']['lines'] for u in units),
                             checkpoint_sha256=inc.digest(units)))
    incremental_plan=report.get('incremental_plan')
    if incremental_plan:
        from .sales_refresh_cycle import validate_plan
        validate_plan(incremental_plan)
        if incremental_plan!=plan or plan['base']!=base.foundation_publication_id or plan['base_manifest_sha256']!=inc.digest(base.manifest):
            raise FoundationReaderError('Incremental plan/base binding mismatch')
        ledger={w['id']:w for w in base.manifest.get('sales_coverage',[])}
        ledger.update({w['id']:w for w in coverage})
        coverage=sorted(ledger.values(),key=lambda w:(w['start'],list(inc.DOMAINS).index(w['domain'])))
    proof=dict(report_path=str(report_path),report_sha256=inc.file_hash(report_path),
               capture_plan_sha256=report['capture_plan_sha256'],
               material_supply=report['material_supply'],material_revalidation=material_replay,reference_missing=report['reference_missing'],
               independent_components='PRESERVE_EXACT_HISTORICAL_CONTRACTS_NOT_REFRESHED',
               base_manifest_sha256=_hash(base.manifest),base_data_snapshot_id=report['base_snapshot'])
    if incremental_plan:
        proof['incremental_plan']=incremental_plan
    components=deepcopy(base.manifest['components'])
    catalog=deepcopy(base.components)
    reference_version=base.reference_version
    reference_append=report.get('reference_append')
    if reference_append:
        from .sales_reference_release import append_proof
        if reference_append != append_proof(reference_append['previous_reference_path'],
                reference_append['reference_path'],reference_append['master_capture_root']):
            raise FoundationReaderError('Sales Reference append proof mismatch')
        reference_version=Path(reference_append['reference_path']).name
        proof['reference_append']=reference_append
        component=ComponentReference('reference',reference_version,
            source_as_of=reference_append['source_as_of'],
            content_identity=reference_append['reference_path'])
        catalog['reference']=component
        components['reference']=component.as_dict()
    if material_replay and material_replay.get('new_component'):
        components['material_supply']=deepcopy(material_replay['new_component'])
    for domain,tables in TABLES.items():
        stable=dict(contract_version='1.0.0',base_publication=base.foundation_publication_id,
                    base_data_snapshot_id=report['base_snapshot'],reference_version=reference_version,
                    proof_sha256=_hash(proof),coverage_sha256=_hash(coverage),
                    datasets={t:report['datasets'][t] for t in tables})
        fingerprint=_identity(stable)
        component=ComponentReference(domain,domain+'_'+fingerprint[:24],
            source_as_of=max(c['committed_at'] for c in commits if c['domain']==domain),
            row_count=report['datasets'][tables[0]]['row_count'],content_identity=fingerprint)
        catalog[domain]=component
        components[domain]=dict(component.as_dict(),facts_contract=stable)
    identity='foundation_'+_hash(dict(base=base.foundation_publication_id,components=components,proof=proof,coverage=coverage))[:32]
    manifest=deepcopy(base.manifest)
    # The old builder envelope is retained by exact ancestor id, not repurposed.
    for key in ('purchasing_base_publication_id','reference_compatibility',
                'reference_compatibility_adapter','reference_data_snapshot_id'):
        manifest.pop(key,None)
    manifest.update(foundation_publication_id=identity,candidate_kind=KIND,manifest_schema_version='1.0.0',
                    base_foundation_publication_id=base.foundation_publication_id,
                    components=components,facts_base_snapshot_id=report['base_snapshot'],
                    sales_facts_revalidation=proof,sales_coverage=coverage,
                    source_as_of=max([c['committed_at'] for c in commits]+
                        ([reference_append['source_as_of']] if reference_append else [])))
    return FoundationPublication(identity,capture_root.name,previous_foundation_publication_id=base.foundation_publication_id,
        reference_version=reference_version,components=catalog,manifest=manifest,
        source_as_of=manifest['source_as_of'],validation_status='PASS')


def validate_transition(publication, base, base_components):
    """Strict metadata validation, called from canonical manifest validation."""
    def fail(message): raise FoundationReaderError(message)
    m=publication.manifest
    components=m['components']
    if (set(components)!=NAMES or set(base_components)!=NAMES
            or m['base_snapshot_id']!=base.manifest['base_snapshot_id']
            or m['base_foundation_publication_id']!=base.foundation_publication_id
            or publication.previous_foundation_publication_id!=base.foundation_publication_id):
        fail('Sales facts transition base identity/snapshot/reference mismatch')
    proof=m.get('sales_facts_revalidation')
    if (not isinstance(proof,dict) or proof.get('base_manifest_sha256')!=_hash(base.manifest)
            or type(m.get('facts_base_snapshot_id')) is not int
            or m['facts_base_snapshot_id']<m['base_snapshot_id']
            or proof.get('base_data_snapshot_id')!=m['facts_base_snapshot_id']
            or set(proof.get('reference_missing',{}))!={'customers','products','credit_customers','credit_products'}
            or any(proof['reference_missing'].values())):
        fail('Sales facts transition revalidation proof is incomplete')
    reference_append=proof.get('reference_append')
    if reference_append:
        from .sales_reference_release import append_proof
        from .ducklake import DATA_ROOT
        old_path=DATA_ROOT/'reference/_versions'/base.reference_version
        new_path=DATA_ROOT/'reference/_versions'/publication.reference_version
        if (reference_append.get('previous_reference_path')!=str(old_path)
                or reference_append.get('reference_path')!=str(new_path)
                or reference_append!=append_proof(old_path,new_path,reference_append['master_capture_root'])
                or components['reference']!=ComponentReference('reference',publication.reference_version,
                    source_as_of=reference_append['source_as_of'],content_identity=str(new_path)).as_dict()
                or publication.component('reference').source_as_of!=reference_append['source_as_of']):
            fail('Sales transition Reference append binding mismatch')
    elif publication.reference_version!=base.reference_version:
        fail('Sales transition changed Reference without append revalidation')
    replay=proof.get('material_revalidation')
    if proof.get('material_supply',{}).get('unchanged'):
        for d in ('sales','credit_memo'):
            p=proof['material_supply'].get('proofs',{}).get(d,{})
            if not p.get('unchanged') or p.get('before_sha256')!=p.get('after_sha256') or len(p.get('before_sha256',''))!=64:
                fail('Sales facts transition historical dependency changed')
        if components['material_supply']!=base_components['material_supply']:
            fail('Sales facts transition changed an unaffected Material Supply')
    else:
        if (not isinstance(replay,dict) or replay.get('status')!='REPLAY_PASS'
                or not replay.get('old_demand_replay_matches') or not replay.get('old_status_replay_matches')
                or replay.get('before_demand_sha256')!=replay.get('replay_demand_sha256')
                or replay.get('before_status_sha256')!=replay.get('replay_status_sha256')
                or replay.get('refresh_of_stock_production_purchasing') is not False):
            fail('Sales facts transition requires an exact original derivation replay')
        replacement=replay.get('new_component')
        expected=replacement or base_components['material_supply']
        if components['material_supply']!=expected:
            fail('Sales facts transition Material Supply replay binding mismatch')
        if replacement:
            stable=replacement.get('sales_revalidation_contract',{})
            fingerprint=inc.digest(stable)
            replaced=set(replay.get('datasets_replaced',[]))
            if (not replaced or not replaced.issubset({'material_equivalent_demand','material_supply_status'})
                    or stable.get('original_component')!=base_components['material_supply']['publication_id']
                    or replacement.get('publication_id')!='material_supply_'+fingerprint[:24]
                    or replacement.get('content_identity')!=fingerprint
                    or stable.get('datasets')!=replacement.get('datasets')
                    or set(replacement['datasets'])!=set(base_components['material_supply']['datasets'])):
                fail('Sales facts transition versioned Material Supply contract mismatch')
            for name,metadata in base_components['material_supply']['datasets'].items():
                if name not in replaced and replacement['datasets'][name]!=metadata:
                    fail('Sales facts transition changed independent Material Supply dataset')
    from .sales_continuity import windows
    coverage=m.get('sales_coverage')
    expected_windows=windows()
    incremental_plan=proof.get('incremental_plan')
    if incremental_plan:
        from .sales_refresh_cycle import validate_plan
        validate_plan(incremental_plan)
        if (incremental_plan['base']!=base.foundation_publication_id
                or incremental_plan['base_manifest_sha256']!=inc.digest(base.manifest)):
            fail('Incremental transition base binding mismatch')
        from datetime import date
        for domain in TABLES:
            ends = [w['end'] for w in base.manifest.get('sales_coverage', [])
                    if w['domain'] == domain and w.get('complete')]
            if (not ends or max(ends) != incremental_plan['published_end']
                    or date.fromisoformat(incremental_plan['end_exclusive']) < date.fromisoformat(max(ends))):
                fail('Incremental transition coverage regressed or base watermark mismatch')
        if m['facts_base_snapshot_id'] != base.manifest.get('facts_base_snapshot_id', base.manifest.get('reference_data_snapshot_id')):
            fail('Incremental transition changed independent data snapshot')
        # Builders may change publication identity, content and evidence, not
        # inherited business semantics, accreditation or permission metadata.
        mutable = {'foundation_publication_id', 'candidate_kind', 'base_foundation_publication_id',
                   'components', 'sales_facts_revalidation', 'sales_coverage', 'source_as_of',
                   'reference_compatibility', 'reference_compatibility_adapter',
                   'reference_data_snapshot_id', 'purchasing_base_publication_id'}
        if ({k:v for k,v in m.items() if k not in mutable} !=
                {k:v for k,v in base.manifest.items() if k not in mutable}):
            fail('Incremental transition changed inherited business contract or permissions')
        for domain, tables in TABLES.items():
            previous = base_components[domain].get('facts_contract', {}).get('datasets', {})
            for table in tables:
                actual = components[domain].get('facts_contract', {}).get('datasets', {}).get(table, {})
                if table not in previous or actual.get('schema') != previous[table].get('schema'):
                    fail('Incremental transition schema incompatible')
        ledger={w['id']:w for w in base.manifest.get('sales_coverage',[])}
        ledger.update({w['id']:w for w in incremental_plan['windows']})
        expected_windows=sorted(ledger.values(),key=lambda w:(w['start'],list(inc.DOMAINS).index(w['domain'])))
    if not isinstance(coverage,list) or len(coverage)!=len(expected_windows):
        fail('Sales facts transition coverage ledger is incomplete')
    for expected,actual in zip(expected_windows,coverage):
        if (any(actual.get(k)!=v for k,v in expected.items()) or actual.get('complete') is not True
                or any(type(actual.get(k)) is not int or actual[k]<0 for k in ('documents','lines'))
                or len(actual.get('checkpoint_sha256',''))!=64):
            fail('Sales facts transition coverage gap or malformed window')
    for name,entry in base_components.items():
        if name not in ({*TABLES,'material_supply'} | ({'reference'} if reference_append else set())) and (components[name]!=entry or publication.component(name)!=base.component(name)):
            fail('Sales facts transition changed independent sealed component: '+name)
    for domain,tables in TABLES.items():
        entry=components[domain]
        stable=entry.get('facts_contract',{})
        datasets=stable.get('datasets')
        if (stable.get('contract_version')!='1.0.0' or not isinstance(datasets,dict) or set(datasets)!=set(tables)
                or stable.get('base_publication')!=base.foundation_publication_id
                or stable.get('base_data_snapshot_id')!=m['facts_base_snapshot_id']
                or stable.get('reference_version')!=publication.reference_version
                or stable.get('proof_sha256')!=_hash(proof) or stable.get('coverage_sha256')!=_hash(coverage)):
            fail('Sales facts transition dataset/dependency contract mismatch')
        fingerprint=_identity(stable)
        ref=publication.component(domain)
        if (ref is None or ref.publication_id!=domain+'_'+fingerprint[:24]
                or entry.get('publication_id')!=ref.publication_id
                or entry.get('content_identity')!=fingerprint or entry.get('source_as_of')!=ref.source_as_of):
            fail('Sales facts transition component fingerprint mismatch')
        for table,metadata in datasets.items():
            path=Path(metadata.get('path',''))
            schema=metadata.get('schema',[])
            required={'atomic_id','source_system','doc_entry','currency'} | ({'line_num','item_code','quantity'} if table.endswith('_line') else {'doc_date','doc_total','canceled','card_code'})
            columns=[s[0] for s in schema if isinstance(s,list) and len(s)==2 and s[1]=='VARCHAR']
            if (not path.is_absolute() or path.suffix!='.parquet' or inc.DATA_ROOT.resolve() not in path.resolve().parents
                    or type(metadata.get('row_count')) is not int or metadata['row_count']<0
                    or len(metadata.get('sha256',''))!=64 or len(columns)!=len(set(columns))
                    or len(columns)!=len(schema) or not required.issubset(columns)):
                fail('Sales facts transition physical dataset metadata invalid')
    return components


def verify_files(manifest):
    """Physical bytes are immutable and checked before exposing any relation."""
    for domain in TABLES:
        for metadata in manifest['components'][domain]['facts_contract']['datasets'].values():
            path=Path(metadata['path'])
            if path.is_symlink() or inc.file_hash(path)!=metadata['sha256']:
                raise FoundationReaderError('Sales facts transition physical hash mismatch')
    proof=manifest['sales_facts_revalidation']
    report=Path(proof['report_path'])
    if report.is_symlink() or inc.file_hash(report)!=proof['report_sha256']:
        raise FoundationReaderError('Sales facts transition revalidation artifact hash mismatch')
    evidence=inc.read_json(report)
    if (evidence['blockers'] or evidence['material_supply']!=proof['material_supply']
            or evidence['reference_missing']!=proof['reference_missing']
            or evidence.get('material_revalidation')!=proof.get('material_revalidation')
            or evidence.get('reference_append')!=proof.get('reference_append')
            or evidence.get('incremental_plan')!=proof.get('incremental_plan')
            or evidence['capture_plan_sha256']!=proof['capture_plan_sha256']):
        raise FoundationReaderError('Sales facts transition revalidation artifact binding mismatch')
    for metadata in manifest['components']['material_supply'].get('datasets',{}).values():
        # Original sealed files as well as any legitimate replayed versions.
        for path,sha in zip(metadata.get('file_references',[]),metadata.get('file_hashes',[])):
            if Path(path).is_symlink() or inc.file_hash(Path(path))!=sha:
                raise FoundationReaderError('Material Supply transition physical hash mismatch')
    for domain,tables in TABLES.items():
        datasets=manifest['components'][domain]['facts_contract']['datasets']
        if any(datasets[t]!=evidence['datasets'][t] for t in tables):
            raise FoundationReaderError('Sales facts transition report/dataset mismatch')


def relation(manifest,component,table):
    if component not in TABLES or table not in TABLES[component]:
        raise FoundationReaderError('Sales facts transition invalid relation')
    path=manifest['components'][component]['facts_contract']['datasets'][table]['path']
    return "(SELECT * FROM read_parquet('"+path.replace("'","''")+"'))"
