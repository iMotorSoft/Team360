"""Resume exact operational successor using canonical publisher; no SAP reads."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from modules.telchi.datalake import sales_incremental as durable
from modules.telchi.datalake.ducklake import DuckLakeConnector, DATA_ROOT
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.operational_overlap import make_candidate
from modules.telchi.datalake.sales_foundation_promotion import real_promotion
from modules.telchi.runtime.resource_guard import ResourceGuard

ROOT=Path(__file__).resolve().parent
EXPECTED='foundation_163c54dbb6060f534b0a76f38272326e'
DEST=DATA_ROOT/'staging/october-finalize-20261104-v1/operational'
JOURNAL=ROOT/'operational-promotion-journal'

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--promote',action='store_true'); args=parser.parse_args()
    # CPython 3.12.3's dump_traceback_later watchdog can SIGSEGV while
    # walking JSON encoder frames (isolated GDB reproduction retained).
    # Progress is emitted synchronously at phase boundaries instead.
    ResourceGuard().preflight()
    connector=DuckLakeConnector(); store=FoundationPublicationStore(connector.session)
    base=store.get(EXPECTED)
    current=store.current_pointer()
    path=DEST/'foundation-candidate.json'
    if not path.exists():
        if current != EXPECTED: raise RuntimeError('CURRENT_CHANGED:'+str(current))
        DEST.parent.mkdir(parents=True,exist_ok=True)
        evidence=DEST.parent/'movement-evidence.json'
        if not evidence.exists(): durable.seal(evidence,durable.read_json(ROOT/'resume-progress.json'))
        recovery=DATA_ROOT/'raw/sap/full-data-lake-refresh-capture-v1/october-resume-20261104-v1'
        candidate=make_candidate(base,recovery,DEST,domains=['movements','production'],
            movement_evidence=dict(path=str(evidence),sha256=durable.file_hash(evidence)))
        print(json.dumps({'candidate':candidate.foundation_publication_id,'coverage':candidate.manifest['operational_observations']['overlap']['coverage']}),flush=True)
    print(json.dumps({'phase':'canonical_prepare_or_resume','candidate_path':str(path)}),flush=True)
    promotion=real_promotion(JOURNAL)
    if not (JOURNAL/'plan.json').exists():
        plan=promotion.prepare(path)
        print(json.dumps({'prepared':plan['candidate']}),flush=True)
    if args.promote:
        result=promotion.promote()
        live=store.current_publication()
        for name in ('sales','credit_memo','receivables_collections'):
            assert live.manifest['components'][name] == base.manifest['components'][name]
            assert live.component(name) == base.component(name)
        result.update(observed_at=datetime.now(timezone.utc).isoformat(),SALES_UNCHANGED='YES',CXC_UNCHANGED='YES',
            coverage=live.manifest['operational_observations']['overlap']['coverage'])
        durable.seal(ROOT/'finalize-operational-publication.json',result)
        print(json.dumps(result,default=str),flush=True)

if __name__=='__main__': main()
