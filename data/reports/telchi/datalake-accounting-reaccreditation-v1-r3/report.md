# Reacreditación Data Lake V1 y contabilidad

Dictamen **PARTIAL**: V1 preservado y reader real reacreditado; Reference V2 compatible pero no publicada. Las dos consultas contables prioritarias están **BLOCKED_BY_MISSING_PUBLISHED_ACCOUNTING_SOURCES**; no se habilitaron.

## A. Estado Data Lake

Lectura nueva del catálogo PostgreSQL local mediante DuckLake READ_ONLY, sin HANA. Evidencia ejecutable: `local-audit.json`, `access.json`, `manifest.json`, `preservation.json` y consultas con parámetros en `business-checks.json`.

- Rama: `feature/console-backend-core`. `TELCHI_DATALAKE_V1_CLOSED=YES` permanece como cierre canónico; no se repitió ni recreó.
- CURRENT real: `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, mismo al terminar. Manifest completo igual al congelado acreditado anteriormente.
- Snapshot de consumo de facts: **1408**. Snapshot de derivación/Receivables: **1322**. No son intercambiables.
- Reference consumida por el reader canónico: `v2_reference_closure_2088d5885204313a`.
- Pointer Reference independiente: `v2_b19ceecf40d3ba09`. La divergencia histórica **sigue presente**, comprobada de nuevo; no se corrigió ni se usó ese pointer como sustituto de Foundation.
- Candidata `v2_aabf716d342de26794c09797`: construida y compatible. No publicada ni consumida por el reader canónico observado. No se afirma qué hacen todos los procesos externos no inspeccionados.
- El DTO conserva `component_count=5` para el core histórico; el manifest tiene **8 componentes lógicos**. No es pérdida de tres componentes.

| Componente | Publicación vigente |
| --- | --- |
| sales | update_publication_06cba09af83481c325e7aed0688ebace |
| credit_memo | update_publication_d56f2c34733debf3ceed3ff895472dbe |
| oinm | update_publication_fd0cc57d2e5e31c6dfb04dee6bfb2a4c |
| oitw | update_publication_b567d267b6340baf3939083e4c4cea27 |
| reference | v2_reference_closure_2088d5885204313a |
| material_supply | material_supply_2ee04203964a197ab627f839 |
| purchasing | purchasing_4ab178d62c5f5ba27d7180a8 |
| receivables_collections | receivables_collections_633d1fbbfdd87e6665b1aad3 |

Los 13 datasets file-backed de Material Supply/Purchasing conservan SHA-256 y counts declarados, sin diferencias. Schemas leídos de los Parquet reales. Core/Receivables tienen lectura efectiva de snapshot, counts y validación del reader; **no se recalculó un hash integral de todas las filas DuckLake**, ni se certifica integridad criptográfica total por un count.

La prueba de compatibilidad Reference se volvió a ejecutar contra los archivos reales de candidata y Reference publicada, incluyendo crosswalks, identidades, schemas y multiconjuntos de proyecciones. Coincide exactamente con la prueba previa. El fingerprint de contenido volvió a ser `aabf716d342de26794c09797c1e1fe6ff305c267982467242830059641076cc8`.

Candidata: 53.392 productos; 7.958 enriquecidos; 45.434 preservados. Estado físico explícito: 695 LIQUID + 93 SEMISOLID + 490 SOLID = **1.278**. Además: 6.642 UNCLASSIFIED, 37 NOT_PHYSICAL y 1 NOT_APPLICABLE. No confundir enriquecimiento con clasificación física afirmativa. Consolidado hash `819e0b6c…` idéntico; 43 NOT_RETURNED, sin inventar identidades ni interpretar eliminación. Evidencia: `additional-source-validation.json`, `identity-check.json`, `candidate-files.json` y `reference-compatibility.json`.

Recuperación, fallos antes/durante commit, rollback y readers pinned se ejercitaron en stores de prueba aislados. No se ejecutó recovery/rollback sobre CURRENT real. La simulación previa de candidata real sigue referenciada en `reference-v2-foundation-offline-final-r2/report.json`; no equivale a una promoción nueva. Recuperación operacional real ante desastre y lectura criptográfica integral requieren otra acreditación si se necesitan.

## B. Estado empresarial

Los counts observados prueban disponibilidad de filas, no completitud de todos los períodos ni equivalencia entre dominios. La fecha global más reciente no vuelve actuales todos los componentes.

| Frente | Evidencia publicada observada | Cobertura y límites |
| --- | --- | --- |
| Ventas | 330.443 cabeceras OINV; 715.046 líneas; claves documentales y de línea sin duplicados | Fechas mín/máx 31/03/2022–24/09/2026; no prueba histórico continuo. Fechas, clientes facturados, productos, vendedores e importes fuente disponibles. Septiembre no es mes completo. Moneda/base y NC se tratan separadas. |
| Notas de crédito | 2.215 cabeceras, 9.429 líneas | 01/01/2026–23/09/2026. No extrapolar a cobertura histórica de OINV ni conciliación GL. |
| Productos | 53.392 Reference; identidades/crosswalks preservados | Clasificación física candidata no consumida. Clasificación comercial tiene UNKNOWN y vigencia propia; no convertir producto operativo en terminado por estar activo. |
| Producción | 791 consumos derivados; 1.086 demandas equivalentes; 11.445 perfiles de lead time; 1.188 estados supply; 18.717 pipeline | Integridad de los archivos sellados reacreditada. No prueba Libro de órdenes completo ni recepción de fabricación acreditada por cada orden. Recetas/órdenes/recepciones no son un componente Foundation autónomo aquí; no presentar capacidades raw investigativas como reader publicado. |
| Inventario | 1.576.871 movimientos OINM; 1.371.625 filas OITW; 133 depósitos Reference | Movimiento hasta 24/09/2026; balance capturado 24/09/2026. Reader availability existente calcula on_hand-committed con UoM. No es disponibilidad en tiempo real; sucursal/depósito/oficina no equivalentes. |
| Compras | 8 datasets sellados y lineage; 6.169 facturas proveedor; 3.337 pedidos; 3.471 recepciones | Ventana declarada 2026, hasta 23/09; no equivalen a recepciones de producción. |
| Precios | Price/currency de líneas comerciales disponibles | No hay listas de precios vigentes publicadas en los 8 componentes ni maestro de condiciones acreditado por esta auditoría. Reference payment_terms/currencies vacíos; términos RC sí existen por otro contrato. Precio transaccional no equivale a lista vigente. |
| Clientes | 35.071 Reference; 1.859.136 documentos de deuda publicados en RC | Cliente facturado SAP no equivale a cliente comercial clasificado ni comprador final. Taxonomía comercial no se recertificó; ninguna equivalencia nueva. RC tiene corte 28/09, distinto al de Sales. |

## C. Estado contable

Hay conocimiento previo y una FK comercial reutilizable, pero no existe Diario ni Mayor publicados que puedan acreditarse ahora.

- OJDT/JDT1/OACT **no están en el catálogo Foundation/Atomic contable publicado**. OACT legacy local: 523 filas; no es el maestro vigente. Hay schemas y perfiles HANA históricos del 08/09/2026, no nuevas consultas.
- Perfil histórico: 5.789.775 OJDT, 18.242.546 JDT1 y 824 OACT, 31/03/2022–08/09/2026. Son counts de origen fechados, **no counts actuales del Lake ni asientos conciliados**. Conservados en `historical-accounting-source.json`.
- Asientos y líneas acreditados como datasets contables publicados en esta tarea: **0**. Cobertura contable publicada acreditada: ninguna. Saldos acreditados: ninguno. No significa que SAP carezca de asientos.
- Descubrimiento clave: Atomic `receivable_document AT VERSION 1322` contiene **1.859.136 transaction_id no nulos**, grain documental único, fuente real `OINV+INV6`. El join explícito source_system+DocEntry con Sales acredita **330.443/330.443 mappings OINV→TransId no sentinel**. Esto permite reutilizar el identificador sin volver a extraer todas las facturas. **No acredita que cada TransId exista en OJDT ni sus líneas/importes.**
- La misma fuente tiene **0 branch_id no nulos**. Foundation Sales/NC no publica BPLId ni TransId en sus propias cabeceras. Por tanto, la sucursal emisora tampoco puede responderse por esa ruta; no se sustituye por depósito/vendedor.
- Reference tiene siete sucursales de `almacenOficina.xlsx`, no un maestro OBPL acreditado para imputación. Tiene dos business_locations (una UNKNOWN). No atribuirles la semántica de BPLId.
- Evidencia RRHH del 10/09/2026 contiene OBPL con **0 registros** y actividad ProfitCode en el alcance de gastos RRHH, sin sucursal BPL. No acredita uso universal de dimensiones, reglas de reparto ni oficina. Catálogos ODIM/OPRC/OOCR/OCR1 requieren discovery real autorizado.
- JDT1.BPLId, ProfitCode y OcrCode2..5 existen en metadata histórica; **OJDT.BPLId no figura allí**. No asumir sucursal contable de cabecera. Primera dimensión JDT1 no se llama OcrCode en la evidencia disponible.
- Factura `12345`: **sin coincidencias en Sales publicada** en la consulta exacta por doc_num. Es un ejemplo, no se inventó un resultado. No se afirma inexistencia en todo SAP ni en otros períodos. Una consulta real requiere compañía/tipo/serie/DocEntry para evitar ambigüedades.

El [contrato de extracción y consulta](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/datalake_accounting_reaccreditation_v1/CONTRACT.md) define Diario, Mayor, extracción mínima, semántica monetaria, aperturas, cinco imputaciones independientes y pruebas de las diez preguntas. Las queries ejecutables son investigación aislada, no readers runtime. Facturas/NC/reversas y multimoneda sólo se ejercitaron sintéticamente; manuales/automáticos reales y conciliación completa siguen pendientes de datos.

## D. Contrato TelchiAI

La matriz distingue disponibilidad, backend, DEV, asistente y producción. Una capacidad de diseño no tiene publicación ni permiso efectivo.

| Pregunta → capability | Reader / dataset → publicación y snapshot | Métrica / semántica | Permiso y cobertura | Estado y evidencia |
| --- | --- | --- | --- | --- |
| Facturas recientes → sales.latest_documents | Reader Foundation / sales_document → CURRENT, 1408 | Documentos, fechas, cliente facturado | Permiso específico existente; alcance Console por tenant/workspace/módulo | Lake y backend disponibles; DEV previo, no E2E conversacional reejecutado aquí; sin promoción nueva. local-audit + estado local Telchi. |
| Facturación mensual → sales.period_billed_amount.v1 | Sales/NC → CURRENT, 1408 | Totales documentales; base/moneda y NC separadas | Permiso monetario existente; septiembre parcial | Datos observados, backend/DEV previo; no recertificación universal de conversación. business-checks. |
| Productos de factura → sales.invoice_lines.v1 | sales_document/sales_line → CURRENT, 1408 | Cantidad fuente, depósito, identidad; no UoM inferida | Permiso específico de líneas; clave interna acreditada | Disponible con límites documentados; sin habilitación nueva. schemas y tests existentes. |
| Clasificación física → propuesta Reference V2 | Candidata file-backed, sin snapshot productivo | Estado físico explícito vs UNCLASSIFIED/NOT_PHYSICAL | No se hereda permiso por observar candidata | Preparada/compatible; NO publicada/consumida/habilitada. reference-compatibility. |
| Disponibilidad por depósito → reader stock_availability existente | OITW + Reference → CURRENT 1408 | On-hand menos comprometido, UoM acreditada | Autorización del consumidor requerida; corte 24/09 | Lake/reader disponibles; no se acreditó una capability conversacional nueva. |
| Consumos/abastecimiento → componente material_supply | Archivos sellados en manifest CURRENT; derivación 1322 | Consumo y demanda derivada con contrato propio | Permiso de consumidor y cobertura de cada dataset | Integridad reacreditada; no supone preguntas de órdenes completas habilitadas. |
| Lista vigente de precios → pendiente | Dataset publicado ausente | Lista/moneda/condiciones/vigencia, no precio histórico de factura | Permiso de precios por definir | No soportada integralmente; schema de 8 componentes. |
| Factura→asiento→cuentas/importes → propuesta accounting.document_trace.v1 | Atomic receivable_document investigativo 1322 + OJDT/JDT1/OACT pendientes | FK explícita disponible; contabilidad no conciliada | Venta documental + contabilidad + detalle; permisos contables sólo propuestos | PARTIAL para mapping OINV; BLOCKED para respuesta contable. business-checks y CONTRACT. |
| Sucursal/oficina imputada → propuesta accounting.branch_trace.v1 | JDT1 + catálogos y crosswalk efectivo pendientes | A emisora ≠ B contable ≠ C dimensiones ≠ D depósito ≠ E oficina | Contabilidad + análisis por sucursal/cuenta/dimensión, scope vigente | No soportada con precisión actual. Ninguna atribución inventada. |
| Libro Diario → propuesta accounting.journal.v1 | OJDT/JDT1/OACT pendientes; sin publicación/snapshot | Todas las líneas; débito/crédito por base y moneda; origen/reversas | Permiso contable propio propuesto, no registrado | Diseño SQL validado en fixture; NO backend integrado/DEV real/asistente/producción. |
| Mayor septiembre → propuesta accounting.ledger.v1 | Diario + apertura certificada pendientes | Apertura + movimientos = cierre; naturaleza acreditada | Mayor, cuentas, agregado/detalle y sucursales autorizados | BLOCKED para saldos; no datos contables parciales que presentar como movimientos reales. |

Seguridad: se inspeccionó `handler.authorization.allowed` y se reejecutaron tests del mecanismo actual, incluyendo denegación previa al LLM y revalidación de permisos con repository Console. No se consultaron/alteraron grants ni se impersonó Presidencia. Por eso **AUTH real contable = NOT_ACCREDITED**, no PASS. No se asume que acceso de ventas habilite Mayor; Presidencia no es FULL_ACCESS técnico. Las restricciones por cuenta/dimensión necesitan ser expresables y verificables con el mecanismo vigente antes de habilitar.

BUSINESS ANSWER FIRST: mostrar sólo lo autorizado y probado. Si una futura fuente acredita sucursal documental pero no contabilidad, mostrarla etiquetada como documental y advertir falta de imputación contable. En este snapshot branch_id es NULL: no hay sucursal emisora verificable para sustituir. No bloquear datos comerciales válidos porque falte GL.

## E. Validación técnica y límites

El scope writer fue exclusivamente el directorio nuevo de investigación y reportes propios. Se preservaron todos los cambios preexistentes y no se actualizó estado GLOBAL ni autoridades locales de otros writers.

Archivos fuente nuevos bajo `SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/datalake_accounting_reaccreditation_v1/`: `audit.py`, `business_checks.py`, `accounting_queries.py`, `test_accounting_queries.py`, `CONTRACT.md`. Evidencia nueva bajo este directorio y los intentos v1/v1-r2; ninguno se presenta como estado GLOBAL.

Comandos ejecutados desde backend: `uv run --no-sync python -m modules.telchi.investigation.validation.datalake_accounting_reaccreditation_v1.audit --output ../../data/reports/telchi/datalake-accounting-reaccreditation-v1-r3` y módulo `business_checks`. Presupuestos: 2 threads DuckDB, 768 MB; tests secuenciales, sin xdist ni servicios temporales.

- Reader real, snapshots, schemas, 13 hashes/counts sellados, candidata/fingerprint y conservación de pointer: garantías ejecutadas descritas arriba.
- Tests focalizados: **61 PASS** Foundation publication/reader + contrato contable (`tests-final-v2.xml`), y **55 PASS** autorización/asistente + snapshot Reference + candidata física (`regressions.xml`): **116 PASS** en las corridas finales no duplicadas. No se cuentan los intentos previos como pruebas adicionales.
- `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`: **PASS**, logs anexos. Resumen legible por máquina: `gates.json`.
- Primeros intentos propios: llamadas incorrectas a API de store corregidas sin DDL ni writes; import relativo pytest corregido; lectura de timezone falló por pytz ausente y se corrigió serialización a VARCHAR sin instalar dependencias. Join inicial de comprobación usaba source_table OINV; se corrigió al valor realmente observado OINV+INV6 antes de emitir el resultado final. No fueron defectos de Foundation. Ningún intento fallido se usa como PASS.
- Hash integral de facts, catálogos dimensionales, apertura y conciliación real contable: **NOT_ACCREDITED**, no sustituidos por fixtures.
- Host observado: 8 CPUs, load aproximado 1,1–1,6; MemAvailable 6,2 GB; swap 61 MB estable, sin swap-in sostenida; iowait alto de procesos ajenos. **BUSY_BUT_SAFE** para lectura segmentada y secuencial, sin paralelismo de suites ni scan criptográfico masivo.
- `RESOURCE_GUARD=PASS` en alcance ejecutado; `CONCURRENCY_USED=1` runner / hasta 2 threads de conexión; `UNRELATED_PROCESSES_TERMINATED=0`. No se crearon browsers, servidores, workers persistentes ni servicios. Todos los procesos de los comandos propios terminaron al devolver resultado.
- Impacto transversal: sólo lectura de catálogo local y archivos, y evidencia investigativa; ningún cambio a interfaces runtime. No HANA, publicación, refresh, CURRENT, Atomic/facts, permisos, credenciales, VPN, Podman, runtime productivo, commits ni push.

## Próximas acciones exactas

La continuación funcional exige datos y autorizaciones separados; no más iteraciones sintéticas como sustituto de conciliación real.

1. Autorizar por separado discovery/captura HANA bounded del contrato mínimo. Reutilizar los 330.443 mappings OINV y ampliar sólo lo faltante: NC, GL íntegro, cuentas/configuración, dimensiones efectivas y oficina empresarial acreditada.
2. Acreditar local/system currency, naturaleza por cuenta y cobertura. Para septiembre indicar año y obtener apertura por sucursal/dimensión o historia íntegra acreditada; no basta el último saldo OACT.
3. Validar factura/NC→OJDT→JDT1→OACT con integridad/cardinalidad, cuenta de control y puente fiscal/comercial; separar canceladas, reversadas, manuales, automáticos, multimoneda y repartos. Completar las diez consultas con resultados reales y evidencia.
4. Implementar reader/adaptador sobre Foundation canónica sólo con fuentes y semántica acreditadas; ninguna importación runtime de investigation. Coordinar contratos de permisos contables y Presidencia sin otorgar FULL_ACCESS técnico.
5. Validar identidad real autorizada, restricciones cuenta/sucursal/dimensión, agregados y detalle; integración backend/conversacional DEV y gates separados. Publicación/habilitación/promoción requieren autorización explícita futura.

Resultado global **PARTIAL**. Las dos preguntas prioritarias aún **no son certificables**. El diseño y los tests offline reducen el trabajo pendiente, pero no acreditan datos contables inexistentes en la publicación actual.
