"""Supervised one-off DEV composition of the existing adaptive researcher."""
import asyncio
from dataclasses import asdict, replace
import fcntl
import json
import os
from pathlib import Path
import threading

from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.exploratory_sql.authorized_foundation import (
    discover, DiscoveredSource, EffectiveScope, SourcePolicy, ResearchBinding, AuthorizedFoundationExecutor)
from modules.telchi.exploratory_sql.contracts import Column
from modules.telchi.exploratory_sql.foundation import PUBLICATION, SNAPSHOT, PERMISSION, local_context
from modules.telchi.exploratory_sql.foundation_dev import DevBudget, DevExecutor
from modules.telchi.exploratory_sql.ask import Session
from modules.telchi.exploratory_sql.validator import canonical

ROOT = Path(os.getenv('TELCHI_BUSINESS_EVIDENCE_ROOT','../../data/reports/telchi/luna-real-business-query-v1'))
QUESTION = 'Durante 2026, ¿en qué mes vendimos más materias primas y cuál fue el cliente al que más le vendimos en ese mes?'

class SupervisedExecutor(AuthorizedFoundationExecutor, DevExecutor):
    def __init__(self, context, *, authorized=False):
        if not authorized or os.getenv('TEAM360_ENV') != 'development':
            raise ValueError('explicit_dev_exception_required')
        AuthorizedFoundationExecutor.__init__(self, context, reader=FoundationReader())
        self.initial_swap = self.swap_bytes()
        self.done = threading.Event()
        self.monitor = threading.Thread(target=self.watch, name='telchi-dev-memory')
        self.monitor.start()

    def _prepare_connection(self, db, context):
        try:
            return AuthorizedFoundationExecutor._prepare_connection(self, db, context)
        except Exception as exc:
            (ROOT / 'private-setup-diagnostic.txt').write_text(type(exc).__name__ + ': ' + str(exc))
            raise

    execute = DevExecutor.execute
    close = DevExecutor.close


def save(report):
    p = ROOT / 'luna.json'
    tmp = p.with_suffix('.pending')
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    tmp.replace(p)


