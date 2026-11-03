"""Evaluate captured independent/HTTP evidence and emit the requested DEV reports."""
import argparse
import hashlib
import json
from pathlib import Path


def run(out):
    ref=json.loads((out/'foundation_reference.json').read_text())
    http=json.loads((out/'business_http_final/runtime_http_results.json').read_text())
    security=json.loads((out/'security_http_final/security_restart_results.json').read_text())
    authorization=json.loads((out/'effective_authorization.json').read_text())
    cases={s['id']:s['turns'] for s in http['scenarios']}
    from modules.telchi.assistant.capabilities import SalesCapabilities, format_result
    comparisons=[]
    replay=[]
    for scenario, turns in cases.items():
        for turn in turns:
            assert turn['http_ok'] and turn['committed'] is True
            assert turn['classification'] != 'ERROR', (scenario,turn['user_text'])
            result=(turn['audit'] or {}).get('execution_result')
            if result:
                assert SalesCapabilities().availability(turn['audit']['validated_state']).allowed
                assert format_result(result)==turn['response_text']
                replay.append(dict(scenario=scenario,current_registry_allowed=True,current_response_identical=True))
            if result and result['capability']=='sales.by_products.v1':
                found=[c for c in ref['cases'] if c['options']==result['parameters']]
                assert len(found)==1,(scenario,result['parameters'])
                independent=found[0]
                fields=('doc_date','doc_entry','line_num','item_code','quantity','doc_num')
                assert [[r[k] for k in fields] for r in result['rows']]==[[r[k] for k in fields] for r in independent['independent_expected']]
                assert {r['item_code']:r['line_count'] for r in result['product_summary']}==independent['independent_counts']
                comparisons.append(dict(scenario=scenario,parameters=result['parameters'],parity=True,rows=len(result['rows'])))
    assert cases['P04'][1]['classification']=='NEEDS_CLARIFICATION'
    assert cases['P04'][2]['audit']['confirmed_state']['selected_item_codes']==['L03658']
    assert cases['P08'][0]['audit']['execution_result']['rows']==[]
    assert cases['P09'][0]['audit']['execution_result']['selection_required'] is True
    assert cases['P16'][1]['classification']=='DIRECT_UNAVAILABLE'
    assert 'unidad física' in cases['P16'][1]['response_text']
    assert cases['P17'][0]['audit']['execution_result']['rows']==[]
    assert authorization['pilot']['authorized'] and not authorization['admin']['authorized']
    assert all(security['own_servers_reaped']) and http['server']['pid_reaped']
    (out/'http_reference_comparison.json').write_text(json.dumps(comparisons,indent=2)+'\n')
    (out/'current_contract_replay.json').write_text(json.dumps(replay,indent=2)+'\n')
    def document(name,title,body):
        (out/name).write_text('# '+title+'\n\n'+body.strip()+'\n',encoding='utf-8')
    binding='Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, CURRENT efectivo confirmado; solo DEV y lectura. Sin SAP, modificaciones canónicas, reingestión, deploy ni cambio de modelo.'
    document('PRODUCT_CATALOG_CONTRACT.md','Product catalog contract',binding+'''

Catálogo: Reference products sellado por Foundation. Scope de esta operación: `SAP_HANA` (compañía SAP TELCHI); no mezcla Legacy ni resuelve todos los namespaces.

Clave natural: `item_code = source_native_id = _source_native_key`. `canonical_product_id` es derivado y no participa del JOIN comercial. Censo: 16.934 productos SAP únicos; cero duplicados. Fuente de nombre: sap_item_name, product_name, canonical_name, en ese orden.

Unidad disponible: sales_uom_id/inventory_uom_id de catálogo. No existe relación publicada aquí que permita presentar una etiqueta física desde esos IDs; no se deriva ni inventa. Estado: active/status/SellItem. Presentación: descripción original, sin alias ni conversión física.

Autoridad de procedencia: productores `modules/telchi/datalake/reference_update.py` (OITM_SQL y claves naturales), `create_initial.py` (_sales_candidate: ItemCode → item_code sin alteración) y `source_coverage.py` (TELCHI OINV/INV1). La equivalencia se limita a esta compañía SAP y publicación, no a fuentes homónimas.

Evidencia: [censo y schemas](foundation_reference.json).''')
    document('ITEMCODE_SALES_RELATION.md','ItemCode sales relation',binding+'''

Reference SAP_HANA y Atomic SAP_B1_HANA son etiquetas de productores de la misma compañía TELCHI. OITM.ItemCode e INV1.ItemCode conservan la misma clave natural; no son canonical_product_id. Se filtra Reference al único namespace SAP de esa compañía y las líneas a su productor INV1, luego se une por ItemCode exacto. No se transforma ningún ID ni se crea crosswalk.

715.046 líneas: 715.045 con relación, una con ItemCode nulo (excluida); 6.581 ItemCodes no nulos distintos, todos presentes en catálogo. Cero productos no nulos de ventas ausentes del catálogo. El JOIN no multiplica filas porque el catálogo es único por clave dentro de SAP_HANA.

Grano línea: (source_system, DocEntry, LineNum); cabecera: (source_system, DocEntry). Censos iniciales sin duplicados; controles runtime por productos y cabeceras. Para las coincidencias de Calenta, sin líneas huérfanas ni multiplicación. El control rechaza vínculos huérfanos antes de publicar un vacío.

Evidencia: [referencia independiente](foundation_reference.json). No se acepta el JOIN solo porque encuentre algunas filas. La brecha de aliases/brand/canonical namespaces histórica permanece fuera de esta relación natural acreditada.''')
    primary=[r for r in ref['catalog']['rows'] if r['match_rank']==1]
    by_code={r['item_code']:r for r in ref['per_product']}
    table='| ItemCode | Descripción original | Unidad catálogo (ID) | Estado / SellItem | Líneas activas publicadas |\n| --- | --- | --- | --- | --- |\n'
    for p in primary:
        table+=f"| {p['item_code']} | {p['description']} | {p['catalog_sales_uom_id'] or 'No publicada'} | {p['status']} / {p['sell_item']} | {by_code[p['item_code']]['active_line_count']} |\n"
    document('CALENTA_REAL_RESULTS.md','Calenta real results',binding+f'''

Búsqueda normalizada con acentos: {len(primary)} coincidencias de palabra Calenta; nueve productos SellItem=Y se incluyen inicialmente para ventas, incluso inactivos históricos. Insumos/etiquetas SellItem=N se muestran en discovery pero requieren selección explícita. El calentador G00082 es una coincidencia parcial de menor rango y no se incluye.

{table}
La presentación es la descripción original de cada fila, no un alias creado. La búsqueda histórica sin acentos omitía productos CALENTÁ; su tabla de ocho SKUs no era un catálogo exhaustivo.

Últimas ventas verificadas: 23/09/2026; primera línea del orden: factura DocEntry 11532450, línea 2, L02823, cantidad documental 1. Los documentos y cantidades restantes se conservan en [referencia](foundation_reference.json) y [HTTP final](business_http_final/runtime_http_results.json).

Sin líneas publicadas no significa venta cero universal. El resumen cuenta todas las líneas activas en el alcance consultado; la lista temporal está limitada a diez. Ningún vínculo de estos IDs requiere crosswalk adicional. No se suman envases, kg ni UoM desconocidas.''')
    document('PRODUCT_SEARCH_CONTRACT.md','Product search contract',binding+'''

Operación `products.search`, permiso `telchi.products.search.read.v1`. Texto 1..120 caracteres normalizados, entrada cruda ≤240; rechaza controles. Límite 1..20. Mayúsculas, acentos, espacios redundantes y coincidencias parciales/código; nombres originales preservados.

SQL parametrizado con contains, no patrones SQL interpolados. Ranking estable: código exacto, palabra/frase completa, substring; desempate por ItemCode. Limit+1 detecta truncamiento. No elige arbitrariamente ante exceso o múltiples matches solo parciales.

Assistant consulta hasta veinte opciones y conserva contexto verificado. Selección automática de ventas: mejor rango, SellItem=Y (código exacto permite consultar un insumo explícito); los IDs seleccionados pertenecen exclusivamente al resultado real. Una búsqueda vacía informa catálogo/alcance sin inventar alternativas.

Tiempo máximo por worker 30 s; dos threads, 512 MB, temp sin spill, conexión read-only y binding exacto. Evidencia: product_sales_query.py, pruebas focalizadas, HTTP P01/P07/P08/P09.''')
    document('SALES_BY_PRODUCTS_CONTRACT.md','Sales by products contract',binding+'''

Operación `sales.by_products`, permiso `telchi.sales.by_products.read.v1`; el handler exige además el permiso de búsqueda. Entrada: conjunto único de 1..20 ItemCodes verificados, namespace SAP_HANA, período opcional completo (inicio/fin exclusivo, hasta 366 días), límite 1..50.

No recibe texto de nombre para filtrar ventas. JOIN línea/cabecera por source_system y DocEntry; filtro comercial por IDs exactos. Política de últimas ventas: OINV activas CANCELED=N, sin NC; no es venta neta. Orden DocDate, DocEntry y LineNum descendentes. No impone último mes.

Resultado: fecha, tipo OINV, DocEntry/DocNum, número de línea, ItemCode, descripción original, Quantity documental y UoM de catálogo como metadata separada. Grano invoice_line, nunca factura completa. Varias líneas del mismo producto siguen siendo líneas distintas, no documentos duplicados.

Resumen por ItemCode: conteo de líneas activas y primera/última fecha para todo el período consultado, independiente del límite temporal. No agrega cantidades físicas ni importes. Un vínculo huérfano/duplicado se rechaza; un vacío correctamente unido no certifica ausencia fuera de cobertura.''')
    document('LINE_AMOUNT_SEMANTICS.md','Line amount semantics',binding+'''

Estado **PARTIAL**: importes de producto no acreditados. LineTotal existe en Atomic, pero impuestos, descuentos de cabecera, moneda/signo y asignación de NC no tienen aquí contrato neto aprobado por producto. El servicio no expone LineTotal como importe acreditado y nunca asigna DocTotal a cada línea.

DocTotal mensual de cabecera se conserva sin cambio: mayo neto Bs 8.552.079,19; junio Bs 9.763.493,67, derivados de Foundation. Estos valores son controles de regresión, no respuestas hardcodeadas.

Quantity existe por línea. UoM/factor físico de línea no está publicado en sales_line; sales_uom_id de catálogo no acredita esa unidad. Se entregan cantidades documentales originales sin totalizar cantidades físicas, con explicación explícita. Solicitudes de importes/cantidades reciben la parte verificable, no una negativa total.

Para ventas netas por producto se necesita un contrato de línea y NC separado; no se promueve semántica por analogía con cabeceras.''')
    document('RBAC_ACTIVATION.md','RBAC activation',binding+'''

Activación realizada con el CLI administrativo existente `modules.telchi.provisioning.live_cli --product-activation`, backup recuperable owner-only en PRIVATE_ROOT, hashes revisados, destino local PostgreSQL 18/team360 y transacción SERIALIZABLE.

Permisos específicos: telchi.products.search.read.v1 y telchi.sales.by_products.read.v1; roles estrechos asignados a devfull@telchiai.com en telchi_dev. Se validan entitlement/delegación comercial previos y se auditan autorización global, delegación Telchi y grant del incremento. Console resuelve ambos permisos efectivos; no FULL_ACCESS ni cambios a otros tenants.

[Aplicación](activation_apply.json), [idempotencia sin cambios](activation_idempotent.json), [Console efectivo](effective_authorization.json). Se preservaron las cuatro capacidades previas. Identidad administrativa Telchi existente sin estos permisos: resultado Console negativo real; no se la impersonó.

La denegación HTTP P13 usa fixture explícita de permiso faltante sobre el handler real; no certifica autenticación de una segunda identidad externa. No se retiraron permisos al piloto ni se usaron allowlists telefónicas para autorizar negocio.''')
    document('FOUNDATION_SQL_PARITY.md','Foundation SQL parity',binding+f'''

Diecinueve casos SQL/servicio cotejados con lecturas independientes: catálogo completo SAP, líneas por códigos y cabeceras por claves, merge y orden en Python, cantidades Decimal. No se utiliza SQL ni output del servicio para construir las filas esperadas.

Casos: Calenta completo, mayo, cada una de las diecisiete coincidencias de palabra, incluidos vacíos. Se verifican claves naturales, unicidad, cobertura, fechas, orden, cantidades, conteos completos, no duplicación y binding 1408. UoM de línea no existe: no se finge equivalencia física.

{len(comparisons)} resultados HTTP de líneas coinciden con expected independiente y conteos completos. [Referencia](foundation_reference.json), [paridad HTTP](http_reference_comparison.json). Regresiones monetarias de mayo/junio derivadas del contrato previo acreditado; no importe por producto.''')
    http_table='| Caso | Turnos | Resultado final |\n| --- | --- | --- |\n'
    for key, turns in cases.items(): http_table+=f"| {key} | {len(turns)} | {', '.join(t['classification'] for t in turns)} |\n"
    document('BUSINESS_HTTP_RESULTS.md','Business HTTP results',binding+f'''

Luna GPT-5.6 Medium directa, modelo/effort verificados, sin fallback. Batería existente por loopback/auth, handler real y PostgreSQL: 16 escenarios, 25 turnos, cero errores funcionales en la corrida final; HTTP 200 por sí solo no determina éxito.

{http_table}
P03 está en el segundo turno P02; P04 pregunta solo cuando la selección es ambigua y luego consulta L03658 verificado. P05/P06 responden parcialmente con líneas/cantidades y la limitación monetaria, no total global. P09 conserva opciones y pide precisión. P16 rechaza agregación física incompatible. P17 vacío correcto.

P13/P14/P15/P18 están en [HTTP security/restart](security_http_final/security_restart_results.json); P18 prueba persistencia real PG y reinicio, con intérprete fixture explícito. [Respuestas completas finales](business_http_final/runtime_http_results.json).

El último guard impide sustituir productos contextualizados por totales globales. Su regresión es focalizada; la evidencia HTTP se reutiliza porque todos sus estados siguen autorizados por el registry actual y el formatter reproduce las mismas respuestas, ver current_contract_replay.json. No se iniciaron nuevos servidores bajo la presión posterior del host.

La primera corrida se conserva: tuvo rechazos por /pending emitido por el modelo y refinamiento de texto con IDs verificados. Se corrigió la continuidad de selección en State Engine y se aclaró la gramática del intérprete; ningún rechazo se reparó para ejecutar, ni se cambió SQL/semántica para ocultarlo. Corridas corregida y final sin esos fallos.''')
    document('SECURITY_REGRESSION.md','Security regression',binding+'''

Guard obligatorio committed is True: P14 propuesta inválida tras un resultado previo, cero ejecución y estado anterior preservado. P15 ItemCode inventado: rechazo, cero ejecución. product_context no es un path permitido al modelo; selección solo entre resultados reales y validados de la conversación actual.

P13 permiso específico faltante: denegación antes de Foundation; Console real distingue piloto autorizado y administrador sin grants. Permisos efectivos se comprueban en cada turno y por cada operación, no por teléfono. P18 preserva contexto después de reinicio; cambiar período consulta los mismos IDs sin repetir búsqueda.

Pruebas unitarias: texto/códigos/límites/períodos, SQL literal parametrizado, context injection, IDs no encontrados, guard comprometido y no comprometido, catálogo específico/RBAC narrow. La suite focalizada final incluye 200 PASS. Nunca se suman unidades desconocidas, DocTotal por producto ni NC silenciosas.

Host compartido: SAFE inicialmente, BUSY_BUT_SAFE al final; ejecución secuencial, dos threads DuckDB y 512 MB, un servidor temporal a la vez, sin browsers. Todos los servidores propios se reapearon; cero procesos ajenos terminados. Milvus/LiteLLM no son dependencias de esta ruta directa. Sin abortos ambientales; el fallo inicial del launcher fixture fue un defecto del harness corregido, no ambiental.''')
    names=['TELCHI_PRODUCT_CATALOG_DISCOVERY','TELCHI_PRODUCT_SEARCH','TELCHI_PRODUCT_IDENTITY_CONTRACT',
        'TELCHI_ITEMCODE_SALES_RELATION','TELCHI_CALENTA_PRODUCT_DISCOVERY','TELCHI_CALENTA_SALES_QUERY',
        'TELCHI_SALES_BY_PRODUCTS','TELCHI_PRODUCT_PRESENTATIONS','TELCHI_PRODUCT_LINE_AMOUNT_SEMANTICS',
        'TELCHI_PRODUCT_QUERY_RBAC','TELCHI_PRODUCT_QUERY_SQL_PARITY','TELCHI_PRODUCT_QUERY_HTTP_RUNTIME',
        'TELCHI_PRODUCT_QUERY_CONTEXT','TELCHI_PRODUCT_QUERY_SECURITY','TELCHI_EXISTING_SALES_REGRESSION',
        'TELCHI_PRODUCT_SEARCH_SALES_BY_ITEM_V1']
    gates={n:('PARTIAL' if n in {'TELCHI_PRODUCT_PRESENTATIONS','TELCHI_PRODUCT_LINE_AMOUNT_SEMANTICS','TELCHI_PRODUCT_SEARCH_SALES_BY_ITEM_V1'} else 'PASS') for n in names}
    document('GATES.md','Gates',binding+'''

El flujo funcional Product Search → ItemCode → Sales Query está demostrado por HTTP y SQL independiente. El cierre global se mantiene PARTIAL por falta de UoM/factor físico de línea e importe neto por producto; no se fuerza semántica para conseguir PASS.

```text
'''+ '\n'.join(k+'='+v for k,v in gates.items())+'''
```

Validación: 200 tests focalizados; 19 casos de referencia; 25 turnos empresariales finales; negativos y reinicio HTTP. La denegación HTTP de identidad alternativa usa fixture, mientras los grants negativos Console son reales. Ver informes enlazados para no confundir esas garantías.

Sin commit/push/deploy. HEAD preservado: 09d2ec715a31bb88574d734eacb9f437f008624e. Cambios limitados a Telchi y su evidencia. Próximo paso: acreditar UoM física y contrato monetario de línea/NC, sin alterar Foundation en esta ejecución.''')
    (out/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
    backend=Path(__file__).resolve().parents[5]
    paths=[backend/'modules/telchi/datalake/product_sales_query.py']+list((backend/'modules/telchi/assistant').glob('*.py'))+list((backend/'modules/telchi/provisioning').glob('*product*.py'))
    (out/'reviewed_source_hashes.json').write_text(json.dumps({str(p.relative_to(backend)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},indent=2)+'\n')
    print(json.dumps(gates,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);run(p.parse_args().output)
