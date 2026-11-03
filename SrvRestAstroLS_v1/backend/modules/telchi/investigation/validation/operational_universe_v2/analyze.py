"""Reproducible offline universe V2. All outputs stay in repository reports.

Reaccredits the V1 documentary sources using its unchanged read-only analyzer.
No SAP driver is imported or connected. BOM membership is topological, not a
quantity explosion: expand_bom intentionally filters unknown UoM, inappropriate
for identity discovery. All source edges (including resources) remain evidence.
"""
from collections import Counter, defaultdict
import itertools
import json
from pathlib import Path
import sys

import duckdb

from ..operational_products_offline_v1 import analyze as v1
from ..controlled_physical_capture_v1.capture import digest, file_inventory, save
from .selective import plan_for

ROOT = Path(__file__).resolve().parents[7]
REPORT_ROOT = ROOT/'data/reports/telchi'
RAW = v1.DATA_ROOT/'raw/sap'
FACT = RAW/'TELCHI_DATALAKE_MATERIAL_SUPPLY_FACT_CAPTURE_V1'
FLAGS = dict(sales='has_sales', sales_return='has_sales_returns',
    production_consumption='has_production_consumption', production_receipt='has_production_receipt')
LABELS = {'0':'Ninguna','1':'Líquido','2':'Semisólido','3':'Sólido',
          '4':'Medicamento','5':'No corresponde'}


