"""Reaccredit DEV after real ranking probes; never starts runtime or modifies gate policy."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def run(args):
    config = l.load_config(d.PRIVATE_ROOT / 'whatsapp-dev-control.json')
    ap = Path(config.get('approval', d.PRIVATE_ROOT / 'whatsapp-dev-session-approval.json'))
    approval = d.read_approval(ap)
    current = l.read_json(l.root() / 'current.json')
    assert current['state'] == 'STOPPED' and not l.matches(current.get('backend'))
    await asyncio.to_thread(d.preflight, ap, require_gates=False)
    report = l.read_json(d.private_file(args.evidence))
    assert report['status'] == 'PASS' and report['pool_closed'] and report['whatsapp_sent'] == 0
    assert report['source_sha256'] == report['ending_source_sha256'] == d.source_digest()
    assert report['configuration_sha256'] == d.configuration_digest()
    assert report['approval_sha256'] == d.approval_digest(approval)
    assert set(report['observations']) == d.GATES and all(v['status'] == 'PASS' for v in report['observations'].values())
    assert report['unit_price_distinction']['status'] == 'PASS'
    assert report['audited_replay']['exact_state_and_proposal_verified_in_postgres']
    tests = l.read_json(d.private_file(args.validations))
    assert tests['results'] and all(r['exit_code'] == 0 for r in tests['results'])
    assert tests['source_sha256'] == d.source_digest()
    for name, digest in tests['source_hashes'].items():
        assert sha(name) == digest, name
    mp = d.private_file(approval['gates_file'])
    previous = mp.read_bytes()
    old = json.loads(previous)
    assert old['schema_version'] == 2 and old['validity_policy'] == d.DEV_GATE_POLICY
    # Validate provenance before archiving; no freshness inferred from updated hashes.
    for gate in old['gates'].values():
        assert sha(d.private_file(gate['artifact'])) == gate['sha256']
    out = l.directory(d.PRIVATE_ROOT / ('ranking-gates-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
    l.atomic(out / 'previous-manifest.json', old)
    artifact = out / 'report.json'
    l.atomic(artifact, dict(report, inputs={str(args.evidence.resolve()): sha(args.evidence),
        str(args.validations.resolve()): sha(args.validations)},
        renewal_basis='Owner-approved monetary ranking; all six guarantees re-executed against current source. Real authenticated persisted HTTP/dispatcher/PG/Luna/Foundation, current durable claim/cache and rolled-back intent checks; no delivery.'))
    manifest = dict(schema_version=2, validity_policy=d.DEV_GATE_POLICY, environment='dev',
        workspace_id=approval['workspace_id'], user_id=approval['user_id'], instance='team360-meta-dev',
        issued_at=datetime.now(timezone.utc).isoformat(), source_sha256=d.source_digest(),
        configuration_sha256=d.configuration_digest(), approval_sha256=d.approval_digest(approval),
        previous_manifest=dict(artifact=str(out / 'previous-manifest.json'), sha256=sha(out / 'previous-manifest.json')),
        renewal_basis='Monetary product ranking V1; actual current-code probes, no expiry/policy change.',
        gates={name: dict(status='PASS', kind='real', artifact=str(artifact), sha256=sha(artifact), observations=[name]) for name in d.GATES})
    assert mp.read_bytes() == previous, 'Concurrent gate publication'
    l.atomic(mp, manifest)
    try:
        d.gate_evidence(approval)
        await asyncio.to_thread(d.preflight, ap)
    except BaseException:
        l.atomic(mp, old)
        raise
    return dict(SIX_GATES='VALID', runtime='STOPPED', READY_FOR_MANUAL_WHATSAPP='YES',
        artifact=str(artifact), artifact_sha256=sha(artifact), manifest_sha256=sha(mp),
        whatsapp_sent=0, services_started_or_stopped=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evidence', 'validations', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('new output required')
    result = asyncio.run(run(args))
    l.atomic(args.output, result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
