"""B3 schema-only diagnostic via canonical READ_ONLY FoundationReader."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import time

from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.exploratory_sql.authorized_foundation import discover
from modules.telchi.exploratory_sql.foundation import host_read_preflight
from modules.telchi.exploratory_sql.foundation_dev import DevExecutor


def main():
    start=time.monotonic()
    report={'started_at':datetime.now(timezone.utc).isoformat(), 'preflight':host_read_preflight(),
            'scope':'Owner-authorized DEV schema diagnostic, NOT authenticated business research',
            'queries':[], 'threads':1, 'population_scans':0}
    swap=DevExecutor.swap_bytes()
    if report['preflight']['available_bytes']<2*1024**3:
        raise RuntimeError('dev_memory_pressure')
    reader=FoundationReader()
    with reader.connector.session(read_only=True) as db:
        for sql in ["SET threads=1", "SET memory_limit='256MB'", "SET max_temp_directory_size='0B'",
                    "SELECT readonly FROM duckdb_databases() WHERE database_name='telchi'"]:
            rows=db.execute(sql).fetchall()
            report['queries'].append({'sql':sql,'rows':rows})
        if rows != [(True,)]: raise RuntimeError('foundation_not_readonly')
        access=reader.resolve_on(db)
        report['publication']=access.as_dict()
        # Components describe publication, not effective authorization.
        report['manifest']=access.manifest
        sources,gaps=discover(db,access)
        report['sources']=[{'name':s.name,'columns':[asdict(c) for c in s.columns],
                            'limitations':s.limitations} for s in sources]
        report['reader_contract_gaps']=gaps
        report['source_authorization']='NOT_ACCREDITED: no approved SourcePolicy composition or real user session'
        report['relationships']='NONE in issued dynamic catalog; metadata schemas alone do not accredit relationships'
        report['queries'].append({'operation':'discover','sql_pattern':'DESCRIBE SELECT * FROM <FoundationReader pinned relation>',
                                  'source_names':[s.name for s in sources]})
    report['elapsed_seconds']=round(time.monotonic()-start,3)
    report['max_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['swap_growth_bytes']=DevExecutor.swap_bytes()-swap
    report['postflight']=host_read_preflight()
    # Manifest can contain private paths, never credentials; retain only approved
    # schema/coverage metadata in repository evidence.
    def redact(value):
        if isinstance(value,dict): return {k:redact(v) for k,v in value.items() if not any(s in k.lower() for s in ('path','dsn','password','credential','token'))}
        if isinstance(value,(list,tuple)): return [redact(v) for v in value]
        if isinstance(value,str) and ('/media/' in value or 'postgres:' in value): return '<private-reference-redacted>'
        return value
    target=Path('../../data/reports/telchi/authorized-research-b3-v1/foundation.json')
    with target.open('x') as f: json.dump(redact(report),f,indent=2,default=str)
    print(json.dumps({'publication':access.foundation_publication_id,'snapshot':access.ducklake_snapshot_id,
        'sources':[(s.name,len(s.columns)) for s in sources],'gaps':gaps,
        'elapsed_seconds':report['elapsed_seconds'],'max_rss_kib':report['max_rss_kib']},indent=2))

if __name__=='__main__': main()
