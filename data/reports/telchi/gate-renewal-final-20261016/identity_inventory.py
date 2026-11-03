from pathlib import Path
import sys, asyncio, json, os
B=Path(__file__).resolve().parents[4]/'SrvRestAstroLS_v1/backend'
sys.path.insert(0,str(B)); os.chdir(B)
from modules.telchi.assistant import whatsapp_dev as d, whatsapp_dev_lifecycle as l
l.load_config(d.PRIVATE_ROOT/'whatsapp-dev-control.json')
a=d.read_approval(d.PRIVATE_ROOT/'whatsapp-dev-session-approval.json')
async def main():
 import psycopg
 from psycopg.rows import dict_row
 from modules.db.settings import get_database_settings
 from modules.console.repositories import PermissionConsoleRepository
 async with await psycopg.AsyncConnection.connect(get_database_settings().dsn,row_factory=dict_row,connect_timeout=5) as c:
  async with c.transaction():
   await c.execute('SET TRANSACTION READ ONLY')
   rows=await (await c.execute("SELECT DISTINCT b.user_id,b.sender_identity,b.tenant_id,b.workspace_id,u.status,b.verification_status FROM messaging_phone_bindings b JOIN core_users u ON u.id=b.user_id WHERE b.environment='dev' AND b.provider='evolution' LIMIT 30")).fetchall()
   out=[]
   for r in rows:
    perms=await PermissionConsoleRepository().list_effective_permissions(c,str(r['workspace_id']),str(r['user_id']))
    out.append(dict(active=r['status'] in {'active','testing'},verified=r['verification_status']=='verified',telchi=r['tenant_id']=='telchi',approved=str(r['user_id'])==a['user_id'],has_permission=d.PERMISSION in perms,permission_count=len(perms)))
   print(json.dumps(dict(source=d.source_digest(),identities=out)))
asyncio.run(main())
