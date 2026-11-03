"""Offline, read-only investigation. No HANA connector or capture execution path."""
from collections import Counter
from datetime import date
import json
from pathlib import Path
import sys

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_reader import FoundationReader
from modules.telchi.investigation.validation.controlled_physical_capture_v1.capture import (
    destination_lock, digest, file_inventory, read_checkpoint, save,
)

CAPTURE = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/physical-capture-physical-capture-to10000-20261029-v1-c04-b04')
CHECKPOINT = '7b8bbb992fcb83e3d0ec4ae4951084fad90fa12e5c7761ce0f408bf9b7b69099'
AS_OF = date(2026, 10, 29)
CUTOFF = date(2024, 10, 29)


def selective_query(keys):
    if not 1 <= len(keys) <= 25 or keys != sorted(set(keys)):
        raise ValueError('requires_1_to_25_unique_sorted_keys')
    if any(not isinstance(k, str) or not k.strip() for k in keys):
        raise ValueError('invalid_itemcode')
    return ('SELECT "ItemCode", "U_FormaFarmac" FROM "TELCHI"."OITM" '
            'WHERE "ItemCode" IN (' + ', '.join('?' for _ in keys) + ') ORDER BY "ItemCode"', list(keys))


def production_rule(alias='i'):
    # OWOR provides linkage, never evidence by itself. Disassembly is excluded.
    return (f"{alias}.CANCELED='N' AND {alias}.BaseType=202 "
            f"AND try_cast({alias}.Quantity AS DECIMAL(38,10))>0 "
            f"AND {alias}.ItemCode IS NOT NULL AND trim({alias}.ItemCode)<>'' "
            "AND o.DocEntry IS NOT NULL AND o.Type IN ('S','P') AND o.Status<>'C'")


def records(c, sql, params=None):
    cursor = c.execute(sql, params or [])
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def unique(c, relation, columns):
    n, distinct = c.execute(f'SELECT count(*),count(DISTINCT ({columns})) FROM {relation}').fetchone()
    if n != distinct:
        raise RuntimeError('duplicate_documentary_key:' + relation)


