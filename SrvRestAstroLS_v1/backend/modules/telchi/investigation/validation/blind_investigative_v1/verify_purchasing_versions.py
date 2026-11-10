"""Supplementary independent control: distinguish legacy and observed purchasing.

Added after the trace exposed selection of the legacy source; does not change
questions or rerun Luna. Verifies both published versions without model SQL.
"""
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader

os.environ.update(json.loads(Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/whatsapp-dev-control.json').read_text())['env'])
output = Path('../../data/reports/telchi/blind-investigative-v1/purchasing-versions.json')
if output.exists():
    raise ValueError('new_output_required')
connector = DuckLakeConnector()
report = dict(method=__doc__, controls=[], verifier_setup_note='Initial ancillary verifier discovery failed: legacy purchasing has no source_as_of column. Removed that invalid metadata projection only; no Luna retry, no runtime edit, no answer/control predicate changed.')
with connector.session(read_only=True) as db:
    db.execute('SET threads=2')
    db.execute("SET memory_limit='512MB'")
    access = FoundationReader(connector).resolve_on(db)
    report['foundation'] = access.as_dict()
    datasets = access.manifest['components']['purchasing']['datasets']
    for name in ('purchase_order','purchase_order_line','ap_invoice'):
        entry = datasets[name]
        paths = entry['file_references']
        for path, sha in zip(paths, entry['file_hashes'], strict=True):
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha
        relation = 'read_parquet(['+','.join("'"+p.replace("'","''")+"'" for p in paths)+'])'
        db.execute('CREATE TEMP VIEW legacy_'+name+' AS SELECT * FROM '+relation)
        cursor = db.execute('DESCRIBE SELECT * FROM legacy_'+name)
        report[name+'_schema'] = cursor.fetchall()
    def query(name, sql):
        start=perf_counter(); cursor=db.execute(sql); columns=[r[0] for r in cursor.description]
        rows=[dict(zip(columns,r)) for r in cursor.fetchall()]
        report['controls'].append(dict(name=name,sql=sql,rows=rows,seconds=perf_counter()-start))
        print(name,rows)
    query('legacy_line_fields', 'SELECT * FROM legacy_purchase_order_line LIMIT 1')
    query('legacy_line_coverage', 'SELECT min(doc_date) first_doc,max(doc_date) last_doc,count(*) lines FROM legacy_purchase_order_line')
    query('legacy_partial_population', '''SELECT count(*) partial_lines FROM legacy_purchase_order_line
        WHERE canceled='N' AND line_status='O' AND CAST(open_qty AS DECIMAL(38,6))>0
        AND CAST(open_qty AS DECIMAL(38,6))<CAST(quantity AS DECIMAL(38,6))''')
    query('legacy_ap_coverage', 'SELECT min(doc_date) first_doc,max(doc_date) last_doc,count(*) invoices FROM legacy_ap_invoice')
    query('legacy_ap_october', '''SELECT count(*) invoices,count(DISTINCT card_code) vendors,sum(CAST(doc_total AS DECIMAL(38,6))) amount
        FROM legacy_ap_invoice WHERE canceled='N' AND currency='BS' AND doc_date>='2026-10-01' AND doc_date<'2026-11-01' ''')
output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n')
