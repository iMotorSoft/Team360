"""Read-only schema/coverage discovery for independently authored controls."""
import json
import os
from pathlib import Path
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

control = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/whatsapp-dev-control.json')
os.environ.update(json.loads(control.read_text())['env'])
connector = DuckLakeConnector()
with connector.session(read_only=True) as db:
    db.execute('SET threads=2')
    db.execute("SET memory_limit='512MB'")
    access = FoundationReader(connector).resolve_on(db)
    relations = dict(docs=access.sales('sales_document'), lines=access.sales('sales_line'),
                     credits=access.credit_memo('credit_memo_document'), stock=access.oitw())
    for dataset in ('purchase_order', 'purchase_order_line', 'purchase_receipt', 'purchase_receipt_line', 'ap_invoice'):
        relations[dataset] = access.operational_observation('purchasing', dataset)
    result = dict(foundation=access.as_dict(), manifest=access.manifest, relations=relations, schemas={})
    for name, relation in relations.items():
        result['schemas'][name] = db.execute('DESCRIBE SELECT * FROM '+relation).fetchall()
    output = Path('../../data/reports/telchi/blind-investigative-v1/foundation-schema.json')
    if output.exists():
        raise ValueError('output_exists')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str)+'\n')
    for name, schema in result['schemas'].items():
        print(name, [(r[0], r[1]) for r in schema])
    print('FOUNDATION', access.foundation_publication_id)
