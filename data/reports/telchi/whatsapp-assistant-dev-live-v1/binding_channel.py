"""Create only the approved Telchi DEV horizontal channel using existing provisioning."""
import asyncio,json,os
from pathlib import Path
from dotenv import dotenv_values
import psycopg
from psycopg.rows import dict_row
ROOT=Path(__file__).resolve().parent
async def main():
    for k,v in dotenv_values('../.env.backend-dev.local').items():
        if v is not None:os.environ[k]=v
    from modules.db.settings import get_database_settings
    from modules.telchi.provisioning.repository import Seed,ProvisioningRepository,runtime_policy
    from modules.messaging.repository import MessagingRepository
    initial=json.loads((ROOT/'binding-preflight.json').read_text()); w=initial['workspace'][0]
    users={u['email']:str(u['id']) for u in initial['users']}
    seed=Seed(str(w['id']),str(w['organization_id']),'grants',users['admin@telchiai.com'],users['devfull@telchiai.com'],'team360-meta-dev',os.environ['META_TEAM360_PHONE_NUMBER_ID'])
    policy=runtime_policy(seed,module_enable_approved=True,whole_workspace_approved=True)
    async with await psycopg.AsyncConnection.connect(get_database_settings().dsn,row_factory=dict_row,autocommit=True,application_name='telchi-dev-channel-activation') as c:
        async with c.transaction():
            result=await ProvisioningRepository().provision(c,seed,approval_refs={'operation':'TELCHI WHATSAPP DEV BINDING & LIVE V1','scope':'existing documented source quantity permission only'})
            # Existing grants must be reused, not enlarged by this activation.
            assert len(result['created'])==1 and result['created'][0]['table']=='communication_channels'
            binding=await MessagingRepository().binding(c,workspace_slug='telchi_dev',channel_alias='telchi_whatsapp_dev',provider='evolution',instance='team360-meta-dev')
            assert binding.module=='telchi' and binding.environment=='dev' and binding.receiver_context==seed.receiver_context
            await MessagingRepository().validate_transport_schema(c)
        # Re-run plan in a rollback transaction to prove idempotence without extra audit writes.
        async with c.transaction(force_rollback=True):
            repeat=await ProvisioningRepository().provision(c,seed); assert repeat['created']==[]
    result={'channel_id':binding.channel_id,'workspace_id':binding.workspace_id,'environment':binding.environment,'module':binding.module,'tenant':binding.tenant_id,'dispatcher':'horizontal_v1','instance':binding.provider_instance,'runtime_policy_approved':policy.module_enabled and policy.whole_workspace_scope_verified,'created_only_channel':True,'idempotence':'PASS','live_runtime':'NOT_STARTED','phone_binding':'NOT_CREATED'}
    (ROOT/'binding-channel.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':asyncio.run(main())