def main():
    os.umask(0o077)
    if os.getenv('TEAM360_ENV') != 'development':
        raise ValueError('DEV_required')
    ROOT.mkdir(parents=True,exist_ok=True)
    if (ROOT/'luna.json').exists() and not os.getenv('TELCHI_DIAGNOSE_SAVED_QUERY'):
        raise ValueError('evidence_exists_use_new_output_root')
    with open(f'/tmp/telchi-exploratory-dev-{os.getuid()}.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reader = FoundationReader()
        with reader.connector.session(read_only=True) as db:
            db.execute("SET threads=1")
            db.execute("SET memory_limit='512MB'")
            db.execute("SET max_temp_directory_size='0B'")
            access = reader.resolve_on(db)
            assert (access.foundation_publication_id, str(access.ducklake_snapshot_id)) == (PUBLICATION, SNAPSHOT)
            sources, gaps = discover(db, access)
            by_name = {s.name: s for s in sources}
            # Reuse the existing investigator's commercial-line projection,
            # exposing published documentary/customer/product dimensions. No
            # classification value, product code or period is selected here.
            docs = by_name['sales_document'].relation
            lines = by_name['sales_line'].relation
            materials = by_name['material_supply_status'].relation
            customers = by_name['ref_customers'].relation
            products = by_name['ref_products'].relation
            from modules.telchi.datalake.product_business_classification import ProductFacts, classify_product
            facts = db.execute(f'''SELECT p.item_code,p.sap_item_name,p.sap_itms_grp_cod,
                p.sap_invnt_item,p.sap_sell_item,p.sap_prchse_item,p.sap_valid_for,m.is_raw_material
                FROM {products} p JOIN {materials} m ON m.item_code=p.item_code
                WHERE p.source_system='SAP_HANA' ''').fetchall()
            assert len(facts)<=5000 and len({r[0] for r in facts})==len(facts)
            crosswalk=[]
            for code,name,group,inv,sell,purchase,active,leaf in facts:
                result=classify_product(ProductFacts(code,name,int(group) if group else None,None,
                    inv=='Y',sell=='Y',purchase=='Y',active=='Y',is_bom_component=bool(leaf)))
                crosswalk.append((code,result.product_business_type,result.status,result.rule_id,result.evidence))
            fields=('item_code','product_business_type','classification_status','rule_id','classification_evidence')
            quote=lambda value: "'"+str(value).replace("'","''")+"'"
            values=','.join('('+','.join(quote(v) for v in row)+')' for row in crosswalk)
            business='(SELECT * FROM (VALUES '+values+') AS b('+','.join(fields)+'))'
            sources += (DiscoveredSource('product_business_classification',business,
                tuple(Column(n,'VARCHAR',True) for n in fields),
                ('Existing canonical product_business_classification kernel using published SAP item groups and structural material evidence. Limited published coverage, not full historical business master.',)),)
            (ROOT/'business-crosswalk.json').write_text(json.dumps({'fields':fields,'rows':crosswalk,
                'authority':'Existing TELCHI_PRODUCT_BUSINESS_CLASSIFICATION_V1 kernel; no new classification rules'},indent=2))
            operation = f'''(SELECT l.doc_entry,l.line_num,l.item_code,
                TRY_CAST(l.line_total AS DECIMAL(38,6)) AS line_total,l.currency,
                CAST(TRY_CAST(d.doc_date AS DATE) AS VARCHAR) AS doc_date,
                strftime(TRY_CAST(d.doc_date AS DATE),'%Y-%m') AS doc_month,d.card_code,
                c.name AS card_name,m.is_raw_material,m.material_class,m.material_name,
                b.product_business_type,b.classification_status,b.rule_id,
                l.raw_extraction_id,l.source_as_of
                FROM {lines} l JOIN {docs} d ON l.doc_entry=d.doc_entry
                LEFT JOIN (SELECT DISTINCT item_code,is_raw_material,material_class,material_name
                    FROM {materials}) m ON m.item_code=l.item_code
                LEFT JOIN {customers} c ON c.code=d.card_code AND c.source_system='SAP_HANA'
                LEFT JOIN {business} b ON b.item_code=l.item_code
                WHERE l.source_system='SAP_B1_HANA' AND l.source_table='INV1'
                AND d.source_system='SAP_B1_HANA' AND d.source_table='OINV' AND d.canceled='N')'''
            schema = db.execute('DESCRIBE SELECT * FROM '+operation).fetchall()
            sources += (DiscoveredSource('sales_operation', operation,
                tuple(Column(r[0],r[1],r[2]=='YES') for r in schema),
                ('Active OINV/INV1 commercial lines, published product classification and billed SAP customer; before credit memos. Classification coverage and join uniqueness require independent checks.',)),)
        (ROOT / 'extended-discovery.json').write_text(json.dumps({
            'sources': [asdict(s) for s in sources], 'gaps': gaps,
            'binding': access.as_dict()}, indent=2, default=str))
        # Generic business projection: retain all published sources, omit only
        # transport/ETL bookkeeping. No SKU, classification or period list.
        omit = {'atomic_id','business_id','built_at','derivation_id','derivation_version',
                'transformation_version','schema_version','reference_version','reference_manifest_hash',
                'raw_extraction_id','source_key_columns'}
        sources = tuple(replace(s, columns=tuple(c for c in s.columns
            if not c.name.startswith('_') and c.name not in omit),
            limitations=('Published schema; business grain and completeness require independent checks.',)) for s in sources)
        c = local_context('TELCHIAI_LUNA_REAL_BUSINESS_QUERY_V1')
        scope = EffectiveScope(c.identity, c.organization, c.workspace, c.permissions)
        policies = [SourcePolicy(s.name, PERMISSION, c.organization, c.workspace,
            whole_dataset=True) for s in sources]
        binding = ResearchBinding(resolve_scope=lambda: scope, scope=scope,
            publication=PUBLICATION, snapshot=SNAPSHOT, sources=sources, policies=policies,
            investigation_id=c.investigation_id, budget=DevBudget())
        print('catalog_bytes', len(canonical(asdict(binding.context.catalog)).encode()), flush=True)
        # Cheap trusted setup check before spending any model calls.
        with SupervisedExecutor(binding.context, authorized=True) as probe:
            with probe._open_connection(binding.context.effective_budget) as db:
                probe._prepare_connection(db, binding.context)
                db.execute('SELECT doc_month,line_total FROM sales_operation LIMIT 1').fetchall()
                if os.getenv('TELCHI_DIAGNOSE_SAVED_QUERY'):
                    from modules.telchi.exploratory_sql.contracts import ExploratoryQueryProposal
                    from modules.telchi.exploratory_sql.validator import validate
                    raw = json.loads((ROOT/'luna.json').read_text())['turns'][0]['proposal']
                    for key in ('candidate_relations','parameters','requested_budget','version'):
                        raw.pop(key,None)
                    proposal = ExploratoryQueryProposal(**raw, requested_budget=DevBudget())
                    decision, query = validate(proposal,binding.context)
                    print(query.generated_sql, flush=True)
                    print(db.execute(query.generated_sql,{p.name:p.value for p in query.parameters}).fetchmany(30),flush=True)
                    binding.close()
                    return
        # Binding is explicitly LOCAL TEST identity, never authenticated Console.
        from modules.telchi.exploratory_sql import ask as ask_module
        ask_module.SYSTEM += '''
SQL subset notes (general grammar, not business answers): filter BOOLEAN columns
with WHERE boolean_column or WHERE NOT boolean_column. Do not compare to TRUE/FALSE:
DuckDB parses those literals as unsupported CAST nodes. CASE supports at most eight
branches. The trusted sales_operation includes doc_month, an ISO YYYY-MM dimension.
Classification contract: is_raw_material/material_class are LEGACY STRUCTURAL
BOM-leaf flags, NOT sufficient business classification (they can include packaging
and other products). product_business_type/classification_status/rule_id expose the
EXISTING canonical TELCHI_PRODUCT_BUSINESS_CLASSIFICATION_V1 kernel, calculated from
published SAP item groups plus published structural evidence. Use its validated
business classification, not the legacy flag alone, for business category sales.
Coverage is limited to published structural-reference items. No prior figures or
winner are provided. Discover and investigate them yourself.
Business reporting constraints supplied by the operator: compare commercial line
amounts in bolivianos (BS), keeping other currencies separate; never mix physical
units; use data-backed business classification; report billed SAP card_code and
card_name; distinguish invoices from credit memos and collections. Discover the
actual temporal coverage of 2026, not presumed calendar completeness. If published
classification is incomplete, retain the available result and explain its scope.
Discovered source grain is unaccredited by the built-in checker; independent human
verification follows, so retain observed results even when automatic claims are UNVERIFIED.
'''
        session = Session(authorized_binding=binding, progress=lambda x: print(x, flush=True))
        try:
            report = asyncio.run(session.ask(QUESTION, save, executor_factory=SupervisedExecutor))
            report['identity'] = 'SUPERVISED_LOCAL_DEV_TEST_NOT_PRESIDENCY_OR_CONSOLE'
            report['owner_authorization'] = 'TELCHIAI_LUNA_REAL_BUSINESS_QUERY_V1; existing DEV IO-only exception'
            save(report)
            print(report.get('status'), report.get('reason'), report.get('business_answer'), flush=True)
        finally:
            binding.close()

if __name__ == '__main__':
    main()
