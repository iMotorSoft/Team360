"""Publish owner-authorized DEV research gates without touching service lifecycle.

Active operator sessions are preserved. Readiness here authorizes a subsequent
owner restart, not concurrent session admission or external delivery certification.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

from modules.db.settings import get_database_settings
from modules.messaging.domain.messages import InboundMessage
from modules.messaging.repository import MessagingRepository
from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
from modules.telchi.assistant.whatsapp_dev_quick import operation_lock
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.exploratory_sql.foundation import host_read_preflight
from modules.telchi.investigation.validation.presidencia_sourcepolicy_final_v1.validate import audit_permissions
from .activate import digest, isolated, restore_bytes
from .prepare import write_new


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def run(receipt, live_path, validations_path):
    control_path = dev.PRIVATE_ROOT / 'whatsapp-dev-control.json'
    control_bytes = control_path.read_bytes()
    config = lifecycle.load_config(control_path)
    approval_path = Path(config['approval'])
    approval = dev.read_approval(approval_path)
    installed = lifecycle.read_json(receipt)
    assert digest(control_bytes) == installed['installed_sha256']
    live = lifecycle.read_json(dev.private_file(live_path))
    validations = lifecycle.read_json(dev.private_file(validations_path))
    assert live['status'] == 'PASS' and live['pool_closed']
    assert live['whatsapp_messages'] == live['services_restarted'] == live['listeners_created'] == 0
    source, configuration = dev.source_digest(), dev.configuration_digest()
    assert live['source_sha256'] == validations['source_sha256'] == source
    assert live['configuration_sha256'] == validations['configuration_sha256'] == configuration
    assert len(validations['results']) == 2 and all(r['exit_code'] == 0 for r in validations['results'])
    for path, value in validations['source_hashes'].items():
        assert sha(path) == value, path
    assert len(live['turns']) == 2 and all(t['recovery_model_calls'] == t['recovery_sql'] == 0 for t in live['turns'])
    assert live['independent_control']['status'] == 'PASS'
    assert live['turns'][1]['previous_messages'] > 0
    policy = lifecycle.read_json(Path(installed['console']))
    assert sha(installed['console']) == installed['console_sha256']
    anchors = {p['permission'] for p in policy['policies']}
    audit = await audit_permissions(anchors)
    assert isolated(audit, anchors) == approval['user_id'] == installed['user_id']
    assert len(policy['policies']) == 70
    host = host_read_preflight()
    assert host['safe'], 'RESOURCE_BLOCKED'
    with FoundationReader().connector.session(read_only=True) as db:
        db.execute('SET threads=2')
        db.execute("SET memory_limit='512MB'")
        current = FoundationReader().resolve_on(db)
        assert current.foundation_publication_id == installed['foundation_publication_id']
        assert all(t['publication'] == current.foundation_publication_id and
                   str(t['snapshot']) == str(current.ducklake_snapshot_id) for t in live['turns'])
    srv, settings = dev.configuration()
    binding = await dev.check_database(approval, settings, srv.evolution)
    # Isolated storage namespace, never an operational inbox or pending send.
    isolated_binding = replace(binding, receiver_context='devfull-gate:' + uuid4().hex)
    message = InboundMessage(provider='evolution', channel='whatsapp',
        external_message_id='devfull-gate-' + uuid4().hex, sender=settings.authorized_sender,
        recipients=(isolated_binding.receiver_context,), text_body='DEV local idempotency accreditation',
        external_thread_id=None, subject=None, received_at=datetime.now(timezone.utc),
        metadata={'provider_instance': binding.provider_instance, 'local_gate_probe': True})
    raw = lifecycle.read_json(live_path.parent / 'turn-1.json')
    repo = MessagingRepository()
    async with AsyncConnectionPool(get_database_settings().dsn, min_size=1, max_size=2,
            open=False, kwargs={'connect_timeout': 5, 'row_factory': dict_row}) as pool:
        await pool.wait(timeout=10)
        async with pool.connection() as conn:
            async with conn.transaction():
                claimed = await repo.claim(conn, isolated_binding, message, {})
                assert claimed
                result = SimpleNamespace(text=raw['business_answer'], classification='RESEARCH_AVAILABLE',
                                         correlation_id=claimed['id'])
                await repo.complete_dispatch(conn, isolated_binding, claimed, result)
        for _ in range(2):
            async with pool.connection() as conn:
                async with conn.transaction():
                    assert await MessagingRepository().claim(conn, isolated_binding, message, {}) is None
                    row = await (await conn.execute('SELECT payload_jsonb FROM message_events WHERE id=%s',
                                                     (claimed['id'],))).fetchone()
                    assert row['payload_jsonb']['dispatch_result']['text'] == result.text
        async with pool.connection() as conn:
            async with conn.transaction(force_rollback=True):
                one = await repo.intent(conn, isolated_binding, claimed, message, result.text, {})
                two = await repo.intent(conn, isolated_binding, claimed, message, result.text, {})
                assert one == two
        async with pool.connection() as conn:
            async with conn.transaction():
                assert await repo.recoverable_intent(conn, isolated_binding, message) is None
                assert (await (await conn.execute("SELECT count(*) AS n FROM pg_namespace WHERE nspname LIKE 'research_recovery_%' OR nspname LIKE 'durable_inbox_%'")).fetchone())['n'] == 0
    observations = {name: live['observations'][name] for name in dev.GATES if name != 'durable_idempotency'}
    observations['durable_idempotency'] = dict(status='PASS', actual_runtime_postgres=True,
        committed_isolated_claim=True, duplicate_claims=2, persisted_result_identical=True,
        unique_outbound_intent_rolled_back=True, no_outbound_left=True,
        live_research_reuse=live['observations']['durable_result_reuse'],
        interruption_contracts=dict(artifact=validations['results'][1]['artifact'],
            real_postgres=True, synthetic_luna_data_transport=True,
            limit='Controlled interruption and reconstruction, not OS SIGKILL or external WhatsApp.'))
    out = receipt.parent / ('gates-' + uuid4().hex)
    out.mkdir(mode=0o700)
    artifact = out / 'report.json'
    write_new(artifact, dict(status='PASS', source_sha256=source, configuration_sha256=configuration,
        approval_sha256=dev.approval_digest(approval), observations=observations,
        inputs={str(live_path): sha(live_path), str(validations_path): sha(validations_path)},
        supplemental_source_hashes=validations['source_hashes'], permission_audit=audit,
        host=host, services_restarted=0, whatsapp_sent=0, pool_closed=True,
        limit='DEV restart readiness only. No external delivery or full-month completeness certification.'))
    mp = dev.private_file(approval['gates_file'])
    previous = mp.read_bytes()
    # Exact backup, not a reserialized approximation.
    with open(out / 'previous-manifest.backup', 'xb', opener=lambda p, f: __import__('os').open(p, f, 0o600)) as stream:
        stream.write(previous)
    manifest = dict(schema_version=2, validity_policy=dev.DEV_GATE_POLICY, environment='dev',
        workspace_id=approval['workspace_id'], user_id=approval['user_id'], instance='team360-meta-dev',
        issued_at=datetime.now(timezone.utc).isoformat(), source_sha256=source,
        configuration_sha256=configuration, approval_sha256=dev.approval_digest(approval),
        previous_manifest=dict(artifact=str(out / 'previous-manifest.backup'), sha256=digest(previous)),
        renewal_basis='Explicit owner-authorized DEVFULL final activation; current live Luna/Foundation and runtime PG replay/intent checks. Existing operator session untouched.',
        gates={name: dict(status='PASS', kind='real', artifact=str(artifact), sha256=sha(artifact),
                         observations=[name]) for name in dev.GATES})
    assert mp.read_bytes() == previous and control_path.read_bytes() == control_bytes
    assert source == dev.source_digest() and configuration == dev.configuration_digest()
    installed_manifest = None
    try:
        lifecycle.atomic(mp, manifest)
        installed_manifest = mp.read_bytes()
        dev.gate_evidence(approval)
        dev.unchanged_approval(approval_path, approval)
    except BaseException:
        if installed_manifest is not None and mp.read_bytes() == installed_manifest:
            restore_bytes(mp, previous)
        raise
    result = dict(SIX_GATES='PASS', SOURCE_POLICY_DEV='ACTIVE', FREE_SQL_INVESTIGATION='PASS',
        DURABLE_RESEARCH='PASS', READY_FOR_WHATSAPP_RESTART='YES', BLOCKER='NONE',
        scope='DEV only; owner restart is next, no admission of parallel session',
        artifact=str(artifact), manifest_sha256=sha(mp), backup=str(out),
        current_operator_state=lifecycle.read_json(lifecycle.root() / 'current.json')['state'],
        source_sha256=source, configuration_sha256=configuration,
        services_restarted=0, whatsapp_messages=0)
    write_new(out / 'receipt.json', result)
    print(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('receipt', 'live', 'validations'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    with operation_lock():
        asyncio.run(run(args.receipt, args.live, args.validations))


if __name__ == '__main__':
    main()