def summarize(c, relation, date_column):
    return records(c, f'SELECT count(*) AS row_count, min(try_cast({date_column} AS DATE)) first_date, '
                   f'max(try_cast({date_column} AS DATE)) last_date FROM {relation}')[0]


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    with destination_lock(CAPTURE):
        before = file_inventory(CAPTURE)
        assert digest(CAPTURE/'checkpoint.json') == CHECKPOINT
        cp, captured, seen, _ = read_checkpoint(CAPTURE)
        assert len(captured) == len(seen) == 10000
        assert {p.name for p in CAPTURE.glob('batch-*.json')} == {b['file'] for b in cp['batches']}
        assert not (CAPTURE/'pending.json').exists()
    pointer = DATA_ROOT/'manifests/reference_current.json'
    pointer_hash = digest(pointer)
    inventory, raw_inputs = {}, []
    with DuckLakeConnector().session(read_only=True) as c:
        c.execute('SET threads=2')
        c.execute("SET memory_limit='768MB'")
        f = FoundationReader().resolve_on(c)
        foundation_id = f.foundation_publication_id
        inventory['catalog_tables'] = records(c, "SELECT table_schema,table_name FROM information_schema.tables WHERE table_catalog='telchi' ORDER BY 1,2")
        inventory['foundation'] = dict(id=foundation_id, snapshot=f.ducklake_snapshot_id,
            base_snapshot=f.manifest_base_snapshot_id, manifest=f.manifest,
            reference_path=str(f.reference_path))
        for component, table in [('sales','sales_document'), ('sales','sales_line'),
                                 ('credit_memo','credit_memo_document'), ('credit_memo','credit_memo_line')]:
            relation = f.relation(component, table)
            inventory[table] = dict(schema=records(c, 'DESCRIBE SELECT * FROM '+relation),
                foundation_rows=c.execute('SELECT count(*) FROM '+relation).fetchone()[0],
                latest_atomic_rows=c.execute('SELECT count(*) FROM telchi.atomic.'+table).fetchone()[0])
            c.execute(f'CREATE TEMP VIEW {table} AS SELECT * FROM {relation}')
            unique(c, table, 'source_system,doc_entry' + (',line_num' if table.endswith('_line') else ''))
        for table in ['sales_document','credit_memo_document']:
            inventory[table]['coverage'] = summarize(c, table, 'doc_date')
            inventory[table]['document_rules'] = records(c, f'SELECT source_system,source_table,canceled,count(*) AS row_count FROM {table} GROUP BY ALL')
        for component, header, line in [('sales','sales_document','sales_line'),
                                         ('credit_memo','credit_memo_document','credit_memo_line')]:
            inventory[header]['line_coverage_by_year'] = records(c,
                f"SELECT year(try_cast(h.doc_date AS DATE)) document_year,count(DISTINCT h.doc_entry) headers, "
                f"count(l.line_num) joined_lines,count(DISTINCT l.item_code) items, "
                f"count(*) FILTER (WHERE l.item_code IS NOT NULL AND trim(l.item_code)<>'' "
                f"AND try_cast(l.quantity AS DECIMAL(38,10))>0 AND h.canceled='N') positive_item_lines "
                f"FROM {header} h LEFT JOIN {line} l ON h.doc_entry=l.doc_entry "
                "AND h.source_system=l.source_system GROUP BY 1 ORDER BY 1")
        for kind in ['production_order','production_issue']:
            manifests = sorted((DATA_ROOT/'raw/sap/TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1'/kind).glob('*/*/manifest.json'))
            assert len(manifests) == 9
            paths = []
            for path in manifests:
                m = json.loads(path.read_text())
                assert m['status'] == 'COMPLETED' and m['source_system'] == 'SAP_HANA'
                assert m['source_table'] == ('OWOR' if kind == 'production_order' else 'OIGE')
                for ref, expected in zip(m['file_references'], m['file_hashes'], strict=True):
                    assert digest(Path(ref)) == expected
                    paths.append(ref)
                raw_inputs.append(dict(path=str(path), sha256=digest(path), manifest=m))
            c.read_parquet(paths, filename=True).create_view(kind)
            unique(c, kind, 'DocEntry' + (',LineNum' if kind == 'production_issue' else ''))
            inventory[kind] = dict(schema=records(c, 'DESCRIBE SELECT * FROM '+kind),
                coverage=summarize(c, kind, 'PostDate' if kind == 'production_order' else 'DocDate'),
                publication='RAW_ONLY_NOT_FOUNDATION')
        inventory['production_receipt'] = dict(status='UNAVAILABLE_OIGN_IGN1',
            reason='No corresponding Atomic/Foundation table or raw capture found; OINM type 59 alone is insufficient.')
        # No blanket OINM 59/60 classification; it cannot substitute for header/base linkage.
        inventory['oinm_schema'] = records(c, 'DESCRIBE SELECT * FROM '+f.oinm())
        clauses = []
        for family, header, line, ht, lt in [('sales','sales_document','sales_line','OINV','INV1'),
                ('sales_return','credit_memo_document','credit_memo_line','ORIN','RIN1')]:
            eligible = (f"h.source_system='SAP_B1_HANA' AND l.source_system=h.source_system "
                f"AND h.source_table='{ht}' AND l.source_table='{lt}' AND h.canceled='N' "
                "AND try_cast(l.quantity AS DECIMAL(38,10))>0 AND l.item_code IS NOT NULL AND trim(l.item_code)<>'' "
                f"AND try_cast(h.doc_date AS DATE)<=DATE '{AS_OF}'")
            clauses.append(f"SELECT '{family}' AS event_kind,l.item_code, h.doc_entry, l.line_num, "
                f"try_cast(h.doc_date AS DATE) doc_date,l.raw_extraction_id origin, "
                f"'{ht}/{lt}' AS source_tables, l.quantity quantity FROM {header} h JOIN {line} l "
                f"ON h.doc_entry=l.doc_entry AND h.source_system=l.source_system WHERE {eligible}")
            inventory[line]['exclusions'] = records(c, f"SELECT count(*) total_lines, "
                f"count(*) FILTER (WHERE {eligible}) accepted_lines, "
                f"count(*) FILTER (WHERE h.doc_entry IS NULL) orphan_lines FROM {line} l "
                f"LEFT JOIN {header} h ON h.doc_entry=l.doc_entry AND h.source_system=l.source_system")[0]
        rule = production_rule()
        clauses.append("SELECT 'production_consumption' AS event_kind,i.ItemCode item_code, "
            "cast(i.DocEntry AS VARCHAR) doc_entry,cast(i.LineNum AS VARCHAR) line_num, "
            "cast(i.DocDate AS DATE) doc_date,i.filename origin,'OIGE/IGE1->OWOR' AS source_tables, "
            "i.Quantity quantity FROM production_issue i LEFT JOIN production_order o ON i.BaseEntry=o.DocEntry "
            f"WHERE {rule} AND cast(i.DocDate AS DATE)<=DATE '{AS_OF}'")
        inventory['production_issue']['rules'] = records(c,
            'SELECT i.CANCELED,i.BaseType,o.Type,o.Status,count(*) AS row_count, '
            f'count(*) FILTER (WHERE {rule}) accepted FROM production_issue i '
            'LEFT JOIN production_order o ON i.BaseEntry=o.DocEntry GROUP BY ALL')
        c.execute('CREATE TEMP TABLE evidence AS '+' UNION ALL '.join(clauses))
        assert c.execute('SELECT count(*) FROM evidence WHERE doc_date IS NULL').fetchone()[0] == 0
        unique(c, 'evidence', 'event_kind,doc_entry,line_num')
        # Full evidence per document/line, not merely an unexplained set of keys.
        evidence_path = output/'evidence.parquet'
        c.execute('COPY (SELECT * FROM evidence ORDER BY item_code,event_kind,doc_date,doc_entry,line_num) TO ? (FORMAT PARQUET)', [str(evidence_path)])
        aggregates = records(c, f"SELECT item_code,event_kind,count(*) lines,count(DISTINCT doc_entry) documents, "
            f"min(doc_date) first_date,max(doc_date) last_date,bool_or(doc_date>=DATE '{CUTOFF}') recent, "
            f"bool_or(doc_date<DATE '{CUTOFF}') historical FROM evidence GROUP BY ALL ORDER BY item_code,event_kind")
        inventory['evidence_by_family'] = records(c, 'SELECT event_kind,count(*) lines,count(DISTINCT item_code) products,min(doc_date) first_date,max(doc_date) last_date FROM evidence GROUP BY ALL ORDER BY event_kind')
        ref_path = f.reference('products')
        reference_rows = c.execute("SELECT item_code,source_native_id,canonical_product_id FROM read_parquet(?) WHERE source_system='SAP_HANA'", [str(ref_path)]).fetchall()
        assert len({r[0] for r in reference_rows}) == len(reference_rows)
        assert all(r[0] == r[1] for r in reference_rows)
        reference = {r[0]:r[2] for r in reference_rows}
        inventory['reference'] = dict(sha256=digest(ref_path),rows=len(reference),schema=records(c,'DESCRIBE SELECT * FROM read_parquet(?)',[str(ref_path)]))
        assert FoundationReader().resolve_on(c).foundation_publication_id == foundation_id
    by_item = {}
    for a in aggregates:
        by_item.setdefault(a['item_code'], []).append(a)
    operational = set(by_item)
    sold = {a['item_code'] for a in aggregates if a['event_kind']=='sales'}
    returned = {a['item_code'] for a in aggregates if a['event_kind']=='sales_return'}
    production = {a['item_code'] for a in aggregates if a['event_kind']=='production_consumption'}
    sales = sold | returned
    recent = {a['item_code'] for a in aggregates if a['recent']}
    historical = {a['item_code'] for a in aggregates if a['historical']}
    physical = {r['ItemCode']:r['U_FormaFarmac'] for r in captured}
    pending = sorted(operational-seen)
    distribution = Counter(json.dumps(physical[k], ensure_ascii=False) for k in operational & seen)
    explicit = sum(physical[k] in ('1','2','3') for k in operational & seen)
    products = [dict(ItemCode=k, canonical_product_id=reference.get(k), captured=k in seen,
        U_FormaFarmac=physical.get(k), classification_observed=k in seen,
        recent= k in recent, historical=k in historical, evidence=by_item[k]) for k in sorted(operational)]
    plan = dict(status='PREPARED_NOT_EXECUTABLE_AUTHORIZATION_REQUIRED',item_codes=pending,
        item_count=len(pending), batches=[dict(index=i//25+1,sql=selective_query(pending[i:i+25])[0],
            parameters=pending[i:i+25]) for i in range(0,len(pending),25)],
        controls=dict(max_items=25,active_connections=1,parallelism=0,automatic_retries=0,
            pause_seconds=10,hana_seconds=1.5,local_persistence_seconds=10,fsync=True,
            sha256=True,recoverable_journal=True,durable_checkpoints=True,idempotent_resume=True,
            interprocess_exclusion=True,verify_cursor_connection_closed=True),
        implementation_gate='Existing keyset checkpoint/query fingerprints are incompatible with IN selection. Do not pass this plan to existing capture runner. Separate authorized implementation and fault-injection gate required.',
        protocol=['Freeze sorted pending keys and hash plan; bind every journal/checkpoint to that hash.',
            'Reuse existing directory lock, durable save/fsync/readback and destination persistence guards, not global iowait alone.',
            'One SELECT per batch; validate returned keys are unique, ordered and a subset of requested keys; persist missing keys separately, never invent NULL rows.',
            'Record original code and observation time; commit journal then durable batch then checkpoint; recover offline before any resume.',
            'Checkpoint by requested batch index, including missing keys; never use last returned key for IN selection.',
            'Abort on elapsed HANA >1.5s or local persistence >10s; no retry, no next query after uncertain state; allow fsync to finish.',
            'Close cursor in finally; verify closure and close sole connection on every exit; pause 10s between queries.',
            'No backfill, publication or limit expansion. No selective HANA execution in this investigation.'])
    assert file_inventory(CAPTURE) == before
    assert digest(pointer) == pointer_hash
    counts = dict(sold=len(sold),sales_returns=len(returned),sales_including_returns=len(sales),
        production_effective_observed=len(production),both=len(sales & production),total=len(operational),
        recent_24_months=len(recent),historical_before_24_months=len(historical),historical_only=len(historical-recent),
        covered=len(operational & seen),pending=len(pending),captured_without_accredited_activity=len(seen-operational),
        explicit_physical=explicit,without_explicit_physical=len(operational)-explicit,
        operational_missing_reference=len(operational-reference.keys()))
    report = dict(status='PARTIAL_BUSINESS_COVERAGE_OFFLINE_COMPLETE',branch='feature/console-backend-core',
        as_of=str(AS_OF),cutoff_inclusive=str(CUTOFF),counts=counts,
        classification=[dict(original_code=json.loads(k),products=v) for k,v in sorted(distribution.items())],
        classification_unobserved=len(pending),inventory=inventory,raw_inputs=raw_inputs,
        capture=dict(path=str(CAPTURE),checkpoint_sha256=CHECKPOINT,rows=10000,all_file_hashes=before,
            integrity='VERIFIED_ALL_BATCH_HASHES_ORDER_UNIQUENESS_AND_SOURCE_UNCHANGED',
            consistency='MULTI_SESSION_INTERVAL_NOT_TRANSACTIONAL_SNAPSHOT'),
        warnings=['Universe is a verified lower bound, not the entire enterprise catalog.',
            'Production receipts OIGN/IGN1 unavailable; finished products cannot be accredited from open OWOR or generic OINM 59.',
            'Production consumption from local raw 2026 captures, not Foundation; earlier OWOR linkage outside captured window remains unaccredited.',
            'Sales credit memo is documentary return evidence, not independent proof of physical stock receipt; canceled/zero/nonpositive lines excluded.',
            'Observed first/last dates do not prove continuous historical completeness. Credit memos and production lack pre-2026 history; sources stop in September, not October 29.',
            'Historical headers are not historical ItemCode coverage: all accredited item lines here are 2026. Zero older products is NOT proof of no earlier business activity.',
            'Historical and recent sets overlap; historical_only is the disjoint older-only set.',
            'Captured without activity means no evidence in inspected coverage, never nonexistent or erroneous import.',
            'Physical attributes are current observations, not historical backfill. Coverage includes observed NULL/unknown; only original codes 1,2,3 are explicit.'],
        safety=dict(hana_queries=0,sap_writes=0,publications=0,shared_data_writes=0,
            reference_pointer_unchanged=True,foundation_unchanged=True,capture_unchanged=True,
            host_preflight='BUSY_BUT_SAFE',duckdb_threads=2,memory_limit='768MB',
            unrelated_processes_terminated=0,own_processes_left_running=0),
        evidence_sha256=digest(evidence_path))
    # JSON uses ISO dates without changing source values in the Parquet evidence.
    for name, value in [('report.json',report),('products.json',products),('selective_plan.json',plan),
                        ('captured_without_activity.json',sorted(seen-operational))]:
        save(output/name,json.loads(json.dumps(value,default=str,ensure_ascii=False)))
    labels = [('Productos únicos vendidos','sold'),('Productos con devoluciones','sales_returns'),
        ('Ventas o devoluciones','sales_including_returns'),('Producción efectiva acreditada (componentes)','production_effective_observed'),
        ('Ventas/devoluciones y producción','both'),('Total único con movimiento','total'),
        ('Actividad últimos 24 meses','recent_24_months'),('Actividad histórica anterior (puede solapar)','historical_before_24_months'),
        ('Solo histórica anterior','historical_only'),('Cubiertos por captura U_FormaFarmac','covered'),
        ('Pendientes HANA del universo acreditado','pending'),('Sin clasificación física explícita','without_explicit_physical'),
        ('Capturados sin movimiento acreditado','captured_without_accredited_activity')]
    text = '# Productos con movimiento real — análisis offline\n\nResultado parcial en cobertura empresarial; cálculo completo para la evidencia local acreditada. Sin consultas HANA ni publicación.\n\n'
    text += '| Métrica | Productos |\n| --- | ---: |\n'+''.join(f'| {label} | {counts[key]} |\n' for label,key in labels)
    text += '\n## Distribución física\n\nCódigos originales observados sobre el universo operativo; pendiente no equivale a NULL. Solo 1, 2 y 3 son explícitos.\n\n| Código original JSON | Productos |\n| --- | ---: |\n'
    text += ''.join(f'| `{k}` | {v} |\n' for k,v in sorted(distribution.items()))+f'| No observado (pendiente) | {len(pending)} |\n'
    text += '\n## Cobertura y límites\n\nCorte analítico 2026-10-29; últimos 24 meses desde 2024-10-29 inclusive. Fechas observadas, no garantía de continuidad.\n\n'
    text += '| Familia | Primera fecha | Última fecha | Líneas |\n| --- | --- | --- | ---: |\n'+''.join(f"| {r['event_kind']} | {r['first_date']} | {r['last_date']} | {r['lines']} |\n" for r in inventory['evidence_by_family'])
    text += '\n'+'\n'.join('- '+w for w in report['warnings'])+'\n'
    text += '\n## Evidencia y captura futura\n\nLos artefactos conservan claves originales, fechas, documentos, origen y hashes; no alteran Atomic, Reference, Foundation ni capturas anteriores.\n\n'
    text += '- `report.json`: inventario, schemas, exclusiones, cobertura, integridad y métricas.\n- `evidence.parquet`: todas las evidencias por documento/línea.\n- `products.json`: universo único ordenado y cruces por ItemCode.\n- `selective_plan.json`: parámetros por lote, límites y protocolo; NO ejecutable ni autorizado.\n- `captured_without_activity.json`: sin evidencia local, no artículos erróneos.\n'
    text += f'\nFoundation fijada: `{foundation_id}`, snapshot `{f.ducklake_snapshot_id}`. Checkpoint: `{CHECKPOINT}`.\n'
    text += '\nEl extractor keyset existente no acepta esta selección: sus fingerprints no son compatibles. Se requiere adaptación autorizada y gate de recuperación antes de ejecutar el plan; no se ha rebajado ningún control.\n'
    text += '\nLos encabezados OINV llegan a 2022, pero sus líneas no acreditan productos anteriores a 2026: el cero histórico es falta de cobertura, no ausencia empresarial. Hay '+str(counts['operational_missing_reference'])+' claves operativas ausentes de Reference; se preservan sin inventar identidad canónica.\n'
    text += '\nNULL observado: '+str(distribution.get('null',0))+'; códigos desconocidos observados: '+str(sum(v for k,v in distribution.items() if json.loads(k) not in [None,'0','1','2','3','4','5']))+'. Los no observados quedan separados.\n'
    (output/'report.md').write_text(text)
    save(output/'artifact_hashes.json',{p.name:digest(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps(counts,indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
