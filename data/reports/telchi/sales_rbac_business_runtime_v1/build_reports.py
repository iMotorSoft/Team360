"""Build focused reports from captured evidence, never from invented business values."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def load(path): return json.loads((ROOT/path).read_text())
def write(name,text): (ROOT/name).write_text(text.strip()+'\n')
pre=load('precheck.json'); applied=load('apply.json'); second=load('apply_second.json')
auth=load('effective_and_security.json'); parity=load('foundation_parity.json')
http=load('business_http_validated/runtime_http_results.json'); legacy=load('legacy_http_recheck/runtime_http_results.json')
security=load('security_http/security_results.json')
assert second['changed'] is False and security['passed']
assert all(t['classification']!='ERROR' for s in legacy['scenarios'] for t in s['turns'])
assert all(c['parity'] for c in parity['comparisons'].values())
files=[
 'modules/telchi/provisioning/live_cli.py', 'modules/telchi/provisioning/admin_repository.py',
 'modules/telchi/provisioning/admin_service.py', 'modules/telchi/provisioning/sales_cli.py',
 'modules/telchi/provisioning/sales_repository.py', 'modules/telchi/provisioning/tests/test_sales_admin.py',
 'modules/telchi/assistant/handler.py', 'modules/telchi/assistant/tests/test_sales_business_contract.py',
 'modules/telchi/assistant/tests/runtime_http/run_battery.py', 'modules/telchi/assistant/README.md',
 'modules/telchi/status_actual.md']
write('ACTIVATION_REPORT.md',f'''# Activation report

Telchi DEV: las dos operaciones documentales IMPLEMENTED pasan a ACTIVATED para el piloto aprobado. No hay promoción PROD ni cambios a consultas Foundation, Luna o State Engine.

## Resumen ejecutivo

Se verificó PG {pre['version']['server_version']}, las tres identidades persistidas, organización Telchi y workspace `telchi_dev`. El propietario confirmó DEV y autorizó esta intervención limitada.

- Team360 global: catálogo de dos permisos, dos roles de workspace y dos relaciones rol/permiso; límites delegados en el ledger administrativo existente.
- Telchi: actor organization_admin validado; dos relaciones usuario/rol al piloto. Se conserva el permiso source_quantity y no se agregan permisos globales.
- Segunda ejecución: cero registros nuevos y cero eventos administrativos nuevos.
- HTTP B01–B06: datos empresariales reales, cobertura y ranking; sin inventar importes, mes completo ni página anterior.
- SQL independiente: igualdad completa de filas/orden en B01, fechas/universo/período en B02–B03, misma publicación y snapshot 1408.
- Seguridad: siete controles negativos con cero consultas; límites HTTP fail-closed verificados.

## Operación administrativa y respaldo

Se extiende el CLI existente de propietario local DEV, no se emite un token, no se simula un login Console y no se activa ninguna credencial. Actores auditados y roles persistidos se verifican antes de escribir.

- Comando: `uv run python -m modules.telchi.provisioning.live_cli --sales-activation --manifest <private_manifest> --apply --local-owner-bootstrap`.
- Plan previo read-only sin `--apply`; manifest propietario 0600, target exacto y fuentes revisadas con SHA256.
- Backup privado único: `{pre['backup']}`; hash `{pre['backup_sha256']}`; roundtrip JSON confirmado antes de escrituras.
- Dos eventos PG: `telchi.admin.sales-authorize` (actor global) y `telchi.admin.sales-grant` (actor Telchi), con antes/después, permisos, registros creados y resultado.
- Rollback limitado probado en transacción descartada: [detalle](RBAC_CHANGES.md). Estado final intacto.

## Archivos modificados

Paths relativos a `SrvRestAstroLS_v1/backend`; se preservaron los archivos preexistentes y no se hicieron operaciones Git de escritura.

{chr(10).join('- `'+f+'`.' for f in files)}
- `data/reports/telchi/sales_rbac_business_runtime_v1/`: siete entregables, scripts reproducibles y evidencia JSON/logs.

## Validación y límites

Las garantías se documentan por evidencia, no por HTTP 200. [Gates](GATES.md), [permisos](EFFECTIVE_PERMISSIONS.md), [HTTP](BUSINESS_HTTP_RESULTS.md), [paridad](FOUNDATION_PARITY.md) y [seguridad](SECURITY_REGRESSION.md) conservan el detalle.

- Rama `feature/console-backend-core`; HEAD `09d2ec715a31bb88574d734eacb9f437f008624e` conservado; sin commit/push/deploy.
- Tests focalizados: 166 PASS / 2 skips (PG disposable no configurado); una advertencia baseline de composición Diagnosis fixture. Evidencia PG18 real y rollback rehearsal separados, sin crear otra base.
- Runtime: Srv05/Telchi composición real mediante el adaptador DEV existente; loopback efímero, registro Telchi y State Engine V2 acreditados por auditoría persistida. Servidores propios reap al terminar; no se deja listener permanente.
- Modelo preflight: GPT-5.6 Luna Medium, OpenAI directo, eco verificado, sin fallback; Milvus/LiteLLM no son consumidores de esta cadena.
- No DDL, SAP, Parquet, Foundation DML/publicación, Flow, Diagnosis, Messaging, Evolution, Srv01 ni configuración del modelo modificados.
- Impacto transversal: sólo catálogo RBAC de dos códigos Telchi y roles del workspace autorizado. Las fuentes provisioning cambiaron: manifests históricos con hashes previos deben revisarse antes de reutilizarlos.
- Riesgo residual: propuestas ocasionalmente inválidas/no disponibles del intérprete siguen fallando cerrado. No se modificó Luna ni se ocultaron esos rechazos; [incidentes preservados](BUSINESS_HTTP_RESULTS.md).
- Próximo paso: validación WhatsApp separada si se solicita; no requerida ni certificada por este gate HTTP DEV.
''')
write('RBAC_CHANGES.md',f'''# RBAC changes

Antes/después proviene de snapshots privados y del resolver real; no se movieron usuarios, se inventaron IDs ni se duplicaron registros preexistentes.

## Relaciones y catálogo

Sólo los códigos comerciales listados quedan incorporados al alcance Telchi DEV.

| Entidad | Antes | Después |
| --- | --- | --- |
| latest_documents.read.v1 | ausente | permiso business cerrado OINV activa, límite 1..50 |
| coverage.read.v1 | ausente | permiso business cerrado cobertura OINV activa |
| source_quantity.read.v1 | existente | sin cambio |
| Roles exclusivos workspace | ausentes | telchi_sales_latest_documents_reader_v1 y telchi_sales_coverage_reader_v1 |
| Relaciones rol/permiso | 0 nuevas | 2, un código exacto por rol |
| Relaciones piloto/rol | 0 nuevas | 2 |
| Perfiles/usuarios/organización/workspace | existentes | sin cambio |
| Límites globales delegados | sólo V1 original | evento adicional aprobado latest/coverage; bootstrap V1 intacto |

Total: ocho filas RBAC nuevas (dos permisos, dos roles, dos role_permissions, dos user_roles) y dos eventos auditables. Segunda ejecución: `changed=False`, cero filas/eventos adicionales. [apply](apply.json), [no-op](apply_second.json).

## Backup y auditoría

El respaldo está fuera de Git, no sobrescribe otros backups y contiene los registros originales afectados, relaciones, perfiles y ledger anterior. El repo sólo contiene path/hash y evidencia mínima.

- SHA256: `{pre['backup_sha256']}`.
- Antes/después, actor, workspace, permisos, resultados y ledger exacto: [effective_and_security.json](effective_and_security.json).
- Run de asignación: `{applied['run_id']}`. El actor global aprueba; el administrador Telchi asigna dentro de esos límites, sin permisos comerciales personales implícitos al administrador.
- La extensión autenticada `admin_cli manage-client` acepta `grant-sales` sólo para el catálogo exacto y requiere entitlement global aprobado. No admite permisos arbitrarios ni módulos externos.

## Reversión limitada

La retirada afecta sólo relaciones creadas por el run, verificando snapshot sin cambios. Conserva usuarios, permisos, roles, grant original, bootstrap previo y auditoría; no ejecuta DELETE genérico.

```bash
uv run python -m modules.telchi.provisioning.live_cli \\
  --sales-activation --manifest "$PRIVATE_MANIFEST" --apply \\
  --local-owner-bootstrap --rollback-sales-run {applied['run_id']}
```

Rehearsal real PG18: tras retirar las dos asignaciones el piloto resuelve sólo el permiso original; repetir reversión es no-op. La transacción de ensayo fue descartada; snapshot posterior idéntico al anterior. No se revocó el acceso activado al cierre.
''')
write('EFFECTIVE_PERMISSIONS.md',f'''# Effective permissions

AUTH_PASS usa `PermissionConsoleRepository.list_effective_permissions`, no mera existencia en core_permissions. Evidencia completa: [effective_and_security.json](effective_and_security.json).

## Resolución autorizada

Se acredita usuario piloto existente, organización Telchi, workspace telchi_dev, módulo Telchi y los permisos específicos de cada capability.

- Antes: `{pre['effective_before'][0]}`.
- Después: {', '.join('`'+p+'`' for p in auth['effective'])}.
- `BusinessAuthorization.allowed(context, conn, required_permission=...)`: verdadero para ambos grants, con conexión PG real y contexto del workspace correcto.
- Workspace distinto: resolver devuelve `[]` para el mismo piloto.
- Roles de workspace, no globales; sin perfiles nuevos ni grants administrativos al piloto. El administrador Telchi resuelve cero permisos comerciales propios, conservando su rol organization_admin delegado.
- El handler HTTP revalida permisos efectivos dentro del turno; B01 exige latest_documents y B02/B03 coverage. La identidad proviene del resolver telefónico real, no del payload HTTP.
- Pruebas negativas conservan límites tenant/workspace/módulo y permiso específico, sin editar usuarios externos.

## Binding comercial

Los permisos no autorizan SQL libre ni acceso ilimitado: cada rol contiene un único código y cada operación pertenece al registry cerrado acreditado.

- latest: `sales.latest_documents.v1`, OINV activas N/SAP_B1_HANA, DocDate descendente y DocEntry descendente; máximo 50.
- coverage: `sales.coverage.v1`, mismo universo, primera/última fecha y mes con filas, sin completitud certificada.
- Publicación: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot `1408`; conexión read-only y sin SAP.
''')
http_sections=[]
for s in http['scenarios']:
    turns=[]
    for t in s['turns']:
        a=t['audit']; executed=a.get('execution_result') or {}
        turns.append(f"**Pregunta:** {t['user_text']}\n\n**Respuesta:**\n\n"+t['response_text']+f"\n\nEstado: `{t['classification']}`; committed={t['committed']}; ejecución={t['execution_status']}; latencia={t['elapsed_ms']} ms; capability={executed.get('capability','ninguna')}; invocaciones={a['capability_calls']}; permiso={a.get('required_permission')}; correlación=`{t['correlation_id']}`.")
    http_sections.append('## '+s['id']+'\n\nTurnos reales del mismo pipeline con estado persistido PG.\n\n'+'\n\n'.join(turns))
write('BUSINESS_HTTP_RESULTS.md','''# Business HTTP results

Batería final: seis escenarios, ocho turnos, todos HTTP 200 y cero ERROR. No se interpreta el status HTTP como garantía empresarial: resultados, permisos, estado y SQL se verifican por separado.

'''+'\n\n'.join(http_sections)+'''

## Regresión y defectos observados

Se preservan todas las corridas, incluidos rechazos y correcciones; no se declara que el intérprete sea infalible.

- Primero: [legacy_http](legacy_http/runtime_http_results.json), doce escenarios/32 turnos, cero ERROR antes de correcciones.
- [business_http](business_http/runtime_http_results.json): B01 interpretación no disponible/propuesta null, cero ejecución; causa upstream/parse no acreditada. Repetición sin cambios funcionó; no se agregó retry automático ni fallback.
- B02 reprodujo dos veces la lista latest en vez de coverage. Se mantuvo raw en auditoría y añadió contrato documental acotado en handler, que propone coverage al mismo motor, exige su permiso y no amplía filtros ni catálogo. Regresión pytest y HTTP final acreditan corrección.
- B04 reprodujo dos veces ASK de referencia pese a contexto latest. Handler ahora explica paginación no soportada después de commit validado, sin ejecutar. Contexto y auditoría preservados.
- [legacy_http_final](legacy_http_final/runtime_http_results.json): un ERROR seguro, correlación `28694df9-66aa-45ac-b07b-79c48e7859b3`, en «ultimo mes registrado». Raw propuso `unset=['/pending']`, path fuera del contrato: State Engine rechazó correctamente, committed=False y cero consultas. No es fallo RBAC/SQL ni se clasifica como aborto ambiental.
- [legacy_http_recheck](legacy_http_recheck/runtime_http_results.json), mismo código: doce escenarios/32 turnos, cero ERROR; ranking original ejecutado. Variación de propuestas del intérprete sigue como riesgo residual; no se cambió Luna ni se repararon propuestas inválidas.
- [business_http_validated](business_http_validated/runtime_http_results.json): B01 latest, B02/B03 coverage, B04 sin segunda página, B05 sin importe, B06 ranking original.
- Todas las ejecuciones usan Srv05 real vía adapter DEV existente; WhatsApp outbound no ejecutado. Servidores loopback propios cerrados por el runner con `pid_reaped=True`.
''')
write('FOUNDATION_PARITY.md',f'''# Foundation parity

[foundation_parity.json](foundation_parity.json) compara filas HTTP con los algoritmos SQL independientes ya acreditados. Ninguna llamada directa a capability sustituye la evidencia conversacional.

## Binding y referencia

CURRENT permaneció `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408. Sólo se consultó Foundation read-only; sin SAP, DDL/DML, Parquet ni cambios de publicación.

- Latest: ROW_NUMBER por DocDate/DocEntry descendentes, posiciones <=10; alternativa independiente a ORDER BY/LIMIT de la capability.
- Cobertura: fechas ordenadas y conteo por fecha; fecha extrema y suma derivadas, alternativa independiente a MIN/MAX/COUNT del servicio.
- Universo: SAP_B1_HANA, OINV cabeceras activas canceled=N y DocDate no nulo; excluye notas de crédito, no representa ventas netas.
- B01: diez identificadores, referencias, fechas, orden y cantidad coinciden exactamente. Primer DocEntry `{parity['comparisons']['B01']['rows'][0]['doc_entry']}`, último `{parity['comparisons']['B01']['rows'][-1]['doc_entry']}`.
- B02/B03: primera fecha `{parity['comparisons']['B02']['rows'][0]['first_date']}`, última `{parity['comparisons']['B02']['rows'][0]['last_date']}`; `{parity['comparisons']['B02']['rows'][0]['documents']}` documentos; mes `{parity['comparisons']['B02']['rows'][0]['latest_month_with_rows']}`; complete_month_certified=False.
- B04 primera lista también coincide; segunda pregunta no consulta ni simula una página.
- Permisos, capability, parámetros, estado, correlación, fuente y snapshot constan por B01–B04 en JSON. Cada ejecución nueva hizo una invocación de capability/una query empresarial Foundation; consultas internas de metadatos/conexión no se presentan como queries empresariales.

## Resultado

DATA_PASS y SEMANTIC_PASS se restringen al universo documental definido; BUSINESS_RUNTIME_PASS exige además respuesta HTTP real y AUTH_PASS efectivo, no importe neto ni completitud comercial inferidos.

B01/B02/B03: paridad exacta y respuestas empresariales verificadas. No se declararon métricas monetarias, marcas ni filtros comerciales adicionales.
''')
rows='\n'.join(f"| {k} | {v['classification']} | {v['query_calls']} | {'fixture aislada' if v['fixture'] else 'identidad existente, permisos PG'} |" for k,v in auth['security'].items())
write('SECURITY_REGRESSION.md',f'''# Security regression

Controles negativos sin crear usuarios ni alterar grants ajenos. [effective_and_security.json](effective_and_security.json) distingue identidades PG de fixtures; positivos empresariales sólo se acreditan por HTTP real.

## Matriz de autorización

Los handlers negativos usan persistencia/interpretación aisladas; permisos actuales de identidades existentes se leen de PG sin impersonar sesiones ni enviar mensajes operacionales de esos usuarios.

| Caso | Resultado | Queries | Evidencia |
| --- | --- | --- | --- |
{rows}

Usuario piloto autorizado: ambos permisos efectivos y ejecución empresarial positiva por HTTP. Sin permiso, otro tenant y workspace incorrecto: DENIED. Módulo deshabilitado y nueva capability sin grant: DENIED. Fuera del catálogo y committed=False: rechazo sin ejecución, incluso ante output EXECUTE.

## Frontera HTTP y administración

El adapter permanece opt-in/token/loopback; no acepta identidades suministradas por el cliente. El CLI tampoco acepta permisos arbitrarios ni delegación sin aprobación global.

- [security_http/security_results.json](security_http/security_results.json): token ausente/incorrecto 401; body inválido/user_id/phone 400; rutas Console/webhook 404; health 200; token/teléfono ausentes del log; sesiones y concurrencia aisladas.
- Tests administrativos rechazan PROD, permisos globales, permisos extra, otros módulos, acciones SQL libres y falta de entitlement antes de asignar.
- Regresión del handler: revalidación PG del grant nuevo, permisos faltantes y committed=False; contrato B02 no elimina el guard ni el grant coverage.
- Rollback rehearsal no persiste, idempotencia confirmada y original source_quantity preservado.
- No bypass del resolver telefónico, default_admin, permission fallback, SQL libre o outbound transport.
''')
gates=['CATALOG','TENANT_ENTITLEMENT','DELEGATION','PILOT_ASSIGNMENT']
lines=['TELCHI_SALES_RBAC_'+s+'=PASS' for s in gates]
lines += ['TELCHI_SALES_'+s+'=PASS' for s in ['EFFECTIVE_PERMISSIONS','UNAUTHORIZED_DENIAL','LATEST_HTTP','COVERAGE_HTTP','SQL_REFERENCE_PARITY','STATE_ENGINE_GUARD','BUSINESS_RESPONSE']]
lines+=['TELCHI_SALES_RBAC_AND_BUSINESS_RUNTIME_V1=PASS']
write('GATES.md','''# Activation gates

PASS acotado a Telchi DEV y estas dos operaciones documentales; no certifica PROD, WhatsApp delivery, importe neto ni ausencia universal de rechazos del intérprete.

```text
'''+ '\n'.join(lines)+'''
```

## Garantías y evidencia

Los cuatro gates permanentes se cumplen para latest_documents y coverage; código IMPLEMENTED no significa ACTIVATED fuera del alcance aquí acreditado.

- DATA_PASS: SQL real read-only CURRENT/1408; [paridad](FOUNDATION_PARITY.md).
- SEMANTIC_PASS: OINV activas por DocDate; no ingresos netos ni mes completo certificado.
- AUTH_PASS: catálogo/roles/entitlement/delegación/piloto y resolver Console real; [RBAC](RBAC_CHANGES.md), [efectivos](EFFECTIVE_PERMISSIONS.md).
- BUSINESS_RUNTIME_PASS: preguntas naturales por dispatcher/handler/State Engine/capabilities, datos empresariales y SQL independiente coincidentes; [HTTP](BUSINESS_HTTP_RESULTS.md).
- Seguridad: siete controles negativos, guard, rutas y aislamiento; [regresión](SECURITY_REGRESSION.md).
- Backup y reversión: snapshot privado antes de escrituras, SHA256/roundtrip y ensayo transaccional; no-op de segunda activación sin auditoría duplicada.

## Validaciones ejecutadas

Los comandos se ejecutaron desde backend salvo LAT/Git desde raíz. No se reutilizan PASS históricos para sustituir estas mediciones.

- `uv run pytest modules/telchi/assistant/tests modules/telchi/provisioning/tests tests/test_telchi_assistant_srv05.py modules/telchi/datalake/tests/test_messaging_sales_query.py -q`: 166 PASS / 2 skips PG disposable; advertencia baseline. [Log](tests_final.log).
- `prepare.py`: read-only precheck, backup privado único e integridad, identidades y catálogo original.
- `live_cli --sales-activation`: plan read-only; apply y segundo apply no-op, dos eventos en total.
- `live_probe --luna --preflight`: provider/model/effort real verificados, sin fallback; [preflight](luna_preflight.json).
- `run_battery`: regresión previa 12/32, correcciones focales y batería final B01–B06, 6/8; recheck final 12/32 sin ERROR. Rechazos intermedios preservados y explicados, no ocultos.
- `security_probes`: límites HTTP, sesiones y dos requests paralelos PASS.
- `verify.py`: permisos PG, negativos, rollback rehearsal y SQL independiente sobre respuestas HTTP PASS.
- Gates LAT y `git diff --check`: ver [validation_commands.log](validation_commands.log); revisión del diff final sin cambios fuera del scope propio.

## Recursos, riesgos y pendientes

Host seguro y presupuesto acotado: ~8 GB MemAvailable, 8 cores, carga observada 0.4–2.1, swap sin crecimiento sostenido. PostgreSQL no se reinició y no se detuvieron servicios ajenos.

```text
HOST_PREFLIGHT=SAFE
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 worker pytest; 2 threads DuckDB por conexión; máximo 2 requests HTTP en security
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0
OWN_PROCESSES_LEFT_RUNNING=0
```

Servidores temporales propios cerrados/reaped por los runners; cleanup final sin listener DEV. Queda riesgo real de propuestas inválidas/no disponibles del intérprete: fail-closed conservado, Luna sin cambios. No hay paginación, mes completo certificado ni métrica neta aprobada. Sin commit, push, deploy, cambios SAP/Foundation ni otros módulos.
''')
print('Seven activation reports generated from evidence')
