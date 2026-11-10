"""Read-only final audit. Run from backend with PYTHONPATH=. uv run python <path>."""
import asyncio
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from modules.console.repositories import PermissionConsoleRepository
from modules.db.settings import get_database_settings
from modules.telchi.exploratory_sql.console_repository import ResearchConsoleRepository
from modules.telchi.exploratory_sql.authorized_foundation import discover
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.datalake.commercial_purpose_reader import DATASETS

ROOT = Path(__file__).resolve().parents[7]
OUTPUT = ROOT / 'data/reports/telchi/presidencia-sourcepolicy-final-v1/validation.json'
MATRIX = ROOT / 'data/reports/telchi/presidencia-sourcepolicy-v1/matrix.csv'


async def audit_permissions(anchors):
    repo, research = PermissionConsoleRepository(), ResearchConsoleRepository()
    async with await psycopg.AsyncConnection.connect(
        get_database_settings().dsn, row_factory=dict_row, connect_timeout=5,
        options='-c default_transaction_read_only=on -c statement_timeout=10000',
        application_name='presidencia-sourcepolicy-final-readonly',
    ) as conn:
        await conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        preflight = await (await conn.execute(
            'SELECT current_database() AS database, current_setting(\'transaction_read_only\') AS read_only'
        )).fetchone()
        users = await (await conn.execute('''SELECT u.id::text, u.email, u.status,
            w.id::text workspace, w.slug, w.organization_id::text organization
            FROM core_users u JOIN core_workspaces w ON w.id=u.workspace_id ORDER BY u.id''')).fetchall()
        workspaces = await (await conn.execute('''SELECT w.id::text,w.slug,w.status,
            w.organization_id::text,(SELECT count(*) FROM core_users u WHERE u.workspace_id=w.id) AS users
            FROM core_workspaces w JOIN core_organizations o ON o.id=w.organization_id
            WHERE o.organization_code='telchi' ORDER BY w.slug''')).fetchall()
        holders = {p: [] for p in sorted(anchors)}
        scoped_users = []
        for user in users:
            effective = set(await repo.list_effective_permissions(conn, user['workspace'], user['id']))
            enabled = await research.enabled_permissions(conn, user['workspace'])
            identity = await research.identity(conn, user['id'])
            selected = sorted(effective & anchors)
            if selected or user['slug'] == 'telchi_dev':
                roles = await (await conn.execute('''SELECT r.role_code,r.status,r.workspace_id::text
                    FROM core_user_roles ur JOIN core_roles r ON r.id=ur.role_id
                    WHERE ur.user_id=%s ORDER BY r.role_code''', (user['id'],))).fetchall()
                full = await (await conn.execute('''SELECT organization_id::text,workspace_id::text,module,
                    revoked_at_utc IS NULL AS active FROM core_module_full_access_grants WHERE user_id=%s''',
                    (user['id'],))).fetchall()
                scoped_users.append(dict(user, roles=roles, module_grants=full,
                    effective_anchors=selected, identity_accepted=identity is not None,
                    researcher_anchors=sorted(effective & enabled & anchors) if identity else []))
            for p in selected:
                holders[p].append(dict(user_id=user['id'], email=user['email'],
                    workspace=user['workspace'], organization=user['organization'],
                    enabled=p in enabled, identity_accepted=identity is not None))
        # Include roles/profiles with no members: future assignments would share this contract too.
        role_anchors = await (await conn.execute('''SELECT r.role_code,r.workspace_id::text,r.status,p.permission_code,
            (SELECT count(*) FROM core_user_roles ur WHERE ur.role_id=r.id) AS assigned_users
            FROM core_roles r JOIN core_role_permissions rp ON rp.role_id=r.id
            JOIN core_permissions p ON p.id=rp.permission_id WHERE p.permission_code=ANY(%s)
            ORDER BY r.role_code,p.permission_code''', (sorted(anchors),))).fetchall()
        profile_anchors = await (await conn.execute('''SELECT pr.profile_code,pr.workspace_id::text,pr.status,p.permission_code,
            (SELECT count(*) FROM core_user_profiles up WHERE up.profile_id=pr.id) AS assigned_users
            FROM core_permission_profiles pr JOIN core_profile_permissions pp ON pp.profile_id=pr.id
            JOIN core_permissions p ON p.id=pp.permission_id WHERE p.permission_code=ANY(%s)
            ORDER BY pr.profile_code,p.permission_code''', (sorted(anchors),))).fetchall()
        return dict(preflight=preflight, users_with_workspace_examined=len(users),
                    telchi_workspaces=workspaces, users=scoped_users,
                    holders=holders, role_anchors=role_anchors, profile_anchors=profile_anchors)


def audit_current():
    reader = FoundationReader()
    # Connector attaches the catalog READ_ONLY; only five sources are discovered.
    with reader.connector.session(read_only=True) as db:
        db.execute('SET threads=2')
        db.execute("SET memory_limit='512MB'")
        access = reader.resolve_on(db)
        components = access.manifest.get('components', {})
        sources, gaps = discover(db, access, allowed_sources=frozenset(DATASETS))
        available = {s.name: s for s in sources}
        states = {}
        for name in DATASETS:
            declared = name in components.get('commercial_purpose', {}).get('datasets', {})
            state = 'AVAILABLE' if name in available else ('UNVERIFIED' if declared else 'UNAVAILABLE')
            states[name] = dict(state=state, manifest_declared=declared,
                schema_columns=len(available[name].columns) if name in available else None,
                reason='canonical_manifest_and_reader' if name in available else
                    ('declared_but_reader_not_verified' if declared else 'absent_from_current_manifest'))
        return dict(publication=access.foundation_publication_id,
            snapshot=access.ducklake_snapshot_id, commit_snapshot=access.commit_snapshot_id,
            components=sorted(components),
            manifest_sha256=hashlib.sha256(json.dumps(access.manifest, sort_keys=True, default=str).encode()).hexdigest(),
            commercial_purpose_5=states, reader_contract_gaps=list(gaps),
            discovery_scope='ONLY_COMMERCIAL_PURPOSE_FIVE; NO_REINVENTORY_OF_70')


def main():
    rows = list(csv.DictReader(MATRIX.open()))
    anchors = {r['existing_permission'] for r in rows}
    assert len(rows) == 70 and len(anchors) == 12
    report = dict(started_at=datetime.now(timezone.utc).isoformat(),
        matrix_sha256=hashlib.sha256(MATRIX.read_bytes()).hexdigest(),
        permission_audit=asyncio.run(audit_permissions(anchors)), foundation=audit_current(),
        writes_to_operational_state=0, identities_modified=0, policies_published=0,
        services_started=0, sap_queries=0)
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + '\n')
    print(OUTPUT.relative_to(ROOT))
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
