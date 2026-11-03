"""Opt-in DEV PostgreSQL authorization probes. Mutations always rolled back.

Real Console permission resolution/registry, not conversational/model E2E.
"""
import asyncio
from dataclasses import replace
import json
import os
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from modules.db.settings import get_database_settings
from modules.console.repositories import PermissionConsoleRepository
from modules.telchi.assistant.handler import BusinessAuthorization, BusinessPolicy
from modules.telchi.assistant.tests.test_assistant import context
from modules.telchi.datalake.operational_query import PERMISSIONS
from modules.telchi.provisioning.operational_repository import OperationalRegistrationRepository, ROLE, WORKSPACE, PILOT, TARGET


async def run():
    if os.getenv('TEAM360_ENV') not in {'dev','development'}:
        raise RuntimeError('DEV required')
    report = dict(scope='real PostgreSQL authorization port, no model/readers', operations=[], rollback=True)
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn,connect_timeout=5,row_factory=dict_row) as conn:
        await conn.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
        repo = OperationalRegistrationRepository()
        await repo.guard(conn)
        assert await repo.target(conn)==TARGET
        resolver=PermissionConsoleRepository()
        effective=await resolver.list_effective_permissions(conn,WORKSPACE,PILOT)
        c=context()
        c=replace(c,channel=replace(c.channel,workspace_id=WORKSPACE),
                  sender_identity=replace(c.sender_identity,user_id=PILOT,workspace_id=WORKSPACE,permissions=frozenset(effective)))
        auth=BusinessAuthorization(BusinessPolicy('telchi',WORKSPACE,None,True,True,
                    pilot_access_check=lambda:None,pilot_user_id=PILOT))
        # Remove the preexisting module-wide grant only inside this rollback:
        # ALLOW must derive from explicit business-role permissions, not FULL_ACCESS.
        await conn.execute('UPDATE core_module_full_access_grants SET revoked_at_utc=now(),revoked_by=granted_by WHERE workspace_id=%s AND user_id=%s AND revoked_at_utc IS NULL',(WORKSPACE,PILOT))
        no_full=await resolver.list_effective_permissions(conn,WORKSPACE,PILOT)
        assert set(PERMISSIONS.values())<=set(no_full)
        assert not {'user.manage','role.manage','audit.view'} & set(no_full)
        report['explicit_business_role_without_full_access']=True
        for metric,permission in PERMISSIONS.items():
            async def allowed(ctx=c):return await auth.allowed(ctx,conn,required_permission=permission)
            checks={}
            checks['authorized']=await allowed()
            checks['no_permission']=not await allowed(replace(c,sender_identity=replace(c.sender_identity,permissions=frozenset())))
            checks['foreign_workspace']=not await allowed(replace(c,channel=replace(c.channel,workspace_id=str(uuid4()))))
            checks['invalid_identity']=not await allowed(replace(c,sender_identity=replace(c.sender_identity,user_id=str(uuid4()))))
            await conn.execute('SAVEPOINT operation_probe')
            await conn.execute('UPDATE core_workspace_capabilities SET enabled=false WHERE workspace_id=%s AND capability_code=%s',(WORKSPACE,metric+'.v1'))
            checks['disabled_capability']=not await allowed()
            await conn.execute('ROLLBACK TO SAVEPOINT operation_probe')
            await conn.execute('DELETE FROM core_workspace_capabilities WHERE workspace_id=%s AND capability_code=%s',(WORKSPACE,metric+'.v1'))
            checks['unregistered_capability']=not await allowed()
            await conn.execute('ROLLBACK TO SAVEPOINT operation_probe')
            await conn.execute('''DELETE FROM core_role_permissions WHERE role_id IN
                (SELECT id FROM core_roles WHERE workspace_id=%s AND role_code=%s)
                AND permission_id IN(SELECT id FROM core_permissions WHERE permission_code=%s)''',(WORKSPACE,ROLE,permission))
            checks['revoked_stale_identity']=not await allowed()
            fresh=await resolver.list_effective_permissions(conn,WORKSPACE,PILOT)
            checks['revoked_fresh_identity']=not await allowed(replace(c,sender_identity=replace(c.sender_identity,permissions=frozenset(fresh))))
            await conn.execute('ROLLBACK TO SAVEPOINT operation_probe')
            checks['recovery']=await allowed()
            await conn.execute('RELEASE SAVEPOINT operation_probe')
            assert all(checks.values()),(metric,checks)
            report['operations'].append(dict(metric=metric,permission=permission,checks=checks))
        await conn.rollback()
        report['restored_effective']=await resolver.list_effective_permissions(conn,WORKSPACE,PILOT)==effective
        assert report['restored_effective']
    return report


if __name__=='__main__':
    print(json.dumps(asyncio.run(run()),indent=2))
