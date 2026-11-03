"""Repair only this run's generated DSN representation, not its credentials/roles."""
import json
from pathlib import Path
import sys
from urllib.parse import quote, urlencode
sys.path.insert(0,str(Path(__file__).parent))
from provision import P
from psycopg.conninfo import conninfo_to_dict
from modules.telchi.assistant.whatsapp_dev_lifecycle import atomic
p=P/'runtime-dsns.json'
before=json.loads(p.read_text());after={}
for side,value in before.items():
    d=conninfo_to_dict(value)
    after[side]='postgresql://'+quote(d['user'],safe='')+':'+quote(d['password'],safe='')+'@'+d['host']+':'+d.get('port','5432')+'/'+d['dbname']
atomic(p,after)
print('PRIVATE_DSN_FORMAT=POSTGRESQL_URL CREDENTIAL_ROTATIONS=0')
