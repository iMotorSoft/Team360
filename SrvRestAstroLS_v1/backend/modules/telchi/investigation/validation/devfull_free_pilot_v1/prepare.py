"""Read-only DEV pilot accreditation; never publishes runtime configuration.

Run from backend: PYTHONPATH=. uv run python -m modules.telchi.investigation.validation.devfull_free_pilot_v1.prepare
"""
import asyncio
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.exploratory_sql.authorized_foundation import SourcePolicy, discover
from modules.telchi.investigation.validation.presidencia_sourcepolicy_final_v1.validate import audit_permissions

ROOT = Path(__file__).resolve().parents[7]
PRIVATE = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi')
MATRIX = ROOT / 'data/reports/telchi/presidencia-sourcepolicy-v1/matrix.csv'
ORG = '44b9b7ea-1c19-4a9f-a3d5-1f20622d2f99'
WORKSPACE = '3fb026a1-a4ba-44b3-b65b-fab452df7fc9'


def write_new(path, value, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, default=str)
        stream.write('\n')


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = ROOT / 'data/reports/telchi/devfull-free-pilot-v1' / stamp
    output.mkdir(parents=True, exist_ok=False)
    rows = list(csv.DictReader(MATRIX.open()))
    anchors = {r['existing_permission'] for r in rows}
    assert len(rows) == len({r['dataset'] for r in rows}) == 70
    assert len(anchors) == 12
    audit = asyncio.run(audit_permissions(anchors))
    local = [u for u in audit['users'] if u['organization'] == ORG and u['workspace'] == WORKSPACE]
    holders = [u for u in local if u['researcher_anchors']]
    # Any partial holder would gain access: checking only holders of all 12 is insufficient.
    isolated = (len(holders) == 1 and holders[0]['email'] == 'devfull@telchiai.com'
                and set(holders[0]['researcher_anchors']) == anchors
                and any(w['id'] == WORKSPACE and w['slug'] == 'telchi_dev'
                        for w in audit['telchi_workspaces']))
    policies = tuple(SourcePolicy(r['dataset'], r['existing_permission'], ORG,
                                  WORKSPACE, None, True) for r in rows)
    reader = FoundationReader()
    with reader.connector.session(read_only=True) as db:
        db.execute('SET threads=2')
        db.execute("SET memory_limit='512MB'")
        access = reader.resolve_on(db)
        sources, gaps = discover(db, access, allowed_sources=frozenset(r['dataset'] for r in rows))
    names = {s.name for s in sources}
    missing = sorted({r['dataset'] for r in rows} - names)
    ready = isolated and not missing and not gaps
    report = dict(timestamp=stamp, branch='feature/console-backend-core',
        scope_isolation='PASS' if isolated else 'FAIL', source_policy_dev='READY' if ready else 'BLOCKED',
        matrix_sha256=hashlib.sha256(MATRIX.read_bytes()).hexdigest(), permission_audit=audit,
        foundation=dict(publication=access.foundation_publication_id, snapshot=access.ducklake_snapshot_id,
                        coverage=len(names), target=70, missing=missing, gaps=list(gaps)),
        policy_scope=dict(organization=ORG, workspace=WORKSPACE),
        policies_published=0, grants_changed=0, whatsapp_messages=0, services_restarted=0,
        activation_requires_owner_authorization=True)
    if ready:
        private = PRIVATE / ('devfull-free-pilot-' + stamp)
        private.mkdir(mode=0o700)
        # Candidate policy bundle, not a Console config: no accidental service loading.
        bundle = dict(purpose='DEVFULL_FREE_PILOT_NOT_PRESIDENCIA', state='READY_NOT_ACTIVE',
                      organization=ORG, workspace=WORKSPACE, user_id=holders[0]['id'],
                      foundation_publication_id=access.foundation_publication_id,
                      policies=[asdict(p) for p in policies])
        write_new(private / 'policy-candidate.json', bundle)
        report['candidate_directory'] = str(private)
        report['candidate_sha256'] = hashlib.sha256((private / 'policy-candidate.json').read_bytes()).hexdigest()
    write_new(output / 'accreditation.json', report, 0o644)
    print(json.dumps({k: report[k] for k in ('scope_isolation', 'source_policy_dev', 'foundation')}, default=str))
    print('REPORT=' + str(output / 'accreditation.json'))
    if ready:
        print('CANDIDATE=' + str(private / 'policy-candidate.json'))
    return 0 if ready else 1


if __name__ == '__main__':
    raise SystemExit(main())
