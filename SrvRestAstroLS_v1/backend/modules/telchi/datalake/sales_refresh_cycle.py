"""Bounded future-cycle adapter over the existing durable sales capture engine.

Business-date overlap plus explicitly accredited late-change dates, not CDC.
No scheduler and no implicit SAP access. Call capture only in a separately
source-authorized cycle; today's release uses already frozen checkpoints.
"""
from datetime import date, timedelta
from pathlib import Path
from decimal import Decimal

from . import sales_incremental as inc

CONTRACT = 'sales-refresh-cycle-v1'
MAX_DAYS = 31


def window_set(start, end, overlap_days, late_dates):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if not 1 <= overlap_days <= 14 or not start <= end or (end-start).days > MAX_DAYS:
        raise ValueError('UNBOUNDED_INCREMENTAL_SCOPE')
    days = {start-timedelta(days=i) for i in range(1, overlap_days+1)}
    days.update(start+timedelta(days=i) for i in range((end-start).days))
    days.update(date.fromisoformat(d) for d in late_dates)
    if len(days) > MAX_DAYS or any(d >= end for d in days):
        raise ValueError('INCREMENTAL_WINDOW_BUDGET')
    return [dict(id=f'{day}_{domain}',domain=domain,start=str(day),end=str(day+timedelta(days=1)),
                 mode='INCREMENTAL_COMPLETE_DOCUMENT_RECONCILIATION')
            for day in sorted(days) for domain in inc.DOMAINS]


def make_plan(*, base, published_end, end_exclusive, authorization_reference,
              overlap_days=7, late_dates=(), late_change_evidence=None):
    from . import sales_continuity as cap
    if not authorization_reference or (late_dates and not late_change_evidence):
        raise ValueError('SOURCE_SCOPE_AUTHORIZATION_AND_LATE_CHANGE_EVIDENCE_REQUIRED')
    if not base.manifest.get('sales_coverage'):
        raise ValueError('ACCREDITED_PUBLISHED_COVERAGE_REQUIRED')
    for domain in inc.DOMAINS:
        ends = [w['end'] for w in base.manifest['sales_coverage'] if w['domain']==domain and w.get('complete')]
        if not ends or max(ends) != published_end:
            raise ValueError('PUBLISHED_WATERMARK_MISMATCH')
    return dict(contract=CONTRACT, created_at=inc.now(), budget=cap.BUDGET, limits=__import__('dataclasses').asdict(cap.LIMITS),
        source='SAP_B1_HANA/TELCHI', base=base.foundation_publication_id,
        base_manifest_sha256=inc.digest(base.manifest), published_end=published_end,
        end_exclusive=end_exclusive, overlap_days=overlap_days, late_dates=sorted(set(late_dates)),
        late_change_evidence=late_change_evidence, authorization=authorization_reference,
        windows=window_set(published_end,end_exclusive,overlap_days,late_dates),
        publication='NOT_AUTHORIZED', global_change_watermark=None,
        strategy='BOUNDED_BUSINESS_DATE_OVERLAP_WITH_EXPLICIT_LATE_WINDOWS_NOT_CDC',
        limitations='Changes outside overlap require accredited explicit late_dates; no global change completeness claimed')


def validate_plan(plan):
    from . import sales_continuity as cap
    from dataclasses import asdict
    if (plan.get('contract')!=CONTRACT or plan.get('budget')!=cap.BUDGET or plan.get('limits')!=asdict(cap.LIMITS)
            or plan.get('source')!='SAP_B1_HANA/TELCHI' or not plan.get('authorization')
            or not plan.get('base') or len(plan.get('base_manifest_sha256',''))!=64
            or plan.get('global_change_watermark') is not None or plan.get('publication')!='NOT_AUTHORIZED'
            or (plan.get('late_dates') and not plan.get('late_change_evidence'))
            or plan.get('windows')!=window_set(plan['published_end'],plan['end_exclusive'],plan['overlap_days'],plan['late_dates'])):
        raise ValueError('UNACCREDITED_INCREMENTAL_PLAN')


