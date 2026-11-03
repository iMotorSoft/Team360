"""Publish only the verified category DEV change-based evidence; no service writes."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
from modules.telchi.provisioning.tests.live_category_registration import sha


async def run(args):
    config = l.load_config(d.PRIVATE_ROOT/'whatsapp-dev-control.json')
    ap = Path(config.get('approval', d.PRIVATE_ROOT/'whatsapp-dev-session-approval.json'))
    approval = d.read_approval(ap)
    assert l.read_json(l.root()/'current.json')['state'] == 'STOPPED'
    await asyncio.to_thread(d.preflight, ap, require_gates=False)
    report = json.loads(args.evidence.read_text())
    assert report['status'] == 'PASS' and report['pool_closed']
    assert report['source_sha256'] == d.source_digest()
    assert report['configuration_sha256'] == d.configuration_digest()
    assert report['approval_sha256'] == d.approval_digest(approval)
    assert set(report['observations']) == d.GATES
    assert all(o['status'] == 'PASS' for o in report['observations'].values())
    tests = json.loads(args.validations.read_text())
    assert all(r['exit_code'] == 0 for r in tests['results'])
    for name, digest in tests['source_hashes'].items():
        assert sha(name) == digest, name
    mp = d.private_file(approval['gates_file'])
    previous = mp.read_bytes()
    old = json.loads(previous)
    assert old['schema_version'] == 2 and old['validity_policy'] == d.DEV_GATE_POLICY
    # The retained durable gate must still be exactly the audited prior evidence.
    retained = report['observations']['durable_idempotency']['previous_real_evidence']
    assert retained == old['gates']['durable_idempotency']
    assert sha(d.private_file(retained['artifact'])) == retained['sha256']
    out = l.directory(d.PRIVATE_ROOT/('category-gates-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
    l.atomic(out/'previous-manifest.json', old)
    artifact = out/'report.json'
    l.atomic(artifact, dict(report, inputs={str(args.evidence.resolve()):sha(args.evidence),
        str(args.validations.resolve()):sha(args.validations)},
        renewal_basis='Owner-approved category registry increment; real DEV authorization, HTTP conversation, result/cache and no-fallback checks. Unchanged durable fence retains dated evidence.'))
    manifest = dict(schema_version=2, validity_policy=d.DEV_GATE_POLICY, environment='dev',
        workspace_id=approval['workspace_id'], user_id=approval['user_id'], instance='team360-meta-dev',
        issued_at=datetime.now(timezone.utc).isoformat(), source_sha256=d.source_digest(),
        configuration_sha256=d.configuration_digest(), approval_sha256=d.approval_digest(approval),
        previous_manifest=dict(artifact=str(out/'previous-manifest.json'),sha256=sha(out/'previous-manifest.json')),
        renewal_basis='Category DEV scoped activation; no expiry timer or security-policy change.',
        gates={name:dict(status='PASS',kind='real',artifact=str(artifact),sha256=sha(artifact),observations=[name])
               for name in d.GATES})
    assert mp.read_bytes() == previous, 'Gate manifest changed concurrently'
    l.atomic(mp, manifest)
    try:
        d.gate_evidence(approval)
        await asyncio.to_thread(d.preflight, ap)
    except BaseException:
        l.atomic(mp, old)
        raise
    return dict(SIX_GATES='VALID', READY_FOR_MANUAL_WHATSAPP='YES', evidence=str(artifact),
        evidence_sha256=sha(artifact), manifest_sha256=sha(mp), policy=d.DEV_GATE_POLICY,
        runtime='STOPPED', whatsapp_sent=0, services_started_or_stopped=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evidence','validations','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite evidence')
    result = asyncio.run(run(args))
    with args.output.open('x') as f:
        json.dump(result,f,indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