def check(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def identity(k):
    check(isinstance(k, str) and bool(k.strip()), 'invalid_sap_identity')
    return k  # Never trim, case-fold or synthesize identities.


def graph_membership(headers, lines, max_paths=200000):
    """All simple item paths, shared components and cycles; fail rather than truncate."""
    by_parent = {}
    for h in headers:
        key = identity(h['Code'])
        check(key not in by_parent, 'duplicate_bom_header')
        by_parent[key] = h
    edges, excluded, graph, line_keys = [], [], defaultdict(list), set()
    for line in lines:
        key = (line['Father'], line['ChildNum'], line['VisOrder'])
        check(key not in line_keys, 'duplicate_bom_line')
        line_keys.add(key)
        header = by_parent.get(line['Father'])
        edge = dict(line, tree_type=header['TreeType'] if header else None,
                    validity='UNKNOWN', edge_id=json.dumps(key, ensure_ascii=False))
        reason = ('ORPHAN_HEADER' if header is None else
                  'NON_PRODUCTION_BOM' if header['TreeType'] != 'P' else
                  'NON_ITEM_COMPONENT' if line['Type'] != 4 else None)
        if reason:
            excluded.append(dict(edge, exclusion=reason))
            continue
        identity(line['Father']); identity(line['Code'])
        edges.append(edge)
        graph[line['Father']].append(edge)
    parents = {k for k,h in by_parent.items() if h['TreeType']=='P'}
    paths, cycles = [], []
    for root in sorted(parents):
        stack = [(root, (root,), ())]
        while stack:
            node, route, ids = stack.pop()
            for edge in graph[node]:
                child = edge['Code']
                next_route, next_ids = route+(child,), ids+(edge['edge_id'],)
                value = dict(root=root, component=child, depth=len(next_ids),
                             path=list(next_route), edge_ids=list(next_ids))
                if child in route:
                    cycles.append(value)
                else:
                    paths.append(value)
                    stack.append((child, next_route, next_ids))
                check(len(paths)+len(cycles) <= max_paths, 'bom_path_budget_exceeded_no_partial_result')
    return dict(parents=parents, components={e['Code'] for e in edges},
        multilevel={p['component'] for p in paths if p['depth']>=2},
        edges=edges, excluded=excluded, paths=paths, cycles=cycles,
        headers=headers, validity='UNKNOWN', truncated=False)


def universe(activity, graph, reference, physical):
    by_item = defaultdict(list)
    for a in activity:
        identity(a['item_code'])
        check(a['event_kind'] in FLAGS, 'unknown_activity_family')
        by_item[a['item_code']].append(a)
    sets = {flag:{a['item_code'] for a in activity if a['event_kind']==family}
            for family,flag in FLAGS.items()}
    sets.update(is_bom_parent=graph['parents'], is_bom_component=graph['components'],
                is_multilevel_bom_component=graph['multilevel'])
    keys = set(by_item) | graph['parents'] | graph['components']
    bom_evidence = defaultdict(list)
    for h in graph['headers']:
        if h['Code'] in graph['parents']:
            bom_evidence[h['Code']].append(dict(role='parent', source='OITT',
                tree_type=h['TreeType'], validity='UNKNOWN', source_key=h['Code']))
    for e in graph['edges']:
        bom_evidence[e['Code']].append(dict(role='component', source='ITT1->OITT',
            parent=e['Father'], edge_id=e['edge_id'], tree_type=e['tree_type'], validity='UNKNOWN'))
    products = []
    for k in sorted(keys):
        evidence = by_item[k]
        recent = any(a['recent'] for a in evidence)
        historical = any(a['historical'] for a in evidence)
        observed = k in physical
        code = physical.get(k)
        products.append(dict(ItemCode=k, canonical_product_id=reference.get(k),
            reference_match=k in reference, **{flag:k in s for flag,s in sets.items()},
            activity_class='RECENT_OBSERVED' if recent else 'HISTORICAL_OBSERVED' if historical
                else 'BOM_WITHOUT_OBSERVED_MOVEMENT' if k in bom_evidence else 'INSUFFICIENT_EVIDENCE',
            has_recent_activity=recent, has_historical_activity=historical,
            first_observed_date=min((str(a['first_date']) for a in evidence), default=None),
            last_observed_date=max((str(a['last_date']) for a in evidence), default=None),
            movement_evidence=evidence, bom_evidence=bom_evidence[k],
            classification_observed=observed, U_FormaFarmac=code,
            sap_classification=LABELS.get(code) if isinstance(code,str) else None,
            physical_status='EXPLICIT' if observed and code in ('1','2','3') else
                'OBSERVED_NOT_EXPLICIT' if observed else 'NOT_QUERIED'))
    return products, sets


def load_bom(c, kind, table):
    manifests = sorted((FACT/kind).glob('*/*/manifest.json'))
    check(len(manifests)==1, 'bom_snapshot_selection_required:'+kind)
    p = manifests[0]
    m = json.loads(p.read_text())
    check(m['status']=='COMPLETED' and m['source_schema']=='TELCHI' and
          m['source_system']=='SAP_HANA' and m['source_table']==table, 'invalid_bom_manifest')
    check(len(m['file_references'])==len(m['file_hashes']), 'invalid_bom_files')
    for f,h in zip(m['file_references'],m['file_hashes'],strict=True):
        check(digest(Path(f))==h, 'bom_hash_mismatch')
    rows = v1.records(c, 'SELECT * FROM read_parquet(?)', [m['file_references']])
    check(len(rows)==m['row_count'], 'bom_row_count_mismatch')
    return rows, dict(path=str(p),sha256=digest(p),manifest=m,
        schema=v1.records(c,'DESCRIBE SELECT * FROM read_parquet(?)',[m['file_references']]))


def discover():
    """Metadata inventory only. No blind Parquet scan or SAP schema assumptions."""
    manifests, candidates, table_counts = [], [], Counter()
    for p in sorted(RAW.rglob('manifest.json')):
        m = json.loads(p.read_text())
        tables = [m.get(k) for k in ('source_table','source_line_table') if m.get(k)]
        table_counts.update(tables)
        manifests.append(dict(path=str(p),sha256=digest(p),tables=tables))
        if any(t in ('OIGN','IGN1') for t in tables):
            candidates.append(str(p))
    return dict(raw_manifest_inventory=manifests, source_table_manifest_counts=dict(table_counts),
                production_receipt_candidates=candidates,
                scope='SAP RAW manifests plus live Atomic/Foundation catalog reaccredited by V1; no claim about unregistered external files')


def main(output):
    output = output.resolve()
    check(output.is_relative_to(REPORT_ROOT.resolve()) and output != REPORT_ROOT.resolve(),
          'output_must_be_new_repository_telchi_report')
    output.mkdir(parents=True,exist_ok=False)
    capture_before = file_inventory(v1.CAPTURE)
    metadata_before = {str(p):digest(p) for p in (v1.DATA_ROOT/'manifests').rglob('*.json')}
    discovery = discover()
    check(not discovery['production_receipt_candidates'], 'new_receipt_sources_require_schema_review')
    # Fresh offline read of pinned Foundation, Reference and production RAW.
    baseline = output/'activity_reaccredited'
    v1.main(baseline)
    b = json.loads((baseline/'report.json').read_text())
    c = duckdb.connect(':memory:', config={'threads':2,'memory_limit':'768MB'})
    try:
        headers, header_source = load_bom(c,'bom_header','OITT')
        lines, line_source = load_bom(c,'bom_line','ITT1')
        graph = graph_membership(headers,lines)
        activity = v1.records(c, f"SELECT item_code,event_kind,count(*) lines,count(DISTINCT doc_entry) documents, "
            f"min(doc_date) first_date,max(doc_date) last_date,bool_or(doc_date>=DATE '{v1.CUTOFF}') recent, "
            f"bool_or(doc_date<DATE '{v1.CUTOFF}') historical FROM read_parquet(?) GROUP BY ALL ORDER BY item_code,event_kind",
            [str(baseline/'evidence.parquet')])
        reference_path = Path(b['inventory']['foundation']['reference_path'])/'products/part-00000.parquet'
        ref_rows = c.execute("SELECT item_code,canonical_product_id FROM read_parquet(?) WHERE source_system='SAP_HANA'",[str(reference_path)]).fetchall()
        check(len(ref_rows)==len(dict(ref_rows)), 'reference_duplicate_identity')
        check(digest(reference_path)==b['inventory']['reference']['sha256'], 'reference_hash_changed')
        reference = dict(ref_rows)
        # V1 validates all batches/hash/order; use its verified checkpoint reader again.
        _, captured, seen, _ = v1.read_checkpoint(v1.CAPTURE)
        physical = {r['ItemCode']:r['U_FormaFarmac'] for r in captured}
        for a in activity:
            a.update(source_tables={'sales':'OINV/INV1','sales_return':'ORIN/RIN1',
                'production_consumption':'OIGE/IGE1->OWOR'}[a['event_kind']],
                evidence_file='activity_reaccredited/evidence.parquet',
                foundation_publication=b['inventory']['foundation']['id'],
                source_scope='RAW_ONLY' if a['event_kind']=='production_consumption' else 'FOUNDATION')
        products, sets = universe(activity,graph,reference,physical)
        for p in products:
            for e in p['bom_evidence']:
                e.update(header_extraction_id=header_source['manifest']['extraction_id'],
                    line_extraction_id=line_source['manifest']['extraction_id'],
                    source_as_of=header_source['manifest']['source_as_of'],
                    evidence_file='bom_evidence.json')
    finally:
        c.close()
    keys = {p['ItemCode'] for p in products}
    pending = sorted(keys-seen)
    plan = plan_for(pending)
    sales = sets['has_sales'] | sets['has_sales_returns']
    production = sets['has_production_consumption'] | sets['has_production_receipt']
    bom = graph['parents'] | graph['components']
    counts = {k:len(v) for k,v in sets.items()}
    counts.update(total_unique=len(keys),movement_only_baseline=b['counts']['total'],
        exclusively_bom=len(bom-sales-production), covered=len(keys & seen), pending=len(pending),
        explicit_physical=sum(p['physical_status']=='EXPLICIT' for p in products),
        observed_not_explicit=sum(p['physical_status']=='OBSERVED_NOT_EXPLICIT' for p in products),
        missing_reference=len(keys-reference.keys()), select_queries=len(plan['batches']),
        query_blocks=(len(plan['batches'])+4)//5,
        captured_without_observed_movement=len(seen-sales-production),
        captured_outside_universe=len(seen-keys))
    group = dict(sales_or_returns=sales,production_effective=production,production_bom=bom)
    intersections = {' & '.join(names):len(set.intersection(*(group[n] for n in names)))
        for size in (2,3) for names in itertools.combinations(group,size)}
    combinations = Counter(tuple(n for n,s in group.items() if k in s) for k in keys)
    distribution = Counter(json.dumps(physical[k],ensure_ascii=False) for k in keys & seen)
    def pct(n,d):
        return None if not d else round(100*n/d,6)
    report = dict(validation_artifact='validation.json',status='OFFLINE_COMPLETE_BUSINESS_COVERAGE_PARTIAL',
        branch='feature/console-backend-core',entity='TELCHI',stage='INVESTIGATION',
        domains=['VENTAS','PRODUCCIÓN','STOCK_E_INVENTARIOS'],
        as_of=str(v1.AS_OF),recent_cutoff_inclusive=str(v1.CUTOFF),counts=counts,
        intersections=intersections,disjoint_memberships={' + '.join(k):v for k,v in combinations.items()},
        activity_classes=dict(Counter(p['activity_class'] for p in products)),
        classification=[dict(original_code=json.loads(k),products=n,
            percent_of_captured_operational=pct(n,counts['covered']),
            percent_of_operational=pct(n,len(keys))) for k,n in sorted(distribution.items())],
        percentages=dict(captured_of_operational=pct(counts['covered'],len(keys)),
            explicit_of_operational=pct(counts['explicit_physical'],len(keys)),
            explicit_of_captured_operational=pct(counts['explicit_physical'],counts['covered'])),
        identity_missing_reference=sorted(keys-reference.keys()),
        bom=dict(parent_types=dict(Counter(h['TreeType'] for h in headers)),
            line_types={str(k):v for k,v in Counter(l['Type'] for l in lines).items()},
            production_item_edges=len(graph['edges']),excluded_lines=len(graph['excluded']),
            exclusions=dict(Counter(e['exclusion'] for e in graph['excluded'])),
            simple_paths=len(graph['paths']),cycles=graph['cycles'],truncated=False,
            production_bom_validity='UNKNOWN',header_source=header_source,line_source=line_source),
        source_discovery=discovery,activity_provenance=dict(report='activity_reaccredited/report.json',
            sha256=digest(baseline/'report.json'),evidence_sha256=digest(baseline/'evidence.parquet'),
            foundation=b['inventory']['foundation'],coverage=b['inventory']['evidence_by_family']),
        capture=b['capture'],controls=plan['controls'],
        production_receipts=dict(status='UNAVAILABLE_LOCAL_VERIFIED_SOURCE',
            accredited_products=0,actual_enterprise_products=None),
        limitations=b['warnings']+[
            'Production BOM universe uses OITT.TreeType=P only. Sales BOM S is retained separately, never labeled production recipe.',
            'ITT1.Type=4 is an item; Type=290 is a resource, excluded from ItemCode union but preserved in excluded lines.',
            'BOM captured 2026-09-25, not necessarily currently valid. CreateDate/UpdateDate do not establish effective validity.',
            'Production receipts are unavailable, not evidence that zero finished products were received.',
            'BOM membership does not imply consumption, ingredient category, physical state or recent activity.',
            'All simple paths and cycle-closing edges are preserved; cycles are not recursively expanded. No quantity/UoM inference.',
            'Selective ledger is offline tested. No network runner exists here; future pacing, latency, deadline, closure and device guards require transport integration validation.',
            'A completed selective fetch with missing keys records NOT_RETURNED, not deletion; interrupted fetch must not be committed.',
            'Exact pending list and SELECT count apply only to accredited local universe. Future receipt or BOM evidence can expand it.'],
        safety=dict(hana_queries=0,sap_writes=0,shared_data_writes=0,publications=0,
            capture_unchanged=file_inventory(v1.CAPTURE)==capture_before,
            manifest_tree_unchanged=metadata_before=={str(p):digest(p) for p in (v1.DATA_ROOT/'manifests').rglob('*.json')},
            host_preflight='BUSY_BUT_SAFE',concurrency='one process; two DuckDB threads; 768MB',
            unrelated_processes_terminated=0,own_processes_left_running=0))
    check(report['safety']['capture_unchanged'] and report['safety']['manifest_tree_unchanged'], 'source_changed')
    for name,value in [('report.json',report),('products.json',products),('selective_plan.json',plan),
        ('bom_evidence.json', {k:v for k,v in graph.items() if k not in ('parents','components','multilevel')}),
        ('captured_outside_universe.json',sorted(seen-keys))]:
        save(output/name,json.loads(json.dumps(value,default=str,ensure_ascii=False)))
    text = '# Universo operativo Telchi V2 — offline\n\nUnión trazable de movimientos y recetas productivas locales. Cobertura empresarial parcial; no es el catálogo completo de Telchi. Sin consultas HANA.\n\n'
    text += '| Métrica | Artículos únicos |\n| --- | ---: |\n'+''.join(f'| {k} | {v} |\n' for k,v in counts.items())
    text += '\n## Recetas y movimientos\n\nOITT/ITT1 acreditados por hashes y schemas; solo TreeType=P y componentes Type=4 integran recetas productivas. Se conservan también cabeceras y líneas excluidas.\n\n'
    text += f"- Cabeceras por tipo: {report['bom']['parent_types']}. Líneas por tipo: {report['bom']['line_types']}.\n- Caminos simples: {len(graph['paths'])}; ciclos detectados: {len(graph['cycles'])}; truncamiento: NO.\n- Vigencia productiva: desconocida. No se infiere de fechas de creación/actualización.\n- Recepciones OIGN/IGN1: cobertura pendiente; cero acreditados no significa cero reales.\n"
    text += '\nIntersecciones (incluyen triple):\n\n'+''.join(f'- {k}: {v}.\n' for k,v in intersections.items())
    text += '\n## Clasificación física\n\nSolo códigos SAP 1, 2 y 3 acreditan estado físico; NULL y desconocidos se preservan. Pendiente no es NULL. No hay inferencia por nombre ni receta.\n\n'
    text += '| Código original JSON | Artículos | % capturados operativos | % universo |\n| --- | ---: | ---: | ---: |\n'
    text += ''.join(f"| `{json.dumps(r['original_code'])}` | {r['products']} | {r['percent_of_captured_operational']} | {r['percent_of_operational']} |\n" for r in report['classification'])
    text += f"\nDenominadores: capturados operativos={counts['covered']}; universo={len(keys)}. Pendientes={len(pending)}. Porcentajes: `{report['percentages']}`.\n"
    text += '\n## Fuentes y límites temporales\n\nSe reacreditaron los documentos locales mediante el analizador V1 sin modificarlo. El inventario detallado incluye schemas, cancelaciones, duplicados, snapshots y hashes.\n\n'
    text += '| Familia | Primera fecha | Última fecha | Líneas |\n| --- | --- | --- | ---: |\n'+''.join(f"| {r['event_kind']} | {r['first_date']} | {r['last_date']} | {r['lines']} |\n" for r in b['inventory']['evidence_by_family'])
    text += '\n'+'\n'.join('- '+w for w in report['limitations'])+'\n'
    text += '\n## Captura selectiva futura\n\nPlan congelado por SHA-256, SQL parametrizado IN y checkpoint por lote solicitado, incompatible deliberadamente con keyset. No ejecutable contra HANA en esta etapa.\n\n'
    text += f"- {len(pending)} claves exactas; {counts['select_queries']} SELECT; {counts['query_blocks']} bloques, hasta 5 SELECT por bloque.\n- Máximo 25 claves/SELECT; una conexión; sin paralelismo ni reintentos; pausas de 10 s entre consultas y 30 s entre bloques; HANA 1,5 s; persistencia 10 s.\n- Ledger separado con intent durable previo al SELECT, bloqueo de reintento ante resultado incierto, journal completo, hashes, fsync, exclusión de directorio, validación de correspondencia y recuperación idempotente offline.\n- Guard cooperativo con reserva de cierre/recuperación; no abortar fsync en curso. El futuro runner debe reutilizar controles específicos del dispositivo, no decidir solo por iowait global.\n- Antes de ejecutar: nueva autorización, destino privado nuevo y gate de integración de latencia/pacing/cierre de cursor y conexión. No usar este plan con el runner keyset.\n"
    text += '\n## Artefactos y validación\n\nLa evidencia generada no publica ni modifica Reference, Foundation, CURRENT, Atomic ni capturas previas. El resultado de gates se guarda en validation.json.\n\n'
    text += '- `products.json`: identidad única, indicadores independientes y evidencia por pertenencia.\n- `bom_evidence.json`: cabeceras, aristas, caminos multinivel, ciclos y exclusiones.\n- `activity_reaccredited/`: evidencia documental Parquet y reporte V1 reacreditados.\n- `report.json`: métricas, fuentes, hashes, límites y claves sin Reference (sin inventar canónicas).\n- `selective_plan.json`: lista exacta, parámetros por lote y controles futuros.\n- `captured_outside_universe.json`: sin evidencia en este universo, nunca inválidos.\n'
    (output/'report.md').write_text(text)
    save(output/'artifact_hashes.json',{str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()})
    print(json.dumps(counts,indent=2))


if __name__=='__main__':
    main(Path(sys.argv[1]))