def capture(root, plan, source, **kwargs):
    """Explicit source injection; uses original budgets, checkpoints and recovery."""
    from . import sales_continuity as cap
    from . import sales_controlled_block as block
    validate_plan(plan)
    root=Path(root).resolve()
    allowed=(inc.DATA_ROOT/'raw/sap'/CONTRACT).resolve()
    if root.parent!=allowed:
        raise ValueError('INCREMENTAL_CAPTURE_ROOT_OUTSIDE_CONTRACT')
    # Same global extraction flock as the existing controlled capture CLI.
    shared=inc.DATA_ROOT/'raw/sap'/block.CONTRACT
    shared.mkdir(parents=True,exist_ok=True)
    with block.extraction_lock(shared):
        return cap.run(root,plan,source,**kwargs)


def prepare_candidate(root, destination):
    """Offline whole-document upsert, cancellation reconciliation and gate."""
    from .sales_continuity_candidate import build
    from .sales_facts_transition import make_candidate
    from .ducklake import DuckLakeConnector
    from .foundation_publication import FoundationPublicationStore
    from .foundation_manifest import validate_manifest
    from contextlib import contextmanager
    root, destination = Path(root), Path(destination)
    plan = inc.read_json(root/'plan.json'); validate_plan(plan)
    report = build(root,destination)
    connector = DuckLakeConnector()
    with connector.session(read_only=True) as con:
        @contextmanager
        def same(): yield con
        store = FoundationPublicationStore(same)
        base = store.current_publication()
        if base.foundation_publication_id != plan['base'] or inc.digest(base.manifest)!=plan['base_manifest_sha256']:
            raise RuntimeError('CURRENT_CHANGED_INCREMENTAL_RECONCILIATION_REQUIRED')
        candidate = make_candidate(base,destination/'reconciliation.json',root)
        validate_manifest(store,candidate)
        inc.seal(destination/'foundation-candidate.json',candidate.as_row())
    return dict(report=report,candidate=candidate.foundation_publication_id,
                promotion='Use sales_foundation_promotion prepare/promote under the owner instruction for this exact candidate; no separate nominal approval applies')


def verify_cycle_money(connection, report, *, prefix='full_'):
    """Compare complete captured windows to canonical reader relations exactly."""
    from .sales_continuity_candidate import TABLES, sql_literal
    expected={(b['domain'],b['month'],b['currency'],b['cancelled']):
              (b['documents'],Decimal(b['doc_total'])) for b in report['raw_money']}
    actual={}
    for domain,tables in TABLES.items():
        scope=' OR '.join('(doc_date>='+sql_literal(w['start'])+' AND doc_date<'+sql_literal(w['end'])+')'
                          for w in report['coverage'] if w['domain']==domain)
        if not scope: raise ValueError('MISSING_CYCLE_COVERAGE')
        rows=connection.execute(f'''SELECT substr(doc_date,1,7),currency,canceled,count(*),
            sum(cast(doc_total AS DECIMAL(38,12))) FROM {prefix}{tables[0]}
            WHERE source_system='SAP_B1_HANA' AND ({scope}) GROUP BY 1,2,3''').fetchall()
        actual.update({(domain,r[0],r[1],r[2]):(r[3],r[4]) for r in rows})
    if expected!=actual:
        raise ValueError('CYCLE_RAW_MONETARY_RECONCILIATION_FAILED')
    return dict(groups=len(actual),zero_tolerance=True)


def record_published_watermark(destination, plan, publication, *, reader_verified):
    """Advance coverage only after a real canonical reader verifies this release.

    The returned artifact is a business coverage checkpoint, never a global
    modification watermark. Live scheduler must resolve CURRENT before using it.
    """
    validate_plan(plan)
    m=publication.manifest
    if (publication.status!='CURRENT' or not reader_verified
            or m.get('base_foundation_publication_id')!=plan['base']
            or m.get('sales_facts_revalidation',{}).get('incremental_plan')!=plan):
        raise RuntimeError('UNPUBLISHED_WATERMARK_ADVANCE_FORBIDDEN')
    result=dict(contract=CONTRACT,foundation=publication.foundation_publication_id,
                business_coverage_end_exclusive=plan['end_exclusive'],global_change_watermark=None,
                plan_sha256=inc.digest(plan),late_change_scope=plan['late_dates'])
    destination=Path(destination)
    if destination.exists():
        if inc.read_json(destination)!=result:
            raise RuntimeError('PUBLISHED_WATERMARK_CONFLICT')
    else:
        inc.seal(destination,result)
    return result
