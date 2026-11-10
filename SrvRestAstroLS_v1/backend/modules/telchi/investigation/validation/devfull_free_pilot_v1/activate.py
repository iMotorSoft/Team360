"""Owner-authorized devfull pilot: publish private SourcePolicy JSON, never services.

Canonical consumers: lifecycle.load_config -> research_port.build_researcher.
Rollback restores the exact control bytes only if the installed bytes still match.
"""
import argparse
import asyncio
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from modules.telchi.assistant import whatsapp_dev as dev, whatsapp_dev_lifecycle as lifecycle
from modules.telchi.assistant.whatsapp_dev_quick import operation_lock
from modules.telchi.console_http import AccreditedReader
from modules.telchi.exploratory_sql.authorized_foundation import ResearchBinding, SourcePolicy, discover
from modules.telchi.investigation.validation.presidencia_sourcepolicy_final_v1.validate import audit_permissions
from .prepare import MATRIX, ORG, WORKSPACE, write_new


def digest(data):
    return hashlib.sha256(data).hexdigest()


def restore_bytes(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.pilot-rollback-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def isolated(audit, anchors):
    local = [u for u in audit['users'] if u['organization'] == ORG and u['workspace'] == WORKSPACE]
    holders = [u for u in local if u['researcher_anchors']]
    if not (len(holders) == 1 and holders[0]['email'] == 'devfull@telchiai.com'
            and set(holders[0]['researcher_anchors']) == anchors
            and any(w['id'] == WORKSPACE and w['slug'] == 'telchi_dev'
                    for w in audit['telchi_workspaces'])):
        raise ValueError('devfull_isolation_required')
    return holders[0]['id']


def require_storage_privileges(privileges):
    if not all(privileges.get(name) is True for name in ('select', 'insert', 'update')):
        raise PermissionError('canonical_runtime_core_events_select_insert_update_required')


async def check_runtime_storage():
    import psycopg
    from psycopg.rows import dict_row
    from modules.db.settings import get_database_settings
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn,
            row_factory=dict_row, connect_timeout=5,
            options='-c default_transaction_read_only=on -c statement_timeout=5000') as conn:
        privileges = await (await conn.execute("""SELECT
            has_table_privilege(current_user,'public.core_events','SELECT') AS "select",
            (SELECT bool_and(has_column_privilege(
                current_user, 'public.core_events', column_name, 'INSERT'))
             FROM unnest(ARRAY['id', 'workspace_id', 'actor_user_id', 'event_name',
                 'entity_type', 'correlation_id', 'payload_jsonb']) AS column_name) AS "insert",
            has_column_privilege(current_user,'public.core_events','payload_jsonb','UPDATE') AS "update"
            """)).fetchone()
        require_storage_privileges(privileges)


def activate(candidate):
    control = dev.PRIVATE_ROOT / 'whatsapp-dev-control.json'
    original = control.read_bytes()
    config = lifecycle.load_config(control)
    # Do not publish a rollout whose canonical audit/recovery repository cannot write.
    asyncio.run(check_runtime_storage())
    bundle = lifecycle.read_json(candidate)
    rows = list(csv.DictReader(MATRIX.open()))
    policies = [asdict(SourcePolicy(r['dataset'], r['existing_permission'], ORG, WORKSPACE, None, True))
                for r in rows]
    anchors = {p['permission'] for p in policies}
    assert len(policies) == len({p['source'] for p in policies}) == 70 and len(anchors) == 12
    assert bundle['state'] == 'READY_NOT_ACTIVE'
    assert bundle['policies'] == policies
    assert (bundle['organization'], bundle['workspace']) == (ORG, WORKSPACE)
    audit = asyncio.run(audit_permissions(anchors))
    user = isolated(audit, anchors)
    assert user == bundle['user_id']
    approval = dev.read_approval(Path(config['approval']))
    assert approval['user_id'] == user
    reader = AccreditedReader(bundle['foundation_publication_id'])
    # Bind through the exact runtime SourcePolicy mechanism, not ad-hoc file paths.
    from modules.telchi.exploratory_sql.authorized_foundation import EffectiveScope
    scope = EffectiveScope(user, ORG, WORKSPACE, frozenset(anchors))
    with reader.connector.session(read_only=True) as db:
        db.execute('SET threads=2')
        db.execute("SET memory_limit='512MB'")
        access = reader.resolve_on(db)
        sources, gaps = discover(db, access, allowed_sources=frozenset(p['source'] for p in policies))
        assert not gaps and len(sources) == 70
        binding = ResearchBinding(resolve_scope=lambda: scope, scope=scope,
            publication=access.foundation_publication_id, snapshot=access.ducklake_snapshot_id,
            sources=sources, policies=tuple(SourcePolicy(**p) for p in policies),
            investigation_id='devfull-policy-preactivation')
        try:
            assert len(binding.projections) == 70
            publication = access.foundation_publication_id
        finally:
            binding.close()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = dev.PRIVATE_ROOT / ('sourcepolicy-dev-activation-' + stamp)
    backup.mkdir(mode=0o700)
    evidence = backup / 'evidence'
    evidence.mkdir(mode=0o700)
    console = backup / 'console-config.json'
    runtime = dict(purpose='DEVFULL_FREE_PILOT_NOT_PRESIDENCIA', organization=ORG,
                   workspace=WORKSPACE, foundation_publication_id=publication,
                   evidence_directory=str(evidence), policies=policies)
    write_new(console, runtime)
    # Backup actual canonical artifacts, including the actual approval's gate path.
    for label, path in [('control', control), ('approval', Path(config['approval'])),
                        ('gates', Path(approval['gates_file'])), ('candidate', candidate)]:
        data = path.read_bytes()
        target = backup / (label + '.backup')
        with open(target, 'xb', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
            stream.write(data)
        assert target.read_bytes() == data
    config['env'].update(TEAM360_TELCHI_FREE_ANALYSIS='1', TEAM360_TELCHI_CONSOLE_CONFIG=str(console))
    record = dict(control=str(control), original_sha256=digest(original), console=str(console),
                  console_sha256=digest(console.read_bytes()), user_id=user,
                  organization=ORG, workspace=WORKSPACE, foundation_publication_id=publication,
                  policy_count=70, matrix_sha256=digest(MATRIX.read_bytes()),
                  permission_audit=audit, services_restarted=0, whatsapp_messages=0)
    assert control.read_bytes() == original, 'concurrent_control_change'
    installed = None
    try:
        lifecycle.atomic(control, config)
        installed = control.read_bytes()
        record['installed_sha256'] = digest(installed)
        # Exercise canonical environment sanitization and actual researcher composition.
        lifecycle.load_config(control)
        from modules.telchi.console_http import load_config
        from modules.telchi.research_port import build_researcher
        researcher = build_researcher(pool=lambda: None, config=load_config())
        assert researcher is not None and researcher.recovery_repository is not None
        assert len(researcher.policies) == 70
        write_new(backup / 'receipt.json', record)
    except BaseException:
        # Only our publication may be rolled back; never overwrite a later writer.
        if installed is not None and control.read_bytes() == installed:
            restore_bytes(control, original)
        raise
    return backup / 'receipt.json'


def rollback(receipt):
    record = lifecycle.read_json(receipt)
    control = Path(record['control'])
    assert control == dev.PRIVATE_ROOT / 'whatsapp-dev-control.json'
    original = (receipt.parent / 'control.backup').read_bytes()
    assert digest(original) == record['original_sha256']
    assert digest(control.read_bytes()) == record['installed_sha256'], 'later_configuration_preserved'
    restore_bytes(control, original)
    assert control.read_bytes() == original
    # Published bundle and evidence remain private/inert for audit, never deleted.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--candidate', type=Path)
    group.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    with operation_lock():
        if args.rollback:
            rollback(args.rollback)
            print('SOURCE_POLICY_DEV=ROLLED_BACK')
        else:
            print('ACTIVATION_RECEIPT=' + str(activate(args.candidate)))


if __name__ == '__main__':
    main()
