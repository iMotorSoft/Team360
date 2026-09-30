# TELCHI Data Lake Architecture V1

Este documento es la referencia vigente de arquitectura Data Lake de Telchi, subordinada al contexto canónico del módulo en `../../CONTEXT.md`. Consolida decisiones soportadas y no sustituye la evidencia histórica de los gates fuente.

**Last consolidated by:** `TELCHI_DATALAKE_SEGMENTED_INGESTION_MUTABLE_HISTORY_CONTRACT_V1`.

## 1. Purpose

Telchi permite consultar y analizar datos operativos de una empresa, especialmente SAP Business One sobre HANA, con respuestas rápidas, auditables, seguras y flexibles. Esta consolidación no crea datasets ni cambia infraestructura.

## 2. Authority and decision ownership

La arquitectura es GREENFIELD. Los ADR `ACCEPTED` del [índice ADR](TELCHI_DATALAKE_ADR_INDEX_V1.md) están vigentes hasta que un ADR posterior los sustituya explícitamente; ningún gate futuro puede redefinirlos en silencio.

La autoridad global de entidad, stage, roots y promoción sigue en `backend/modules/telchi/CONTEXT.md`. Este documento gobierna la arquitectura Data Lake dentro de ese marco. Los reportes de gates permanecen como evidencia histórica, no como autoridades rivales.

## 3. Architecture principles

Estos principios son obligatorios para los próximos gates y están registrados también en `architecture_principles.csv`.

1. **GREENFIELD FIRST.** Diseñar desde las necesidades vigentes, sin migrar arquitectura legacy.
2. **RAW IMMUTABLE.** La evidencia raw preservada no se reescribe, compacta ni limpia automáticamente.
3. **ATOMIC TRUTH.** Atomic conserva hechos canónicos, trazables y reconstruibles.
4. **BUSINESS READ MODELS.** Business optimiza preguntas conocidas sin sustituir atomic.
5. **CURRENT STATE MODELS.** Current representa estado operativo actual, no historia ni snapshot técnico.
6. **SECURITY BEFORE RETRIEVAL.** La autorización limita el query antes de leer datos.
7. **SQL CALCULATES / LLM INTERPRETS AND EXPLAINS.** El motor analítico calcula; el LLM interpreta intención y explica resultados.
8. **TRACEABILITY TO SOURCE.** Toda respuesta debe poder volver a datasets, filas y evidencia fuente.
9. **METRICS ARE VERSIONED.** Una definición cambia de versión; nunca cambia silenciosamente.
10. **PERFORMANCE IS PART OF THE CONTRACT.** La latencia de datos es una propiedad arquitectónica medible.
11. **BUSINESS-AS-OF != TECHNICAL SNAPSHOT.** El estado histórico empresarial no se deduce automáticamente de una versión técnica.
12. **DEV AND PROD USE IDENTICAL LOGICAL NAMES.** El aislamiento es físico y de configuración, no por sufijos lógicos.
13. **LEGACY IS EVIDENCE, NOT ARCHITECTURE.** Legacy informa semántica, casos y performance; no define el runtime nuevo.
14. **DERIVED DATA MUST BE REBUILDABLE.** Reference/crosswalk derivados, atomic, business, current y ops deben poder reconstruirse desde inputs y manifests.
15. **NO BUSINESS SEMANTIC GUESSING.** Un gap queda explícito hasta contar con evidencia suficiente.
16. **PREFER CONTENT EVOLUTION OVER SCHEMA EVOLUTION.** Los conceptos estables usan columnas, claves y relaciones canónicas; sus vocabularios evolucionan como reference data.
17. **VERSIONED RELATIONSHIPS.** Las clasificaciones y relaciones cambiantes conservan vigencia, estado, fuente y confianza sin fechas ficticias.
18. **NO GENERIC EAV BY DEFAULT.** La extensibilidad no convierte conceptos estables en pares genéricos `attribute_name` / `attribute_value`.
19. **CORRECTNESS OVER FRESHNESS OVER LATENCY.** Para igual definición, scope y `as_of`, la cifra local trusted debe coincidir con la autoridad SAP.
20. **FAIL-CLOSED PUBLICATION.** Candidate state no validado nunca se publica como trusted ni avanza watermark.
21. **HANA LOAD MINIMIZATION.** La ingesta usa lecturas SAP acotadas, compartidas y de baja concurrencia; el chat no dispara HANA.
22. **RESOURCE-GUARDED DATA WORKLOADS.** Jobs pesados tienen límites, guards continuos, backpressure, checkpoints y safe abort.

## 4. Current stack

Cada componente tiene una responsabilidad única; PostgreSQL no es el almacén de hechos analíticos.

| Component | Current responsibility |
| --- | --- |
| SAP HANA | Source system SAP Business One, acceso READ ONLY. |
| Parquet | Storage físico analítico. |
| DuckLake | Metadata lakehouse y administración de tablas, archivos, transacciones y snapshots propios. |
| DuckDB | Motor de ejecución analítica y transformación canónica. |
| PostgreSQL 18 | Backend del catálogo/metadata DuckLake. No almacena el Data Warehouse analítico. |
| Team360 | Capa futura de aplicación, identidad, autorización, semantic layer, API y chat. |
| Semantic layer | Métricas, dimensiones, entidades, filtros, tiempo, unidades, moneda, grain y scope. |
| LLM | Interpretación de intención y explicación; no cálculo de cifras de negocio. |

## 5. Logical architecture

El flujo separa evidencia, verdad canónica, modelos optimizados, semántica y entrega autorizada.

```text
SOURCE
  ↓
RAW
  ↓
REFERENCE / CROSSWALK
  ↓
ATOMIC
  ↓
BUSINESS
  ↓
CURRENT
  ↓
SEMANTIC LAYER
  ↓
AUTHORIZED QUERY
  ↓
CHAT / API / DASHBOARD
```

- **SOURCE:** sistemas y archivos de origen, principalmente SAP HANA, legacy y fuentes externas aprobadas.
- **RAW:** evidencia inmutable de extracción o preservación, sin promesa de semántica ejecutiva.
- **REFERENCE / CROSSWALK:** identidades canónicas, catálogos y mappings evidence-based con vigencia y calidad.
- **ATOMIC:** hechos mínimos de negocio, reconstruibles y con lineage.
- **BUSINESS:** read models derivados y denormalizados para preguntas y flujos concretos.
- **CURRENT:** proyecciones del estado operativo más reciente autorizado.
- **SEMANTIC LAYER:** contrato versionado que traduce una pregunta a métricas, dimensiones, filtros, tiempo y grain.
- **AUTHORIZED QUERY:** ejecución limitada al scope permitido antes del scan o retrieval.
- **CHAT / API / DASHBOARD:** canales consumidores; no son fuentes de verdad.

## 6. Ownership boundaries

Ownership define qué puede administrar DuckLake y qué debe permanecer como evidencia preservada.

### 6.1 Raw ownership

`raw/legacy` conserva evidencia histórica inmutable y `raw/sap` conservará evidencia futura de extracciones SAP. Raw no es DuckLake-owned, no se compacta, no se reescribe, no se limpia automáticamente y no se usa como read model ejecutivo.

El mirror `raw/legacy/parquet` preserva 696 archivos byte-identical. Una fuente raw puede ser leída para transformación, pero no registrarse automáticamente como archivo administrado por DuckLake.

### 6.2 DuckLake ownership

DuckLake administra principalmente `atomic`, `business`, `current` y `ops`. Puede administrar productos derivados de `reference/crosswalk` sólo después de una decisión explícita; nunca adquiere ownership automático de sources preservados.

Los 14 reference y 8 crosswalk existentes son hoy productos reconstruibles externos a DuckLake. El foundation confirmó que tampoco son DuckLake-owned por defecto.

### 6.3 PostgreSQL 18 catalog

La configuración lógica vigente es estable y no contiene hechos analíticos.

```text
POSTGRES_CATALOG_DATABASE=team360_telchi_ducklake
POSTGRES_RUNTIME_ROLE=team360_telchi_ducklake
POSTGRES_METADATA_SCHEMA=public
```

PostgreSQL 18 contiene metadata DuckLake en la database dedicada. DuckLake 1.0 usa `public` para sus tablas internas; la database no es el Data Warehouse y el role runtime dedicado es `LOGIN`, `NOSUPERUSER`, `NOCREATEDB` y `NOCREATEROLE`.

Los roots físicos vigentes son `DATA_ROOT=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi` y `DUCKLAKE_DATA_PATH=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/ducklake/data`. Data Root contiene datos, nunca source code ni secretos.

## 7. DEV and PROD isolation

DEV y PROD usan exactamente los mismos nombres lógicos para evitar divergencia de código y configuración semántica.

```text
DEV:  team360_telchi_ducklake
PROD: team360_telchi_ducklake
```

La separación ocurre mediante host o instancia, network, secrets, filesystem/Data Root y environment config. No se usan sufijos `_dev` o `_prod`. Si ambos entornos compartieran el mismo cluster PostgreSQL, existiría un conflicto de aislamiento que infraestructura debe resolver, no un motivo para cambiar silenciosamente la convención.

## 8. Data layer contracts

Las capas derivadas separan verdad estable, optimización de lectura y estado presente.

### 8.1 Atomic truth

Atomic representa hechos canónicos y reconstruibles. Preserva, según dominio, identidades de fuente, documentos y líneas, fechas, cantidades, unidades, currencies, impuestos, importes, estados, relaciones, metadata de extracción y lineage.

Atomic no decide conceptos CEO ambiguos, no precalcula interpretaciones provisionales, no oculta lineage y no descarta campos necesarios para reconstrucción. Un gap semántico puede bloquear una métrica business definitiva sin bloquear el hecho atomic que conserva su evidencia.

### 8.2 Atomic versus SAP tables

Atomic modela verdades de negocio y no copia SAP tabla por tabla. Ejemplos conceptuales son `sales_document`, `sales_line`, `credit_note`, `inventory_movement`, `production_order`, `production_component`, `production_receipt`, `payment`, `reconciliation`, `purchase_order` y `purchase_line`.

La lista y grains definitivos pertenecen a `TELCHI_DATALAKE_ATOMIC_CORE_V1`. Los nombres conceptuales no autorizan crear tablas en este gate ni reemplazan el diseño físico aprobado.

### 8.3 Business read models

Business combina atomic con reference/crosswalk, enriquece y denormaliza para preguntas conocidas, conserva lineage y es completamente rebuildable. Ejemplos futuros: `sales_flow`, `inventory_flow`, `production_flow`, `cash_flow` y `customer_credit_history`.

El fast path ejecutivo normal usa business/current. Atomic queda para truth, reconciliación, drill-down, análisis profundo y fallback controlado; una pregunta CEO normal no debe reconstruir SAP desde atomic en cada request.

### 8.4 Current state models

Current representa el estado operativo actual y autorizado. Ejemplos futuros: `stock_current`, `customer_credit_current`, `purchase_open` y `production_open`.

Un current model no es un event log histórico ni un DuckLake technical snapshot. Puede ser una vista sobre el último corte válido o una materialización justificada por medición, pero debe declarar `data_as_of` y freshness.

## 9. Technical snapshot versus business state

Un DuckLake snapshot es una versión técnica del lakehouse. Un business historical state es una representación empresarial as-of una fecha y requiere reglas temporales del dominio.

“Deuda hoy” puede usar `customer_credit_current`. “Deuda al 31/08” requiere reconstrucción o `customer_credit_history` as-of con documentos, NC, pagos, reconciliaciones, vencimientos y saldo abierto. Un snapshot técnico no resuelve automáticamente esa semántica.

## 10. Ingestion contract

La secuencia objetivo preserva fuente, manifest, validación y publicación transaccional sin inventar todavía un extractor o scheduler.

```text
SAP HANA READ ONLY
  ↓ extract
raw/sap
  ↓ manifest
validation
  ↓ canonical transform with DuckDB
DuckLake transaction
  ↓
atomic
  ↓
business/current rebuild or update
```

Cada run futuro debe conservar watermarks dataset-specific, row counts, hashes, source timestamps, tiempos de extracción/ingesta, versiones y lineage. Un fallo no avanza el último watermark exitoso. Raw se publica como evidencia inmutable; sólo derivados entran en transacciones administradas.

## 11. Authorized read contract

La lectura comienza por identidad y autorización, no por el dataset.

```text
User question
  ↓
identity
  ↓
authorization context
  ↓
entity resolution within scope
  ↓
semantic plan
  ↓
data product routing
  ↓
DuckDB / DuckLake
  ↓
result
  ↓
LLM explanation
```

El patrón prohibido es `leer todo → responder → ocultar después`. El patrón obligatorio es `identity → permissions → allowed scope → filtered query → result`. Un warehouse manager sólo consulta warehouses permitidos; CEO/admin puede recibir full scope cuando su autorización real lo permite.

## 12. Semantic layer

El semantic layer es composable y no se reduce a intents rígidos. Trabaja con `metrics`, `dimensions`, `entities`, `filters`, `time_range`, `comparison`, `unit`, `currency`, `grain`, `scope` y `freshness`.

Un semantic plan debe resolver ambigüedades o pedir aclaración, seleccionar una versión de métrica y enrutar al producto adecuado. Las expresiones temporales usan timezone empresarial configurado y no el timezone implícito del servidor.

## 13. LLM boundary

El LLM interpreta lenguaje natural, resuelve contexto conversacional, selecciona semántica conocida, resume y explica resultados ya calculados.

El LLM no suma datasets, inventa conversiones, joins, aliases, métricas, FX, tax semantics ni security scope. SQL/DuckDB calcula sobre contratos y datos autorizados; el LLM no es una calculadora financiera ni una autoridad semántica.

## 14. Performance contract

Los objetivos son de **DATA QUERY LATENCY** warm y no incluyen LLM, UI, red ni streaming.

| Stage/class | Observed or target P95 |
| --- | ---: |
| Entity resolution observed | `< 8 ms` aproximadamente; máximo baseline `7.959 ms` |
| DuckLake warm baseline observed | `~10 ms`; baseline `10.0535 ms` |
| CLASS A | `<= 100 ms` |
| CLASS B | `<= 300 ms` |
| CLASS C | `<= 750 ms` |
| Deep analysis / CLASS D | Sin obligación sub-second |

ATTACH cold no debe ocurrir por pregunta. Conexiones y catálogo se reutilizan de forma segura. Current/business son el fast path; atomic se reserva para profundidad, evidencia y reconciliación.

## 15. Query traceability

Toda future query debe poder registrar evidencia suficiente para reproducir qué se preguntó, qué se autorizó y qué datos se usaron.

```text
query_id
user/scope
semantic_plan_hash
metric versions
dataset versions
DuckLake snapshot
data_as_of
execution_ms
row_count
source lineage
```

Este contrato no implementa runtime. Cada drill-down futuro debe revalidar scope y as-of, no heredar acceso por conveniencia.

## 16. Metric versioning

Una métrica se identifica por `metric_id + semantic_version`, por ejemplo `NET_SALES@1` u `OVERDUE_RECEIVABLE@1`.

Definición, fórmula lógica, grain, moneda/unidad, tiempo, inclusiones, exclusiones y autoridad de reconciliación no pueden cambiar silenciosamente. Un cambio semántico crea una versión nueva y conserva trazabilidad hacia resultados previos.

## 17. Known semantic gaps

Los gaps actuales no bloquean Atomic Core si atomic conserva evidencia suficiente, pero sí bloquean congelar algunos business metrics definitivos.

| Gap | Current status | Atomic preservation required |
| --- | --- | --- |
| Cash versus credit sales | SEMANTIC_GAP | Payment term, payment received, open balance, document type, payments y reconciliations. |
| `NET_SALES` | SEMANTIC_GAP | Gross/net fields, discounts, NC, cancellations, tax and currency evidence. |
| Production count default | SEMANTIC_GAP | Orders, statuses, receipts, output quantities and runs as distinct facts. |
| Cost semantics | SEMANTIC_GAP | Document, historical, moving-average, production and last-purchase cost evidence when available. |
| FX policy | SEMANTIC_GAP | Document/local/system currencies and approved FX evidence. |
| Tax semantics | SEMANTIC_GAP | Tax components, tax-relevant amounts, gross/net fields and document totals. |

## 18. Domain-specific invariants

Estas reglas evitan que los próximos gates conviertan evidencia parcial en semántica definitiva.

### 18.1 L-product priority

Legacy clasificaba por el primer carácter de `ItemCode`: `L* → Litel`, `M* → Medi` y el resto como Otros. `ItemCode LIKE 'L%'` sigue siendo evidencia histórica y una posible regla de construcción de Reference V2, no un predicado de runtime. `LIKE_L_REQUIRED_AT_QUERY_TIME=NO`; las queries consumen `portfolio_family`.

La referencia canónica materializa la clasificación mediante `is_l_product` y, cuando se confirme el contrato, `business_family` o `commercial_family`. El flag L no implica marca, pertenencia Telchi, business unit, operating model ni sitio productivo. Stock, replenishment, sales, MRP, capacity y policy priorizan L-products cuando aplique sin excluir silenciosamente otros productos.

### 18.2 Reference and crosswalk

El estado conocido es `REFERENCE_DATASETS_CREATED=14`, `CROSSWALK_DATASETS_CREATED=8` y `ENTITY_ALIAS_DATASET_CREATED=YES`.

Reference/crosswalk resuelven identidad y mapping; no son atomic. Son reconstruibles y no se convierten automáticamente en DuckLake managed. Los mappings ambiguos o no evidenciados permanecen `UNKNOWN`, `UNMAPPED` o con candidatos explícitos.

### 18.3 Warehouse and branch

Warehouse y branch son entidades distintas; el mapping puede ser `mapped`, `unmapped` o `temporal unknown` y nunca se presupone 1:1.

El workbook evidenció 51 mappings con vigencia desconocida y 82 warehouses SAP actuales unmapped en ese contrato. La atribución histórica de branch no se fabrica desde el mapping actual.

### 18.4 Entity resolution

Los canonical IDs se resuelven primero y los aliases son evidence-based. “creolina” y “Saavedra” resolvieron como búsquedas/candidatos observados; “Segundo Anillo” no resolvió y sigue como gap explícito.

No se inventan aliases ni se selecciona arbitrariamente entre candidatos ambiguos. La resolución ocurre dentro del scope autorizado antes de consultar hechos.

### 18.5 Units of measure

Cantidades y unidades se calculan desde datos y reglas versionadas. Deben distinguirse `sales_uom`, `inventory_uom`, `purchase_uom` y `canonical_measure`.

El LLM no convierte intuitivamente ni presume factores. Una conversión requiere factor, fuente, confianza y vigencia aprobados.

### 18.6 Currency and FX

BOB, USD y otras currencies preservan document currency, local currency, system currency y FX evidence. No se usan constantes legacy como `6.97`.

Una métrica financiera declara moneda objetivo y política FX. Si falta una tasa histórica aprobada, el resultado se detiene o expone el gap; no mezcla currencies.

### 18.7 Tax

Tax semantics sigue abierto. Atomic conserva tax components, tax-relevant amounts, gross/net fields y document totals cuando la fuente los ofrece.

Ninguna métrica asume IVA incluido o excluido sin versión semántica explícita y reconciliada.

### 18.8 Credit

Los current credit read models deben construirse sobre la reconstrucción SAP validada, no sobre fórmulas legacy.

Deben preservar invoice, credit note, payment, reconciliation, due date y open balance. `OITR/ITR1` permanece autoridad conceptual de settlement y `RCT2` no la sustituye.

### 18.9 Cash versus credit

Payment term, payment received, open balance, credit document y cash transaction no son equivalentes. La clasificación ejecutiva definitiva está pendiente.

Atomic debe conservar cada elemento por separado para permitir reconciliación y una métrica futura evidence-backed.

## 19. Product & operating model

El producto se identifica de forma estable y se clasifica mediante conceptos separados. La existencia de un concepto queda aceptada aunque su vocabulario o mapping permanezca provisional.

### 19.1 Separate concepts

Los conceptos siguientes no son equivalentes y no se derivan en bloque desde el código del producto.

| Concept | Semantic role | Contract status |
| --- | --- | --- |
| Brand | Identidad comercial del producto, por ejemplo TELCHI cuando exista evidencia. | Concept confirmed; authority gap open. |
| Business unit | Unidad económica u organizacional con la que Telchi gestiona el negocio. | Concept confirmed; taxonomy provisional. |
| Operating model | Forma en que Telchi obtiene o transforma el producto. | Concept confirmed; vocabulary provisional. |
| Sales / distribution channel | Forma de comercialización o llegada al cliente. | Concept confirmed; taxonomy provisional. |
| Production site | Lugar físico de fabricación, fraccionamiento, acondicionamiento o transformación. | Concept confirmed; mappings open. |
| Warehouse | Ubicación logística SAP o física de inventario. | Confirmed and separate from production site. |
| Branch | Unidad o local organizacional/comercial relacionado mediante mappings explícitos. | Confirmed and separate from warehouse/site. |
| Product family | Clasificación comercial o de negocio, incluida la clasificación L histórica. | Concept confirmed; vocabulary evidence-based. |

`RETAIL` puede resultar canal, business unit o ambos según evidencia organizacional; no se decide por intuición. `is_telchi_product`, `is_l_product`, `brand`, `business_unit`, `operating_model` y `production_site` representan hechos o clasificaciones distintos.

### 19.2 Conceptual product and catalogs

El diseño objetivo de `reference.product` puede exponer `canonical_product_id`, `item_code`, `product_name`, `brand_id`, `business_unit_id`, `operating_model_id`, `is_telchi_product`, `is_l_product`, `inventory_uom`, `sales_uom` y `purchase_uom`. Este gate no obliga a cambiar físicamente el dataset actual.

Las futuras entidades estables son:

- `reference.brand`: `brand_id`, `code`, `name`, `active`, `valid_from`, `valid_to`, `source`, `confidence`.
- `reference.business_unit`: `business_unit_id`, `code`, `name`, `description`, `active`, `valid_from`, `valid_to`, `semantic_version`.
- `reference.operating_model`: `operating_model_id`, `code`, `name`, `description`, `active`, `semantic_version`.
- `reference.production_site`: `production_site_id`, `code`, `name`, `site_type`, `active`, `valid_from`, `valid_to`, `source`, `confidence`.

No se cargan valores especulativos. Como vocabulario candidato de operating model pueden evaluarse `MANUFACTURED`, `FRACTIONATED`, `REPACKAGED`, `PURCHASED_FOR_RESALE` y `THIRD_PARTY_MANUFACTURED`; la arquitectura del concepto es `ACCEPTED`, pero ese vocabulario permanece `PROVISIONAL` hasta evidencia real.

### 19.3 Production site, warehouse and temporal relations

`production_site != warehouse`: un sitio productivo puede contener varios warehouses y cada warehouse puede cumplir roles de materia prima, trabajo en proceso, producto terminado o despacho. No se asume una relación 1:1 ni se inventan sitios.

La relación futura `product_production_site` conserva `canonical_product_id`, `production_site_id`, `operating_model_id`, `valid_from`, `valid_to`, `status`, `source` y `confidence`. Admite `CONFIRMED`, `UNMAPPED`, `AMBIGUOUS` y `PROVISIONAL`; fechas desconocidas quedan `NULL`, nunca ficticias.

Producto–business unit y producto–operating model también pueden cambiar con el tiempo. Una transición, por ejemplo de `PURCHASED_FOR_RESALE` a `MANUFACTURED`, se representa con relaciones o clasificaciones versionadas, no con columnas booleanas nuevas. La implementación física definitiva corresponde a Reference V2 o a un gate posterior explícito.

### 19.4 Identity and query implications

`canonical_product_id` identifica; brand, business unit, operating model, channel, production site y family clasifican o relacionan. Ninguna clasificación cambiante se incorpora al ID canónico.

La autoridad de clasificación reside en reference y relationships; atomic es autoridad de hechos; business/current son read models derivados. Atomic conserva `canonical_product_id` y las identidades suficientes para enriquecimiento posterior sin duplicar textos de clasificación en cada fila. Business/current pueden materializar IDs o nombres por performance y ergonomía, pero esos textos no se convierten en autoridad maestra.

Este contrato habilita consultas sobre fabricación propia, reventa, fraccionamiento, margen por modelo operativo, sitio de fabricación, sucursales que venden sus productos y materias primas requeridas sin migrar el schema por cada nueva categoría.

## 20. Schema evolution strategy

La estrategia es **STABLE CANONICAL SCHEMA + EXTENSIBLE REFERENCE DATA**: preferir evolución de contenido sobre evolución de schema sin degradar la semántica.

### 20.1 Content-first evolution

Conceptos semánticos estables se modelan como columnas, foreign keys o relaciones canónicas. Valores, taxonomías y clasificaciones cambiantes evolucionan mediante nuevas filas de catálogo; relaciones cambiantes usan vigencias temporales, estado, fuente y confianza.

Por ello no se adopta como mecanismo principal una proliferación de flags como `is_manufactured`, `is_fractionated`, `is_retail`, `is_third_party`, `is_imported`, `is_repacked` o `is_contract_packaged`. Un valor futuro como `CONTRACT_PACKAGING` debe agregarse como contenido de `operating_model`, no como una columna en cada hecho.

### 20.2 EAV rejected as default

La extensibilidad no autoriza un Entity-Attribute-Value indiscriminado de `attribute_name` y `attribute_value`. `production_site`, `business_unit` y `operating_model` son conceptos estables y merecen IDs y relaciones explícitas; lo extensible son sus valores.

### 20.3 Controlled schema change and DuckLake

Un cambio de schema sigue permitido cuando aparece un concepto semántico genuinamente nuevo que no puede representarse correctamente, por ejemplo una futura `regulatory_license`. La estabilidad no justifica forzar una semántica incorrecta.

DuckLake soporta schema evolution, pero esa capacidad es una herramienta controlada y excepcional, no el mecanismo normal de configuración del negocio. El mecanismo normal es reference data más versioned relationships.

## 21. Legacy role

Legacy DataScience demostró que Parquet enriquecido con filtros y agregaciones podía responder rápidamente. El nuevo sistema conserva ese principio de performance con DuckLake, DuckDB, lineage formal, seguridad, semantic contracts y versioning.

Tornado, Dask per request, ArangoDB, hardcodes, credenciales, naming legacy, handlers y modelos físicos antiguos no se heredan por defecto. Legacy es evidencia semántica, funcional y de performance, nunca arquitectura nueva.

## 22. Current implementation status

El estado separa capacidades ya materializadas de contratos y piezas todavía inexistentes.

| Capability | Status |
| --- | --- |
| Legacy Parquet mirror | PASS; 696/696 preservados. |
| Reference/crosswalk V1 físico | PASS; 14 reference, 8 crosswalk y entity alias, sin mutaciones en este gate. |
| Reference V2 contract | DESIGN READY; 21 entidades/equivalentes diseñados y rebuild físico pendiente. |
| DuckLake/PostgreSQL 18 foundation | PASS; catálogo dedicado y probe sintético. |
| CEO semantic/performance contract | DEGRADED controlled; contrato listo, seis gaps explícitos. |
| Ingestion modes/resource guards | PASS; contrato operacional documental listo, sin runtime ni scheduler. |
| Atomic | NOT BUILT. |
| Business | NOT BUILT. |
| Current | NOT BUILT. |
| Chat/API/dashboard Telchi | NOT BUILT. |

El foundation sintético no cuenta como hecho atomic/business/current. Esta consolidación no modifica ningún estado de runtime o Data Root.

## 23. Architecture roadmap

El roadmap actual define orden de madurez, no promete que cada paso sea un único gate.

1. Architecture/ADR consolidation.
2. Product operating model and stable schema contract V1.
3. Product and operating model contract V2.
4. Reference V2 rebuild decision and explicit rebuild gate.
5. Atomic Core, sólo después de esa decisión y revisión.
6. Atomic reconciliation/validation.
7. Semantic gap closure where evidence permits.
8. Business read models.
9. Current read models.
10. Semantic planner and security integration.
11. Chat/API and later production promotion.

La consolidación de producto terminó en el paso 3; este gate agrega el contrato operativo previo a la ingesta futura. `REFERENCE_V2_REBUILD_REQUIRED=YES`; no debe iniciar Atomic Core ni ejecutar el rebuild sin un gate posterior explícito.

## 24. Product and operating model V2

V2 corrige el contrato antes de Atomic y mantiene separados `brand`, `business_unit`, `portfolio_family`, `product_business_type`, `operating_domain`, `operating_model`, `sales_channel`, `production_site`, `warehouse` y `branch`. `product_family` y `commercial_family` quedan como aliases deprecados de `portfolio_family`; no se crean dimensiones duplicadas.

### 24.1 Canonical product model

`reference.product` conserva como columnas estables `canonical_product_id`, `item_code`, `product_name` y las tres claves de UoM (`sales_uom_id`, `inventory_uom_id`, `purchase_uom_id`). Brand, portfolio, tipo de negocio, business unit, operating model, sitios y parties se resuelven mediante foreign keys y relaciones versionadas, no como textos autoritativos repetidos.

`is_telchi_product`, `manufactured_by_telchi` y `brand_owned_by_telchi` son predicados independientes. Preferentemente se derivan de relaciones autoritativas y sólo se materializan en read models por ergonomía o performance. En white-label, por ejemplo, `manufactured_by_telchi=TRUE` y `brand_owned_by_telchi=FALSE`; `is_telchi_product` permanece sujeto a `TELCHI_PRODUCT_DEFINITION`.

### 24.2 Portfolio classification and executive segmentation

`portfolio_family` responde medicamentos versus Litel. `product_business_type` responde, dentro de Litel, elaborados de laboratorio versus materias primas versus fraccionados. Las taxonomías son `PROVISIONAL` y admiten `CONFIRMED`, `PROVISIONAL`, `UNMAPPED` y `AMBIGUOUS`, con source, confidence y vigencia.

La comparación ejecutiva prioriza `net_sales`, `gross_sales` cuando corresponda, conteos de documentos/clientes y business volume. Unidades físicas heterogéneas no son la métrica principal. El drill-down es portfolio → product business type → product → branch/channel → documents.

### 24.3 Business unit, channel and locations

Business unit describe quién gestiona económica u organizacionalmente el negocio; sales channel describe por qué canal ocurrió la operación. Retail One, DMS y SAP directo son evidencia de canales y no business units automáticas. `production_site != warehouse`, `warehouse != branch` y `branch != production_site`; todas las relaciones relevantes pueden ser many-to-many y temporales.

`production_site_warehouse` conserva `production_site_id`, `warehouse_id`, `warehouse_role`, `valid_from`, `valid_to`, `source`, `confidence` y `status`. `product_production_site` conserva además `canonical_product_id` y `operating_model_id`; un `primary_production_site_id` nunca sustituye esa historia.

### 24.4 Operating domain and industrial manufacturing

`operating_domain` separa `INDUSTRIAL_MANUFACTURING`, `PHARMACY_BOTICA` y `COMMERCIAL_RESALE` como vocabulario provisional. `operating_model` representa adquisición o transformación mediante valores provisionales como `MANUFACTURED`, `FRACTIONATED`, `REPACKAGED`, `PURCHASED_FOR_RESALE` y `CONTRACT_MANUFACTURING`.

Contract manufacturing y white-label pertenecen al dominio industrial. White-label es representable como manufacturing arrangement con manufacturer Telchi, contract customer tercero, brand y brand owner tercero; no se infieren estas parties entre sí. Atomic industrial deberá preservar fórmula/BOM, orden, componentes, issues, receipts, cantidades/UoM, sitio, warehouses, lote/batch, costos, fechas, estado, customer tercero y lineage.

### 24.5 Pharmacy / botica and magistral compounding

Receta magistral significa una preparación de botica para un cliente y una droga/preparación puntual; no es white-label ni una variante de orden industrial. El vocabulario distingue `industrial_formula / BOM` de `magistral_preparation / magistral_formula`.

El futuro `atomic.pharmacy_compounding`, separado de órdenes, BOM e issues industriales, tiene grain de una preparación/solicitud realizada y preserva customer, drug/preparation, descripción, cantidad/UoM, fechas, botica/site, amount, cost evidence, status y lineage. No captura PII clínica innecesaria. Si faltan mano de obra, horas, costos completos, capacidad o merma, la evaluación debe emitir `PARTIAL_ECONOMIC_EVALUATION` y declarar los gaps.

### 24.6 Schema evolution and physical impact

La regla sigue siendo **STABLE CANONICAL SCHEMA + EXTENSIBLE REFERENCE DATA + VERSIONED RELATIONSHIPS**, sin EAV genérico. Conceptos estables tienen schemas explícitos; valores cambian como catálogo; relaciones cambian con vigencia; sólo un concepto semántico nuevo justifica schema change.

Los 14 reference datasets V1 son evidencia física validada, no un count objetivo. V2 diseña 21 entidades/equivalentes de referencia: migra `product_groups` a `portfolio_family`, migra `channels` a `sales_channel` e incorpora brand, business unit, product business type, operating domain, operating model, production site y party sin duplicar equivalentes existentes. El impacto es aditivo y de migración/rename de `channels`; no se modificó Parquet. `REFERENCE_V2_REBUILD_REQUIRED=YES`, `REFERENCE_V2_REBUILD_EXECUTED=NO`.

Los contratos machine-readable V2 viven en `../validation/datalake_product_and_operating_model_contract_v2/`. Corrigen producto, clasificaciones, relaciones, reference schemas, fabricación industrial, botica, requisitos Atomic, read models y catálogo CEO. Atomic, business y current siguen sin materializar.

## 25. Terminology glossary

| Term | Meaning |
| --- | --- |
| brand | Marca comercial del producto; no fabricante ni business unit. |
| business unit | Unidad económica u organizacional gestora. |
| portfolio family | Clasificación ejecutiva como medicamentos o Litel. |
| product business type | Subtipo dentro del portfolio, como elaborado, materia prima o fracción. |
| operating domain | Contexto superior industrial, botica o reventa. |
| operating model | Cómo se obtiene, transforma o prepara el producto. |
| sales channel | Canal por el que ocurrió la operación. |
| production site | Sitio físico productivo, distinto de warehouse. |
| warehouse | Ubicación logística de inventario. |
| branch | Local/unidad organizacional o comercial. |
| contract manufacturing | Producción industrial encargada por un tercero. |
| white-label | Caso de producción para terceros donde la marca final pertenece al tercero. |
| magistral compounding | Preparación puntual de botica para cliente y droga/preparación. |
| industrial formula/BOM | Fórmula y componentes de producción industrial; no receta magistral. |

## 26. Source gate references

Las fuentes se resumen y enlazan para evitar copiar sus páginas completas; los estados históricos y detalles reproducibles permanecen allí.

| Gate | Consolidated contribution | Source |
| --- | --- | --- |
| `TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS` | Inventario legacy, grains observados, overlaps y baseline Parquet. | [Historical inventory](TELCHI_HISTORICAL_DATA_INVENTORY_V1.md) |
| `TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED` | Evidencia SAP, relaciones, gaps y reglas de negocio. | [SAP knowledge](TELCHI_SAP_KNOWLEDGE_INVENTORY_V1.md) |
| `TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS` | Modelo lógico, lineage, temporalidad, seguridad y atomic/business boundary. | [Canonical model](TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1.md) |
| `TELCHI_DATALAKE_PHYSICAL_DESIGN_READINESS_V1_PASS` | Cierre seguro de gaps físicos sin adivinar. | [Physical readiness](TELCHI_DATALAKE_PHYSICAL_DESIGN_READINESS_V1.md) |
| `TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS` | Layout, schemas, incrementalidad, registry y ownership físico. | [Physical design](TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1.md) |
| `TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1_PASS` | Mirror raw inmutable de 696 Parquet. | [Legacy mirror](TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1.md) |
| `TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1_PASS` | Reference/crosswalk, aliases, L-products y mappings explícitos. | [Reference and crosswalk](TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1.md) |
| `TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1_PASS` | DuckLake, PostgreSQL catalog, role dedicado, ownership y warm baseline. | [DuckLake foundation](TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1.md) |
| `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` | Semantic plan, gaps, fast path y targets de latencia. | [CEO query contract](TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1.md) |
| `TELCHI_DATALAKE_PRODUCT_OPERATING_MODEL_AND_STABLE_SCHEMA_CONTRACT_V1_PASS` | Separación inicial de ejes y stable-schema principle. | Este living document y artefactos V1. |
| `TELCHI_DATALAKE_PRODUCT_AND_OPERATING_MODEL_CONTRACT_V2_PASS` | Corrección pre-Atomic de producto, fabricación, botica, schemas y catálogo CEO. | Contratos V2 machine-readable. |
| `TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1_PASS` | Modos de ingesta, validez, reconciliación, HANA load minimization y resource guards. | Contratos machine-readable del gate de ingesta. |

## 27. Gate safety and stop condition

Este gate fue exclusivamente documental y contractual. No accedió SAP, PostgreSQL, DuckLake, legacy source ni Data Root; no creó databases, roles, tables, Parquet o runtime.

```text
SAP_ACCESSED=NO
SAP_WRITE_COUNT=0
POSTGRES_MODIFIED=NO
DUCKLAKE_MODIFIED=NO
DATA_FILES_MODIFIED=0
ATOMIC_TABLES_CREATED=0
BUSINESS_TABLES_CREATED=0
CURRENT_TABLES_CREATED=0
```

Esta actualización contractual tampoco modificó reference/crosswalk materializado, PostgreSQL, DuckLake o Data Root. La decisión es `REFERENCE_V2_REBUILD_REQUIRED=YES`, por lo que corresponde **STOP AND REVIEW** y proponer un gate específico de Reference V2. Atomic Core queda expresamente prohibido hasta resolver ese paso y obtener revisión explícita.

## 28. Ingestion modes and operational contract

Este contrato fija la operación futura de ingesta sin implementar scheduler, workers, polling recurrente ni backfill.

### 28.1. Two modes only

Telchi distingue exactamente dos modos principales: `INITIAL_INGESTION` (también `BOOTSTRAP` o `BACKFILL`) construye el baseline histórico confiable, e `INCREMENTAL_UPDATE` (también `CONTINUOUS_SYNC`) mantiene el estado local. `RECONCILIATION` es un mecanismo de control interno del UPDATE, no un tercer pipeline principal.

Ambos modos usan el mismo schema canónico, IDs, mappings, lineage, transformación y validaciones. La diferencia está en selección de fuentes, tamaño de ventana, detección de cambios y scheduling. `SAME_SOURCE_RECORD + SAME_REFERENCE_VERSION + SAME_TRANSFORMATION_VERSION` produce el mismo `ATOMIC_ID` y contenido Atomic, independientemente del modo.

### 28.2. Initial ingestion

`INITIAL_INGESTION` puede combinar fuentes históricas legacy y lecturas SAP HANA READ ONLY aprobadas para construir `raw → atomic → validation → reconciliation → trusted baseline → initial watermarks`. No significa full scan descontrolado: la unidad preferida es `MONTH`, con ventanas acotadas, chunks, checkpoint y resume.

El lifecycle contractual es `PRECHECK → EXTRACT_BOUNDED_WINDOW → PRESERVE_RAW → VALIDATE → TRANSFORM → RECONCILE → COMMIT → CHECKPOINT → NEXT_WINDOW`. Un fallo afecta sólo la ventana y no obliga a reiniciar todo el histórico. `MONTH` es unidad de trabajo, no contrato de un Parquet Atomic por mes.

### 28.3. Incremental update and reconciliation

`INCREMENTAL_UPDATE` parte del último trusted watermark, detecta cambios, identifica claves afectadas, lee desde SAP sólo los objetos autoritativos afectados, construye estado candidate, valida, reconcilia focalmente, publica y recién entonces avanza el watermark. No relee historia completa.

La reconciliación tiene dos niveles dentro del control del UPDATE: `FAST/FOCAL_RECONCILIATION` para documentos, clientes, órdenes o `ItemCode×Warehouse` cambiados; y `PERIODIC_AUTHORITATIVE_RECONCILIATION` para un período, warehouse, grupo o dominio elegido. El segundo detecta drift no capturado por change detection y no crea un modo principal adicional.

`MICRO_BATCH` es unidad lógica de extracción; no implica un archivo Parquet. Se evita la explosión de tiny files y Atomic continúa bajo ownership de DuckLake. Raw soporta ambos modos: `raw/sap/INITIAL` conserva ventanas históricas y `raw/sap/UPDATE` extracciones acotadas; cada manifest registra `ingestion_mode`, ventana, watermark y/o affected keys.

### 28.4. Validity, candidate state and trust

Rige `CORRECTNESS > FRESHNESS > LATENCY`. Para la misma definición, scope y `as_of`, el resultado local debe coincidir con SAP: `SAME_DEFINITION + SAME_SCOPE + SAME_AS_OF = SAME_RESULT_AS_SAP`. Una diferencia temporal explícita puede ser aceptable; una cifra incorrecta para el mismo corte no.

La publicación es fail-closed: `source changes → candidate local state → validation/reconciliation → trusted published state`. `UNVALIDATED DATA MUST NOT BE PUBLISHED AS TRUSTED DATA`. Si falla la validación, no se publica el candidate ni se avanza el watermark; permanece activo el último trusted state, marcado `STALE` o `DIVERGED` según la causa.

Los estados son:

- `AUTHORITATIVE_SYNCED`: último estado publicado y reconciliado contra SAP en su scope y `as_of`; puede servirse como trusted.
- `AUTHORITATIVE_LAGGING`: estado autoritativo validado pero atrasado respecto de la fuente; puede servirse con `data_as_of` y aviso.
- `VALIDATED_DERIVED`: producto derivado validado desde inputs trusted; puede servirse con lineage y `data_as_of`, pero no sustituye la autoridad SAP.
- `STALE`: el atraso supera el SLA de freshness o no existe una actualización válida reciente; serving es restrictivo y siempre declara `data_as_of`.
- `DIVERGED`: la reconciliación detectó diferencia para el mismo contrato; el candidate nuevo no es trusted ni se sirve como válido. Se conserva el último trusted, se registra la divergencia, no se avanza watermark y se ejecuta reconciliación focal/retry.

Toda capa `current` futura debe exponer internamente `data_as_of`, `source_reconciled_at`, `reconciliation_status` y `source_authority`. El estado puede ser por dominio (`sales=SYNCED`, `inventory=LAGGING`, `credit=DIVERGED`) y no se declara reconciliado todo el Data Lake por una verificación parcial.

La respuesta futura respeta el estado: `SYNCED` responde normalmente; `LAGGING` incluye `data_as_of`; `STALE` aplica política restrictiva y aviso; `DIVERGED` no presenta la cifra candidate nueva como válida. No existe fallback silencioso `chat → SAP`.

La tolerancia es cero para identidad, cantidades, conteos de documentos y estados. Los importes sólo admiten la precisión o redondeo técnico propio de SAP cuando esté explícitamente documentado; nunca se usa una tolerancia porcentual genérica.

### 28.5. Watermark, checkpoint and resume

Conceptualmente se distinguen `detected watermark`, `processed watermark`, `validated watermark` y `published/trusted watermark`. El único cursor autoritativo para continuar es el último trusted watermark: `WATERMARK ADVANCES ONLY AFTER SUCCESSFUL VALIDATION AND PUBLICATION`.

`INITIAL_INGESTION` conserva checkpoint preferentemente por ventana/mes; `INCREMENTAL_UPDATE`, por trusted micro-batch/watermark; una reconciliación larga, por scope/range. Un safe abort no hace publicación parcial ni avance de watermark, conserva el trusted state, mantiene válido el checkpoint y preserva la evidencia raw ya completada. Resume desde el último checkpoint confiable, nunca desde cero.

### 28.6. HANA authority and load minimization

`SAP HANA` es la autoridad de valores y fuente READ ONLY, no el runtime de consultas del chat. `NEAR-REAL-TIME` se logra manteniendo estado local validado desde cambios incrementales, no consultando SAP por cada pregunta. `HANA_QUERY_ON_USER_REQUEST=NO`: el chat consulta trusted local state; una excepción administrativa puede ejecutar una verificación focal autorizada READ ONLY, sin convertirla en ruta del chat ni fallback silencioso.

La ingesta recurrente prohíbe full scans, `SELECT *`, joins grandes sin límite, queries por usuario, N+1, polling masivo concurrente, relectura histórica en cada update y workers independientes que escaneen la misma fuente. Requiere columnas mínimas, rangos acotados, keys/change markers, lecturas de objetos afectados, parámetros, timeouts, retry con backoff, lookback controlado, baja concurrencia y reconciliación profunda periódica.

Change detection se separa de authoritative value read. Para stock, por ejemplo, detectar un `ItemCode×Warehouse` cambiado dispara una lectura focal OITW; no se presume que `OITW` se reconstruye siempre como `OINM baseline + eventos`. `OnHand`, `IsCommited`, `OnOrder` y otras métricas mantienen autoridad explícita y su semántica real debe validarse antes de congelar el contrato definitivo. Ventas lee sólo OINV/INV1 afectados; crédito exige reconciliación validada de invoices, credit notes, payments, reconciliations, open balance y due date antes de trusted.

### 28.7. Resource guards and backpressure

Rige `A DATA JOB MAY FAIL. IT MUST NOT TAKE DOWN THE MACHINE`. Todo `INITIAL_INGESTION`, `INCREMENTAL_UPDATE`, reconciliación, rebuild o backfill debe ejecutar preflight y guards continuos. El preflight revisa RAM, swap, load, disk/temp disk, workers, DuckDB, conectividad HANA y concurrencia; los checks se repiten entre chunks, meses, particiones o micro-batches.

Los thresholds son configurables y específicos del entorno; este gate no inventa valores productivos sin benchmark del host. Las categorías mínimas son RAM, SWAP, LOAD, DISK, TEMP_DISK, DUCKDB_MEMORY, DUCKDB_THREADS, WORKERS, HANA_CONCURRENCY, QUERY_TIMEOUT y SPILL. Warning aplica `PAUSE` o `BACKOFF`; critical aplica `SAFE_ABORT` según severidad.

DuckDB debe recibir explícitamente `threads`, `memory_limit`, `temp_directory` y, cuando aplique, `max_temp_directory_size`. El pipeline prefiere DuckDB/PyArrow, streaming y batches acotados; no carga datasets multimillonarios completos en pandas y no incorpora Dask por defecto. `MAX_INGESTION_WORKERS` y `MAX_HANA_CONCURRENT_QUERIES` son configuración explícita y comienzan con concurrencia conservadora. La presión de HANA, máquina, disco, spill o lag reduce velocidad: freshness puede degradarse, correctness no.

`SAFE_ABORT` deja sin publicación parcial, sin watermark advance, activo el último trusted state, checkpoint válido y raw completado preservado. Antes de una carga se estima source, raw, spill, output administrado, manifests y evidencia; temp storage usa un path conocido, monitorizado y con espacio suficiente, no un `/tmp` arbitrario. Una incidencia previa de consumo de recursos que comprometió la máquina motiva este contrato: el consumo sin límite es inaceptable.

### 28.8. Physical layout and operating classes

El layout raw contractual es `raw/sap/INITIAL=<domain>/year=<YYYY>/month=<MM>/extraction=<id>` para backfill y `raw/sap/UPDATE=<domain>/date=<YYYY-MM-DD>/extraction=<id>` o equivalente contractual para update. Las diferencias DEV/PROD viven en configuración y los nombres lógicos son idénticos.

La partición es `NO PARTITION BY DEFAULT`; sólo se adopta con beneficio probado en volumen, pruning, rebuild, mantenimiento o benchmark. Se evitan miles de archivos pequeños, metadata y compaction innecesarios. Las clases `HOT`, `WARM` y `COLD` son candidatos domain-specific (por ejemplo 1–5, 5–15 minutos e histórico programado), no SLAs productivos fijados por este gate. Mientras exista polling/micro-batch se usa `NEAR-REAL-TIME`, no “real-time”.

La futura orquestación puede usar `pg_durable` para estado durable, retries, checkpoints, history y audit, pero este gate no implementa scheduler ni workflow productivo. Los future run records deberán conservar modos, reconciliaciones, fallos, retries, watermarks, duración y eventos de presión de recursos.

## 29. Gate contractual de ingesta y stop condition

Este gate es documental/contractual y deja los contratos machine-readable en `validation/datalake_ingestion_modes_and_resource_guards_contract_v1/`.

```text
GATE=TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1
ARCHITECTURE_UPDATED=YES
ADR_INDEX_UPDATED=YES
INITIAL_INGESTION_DEFINED=YES
INCREMENTAL_UPDATE_DEFINED=YES
RECONCILIATION_AS_UPDATE_CONTROL_DEFINED=YES
SHARED_CANONICAL_TRANSFORMATION=YES
CORRECTNESS_OVER_FRESHNESS_OVER_LATENCY=YES
FAIL_CLOSED_PUBLICATION=YES
CANDIDATE_STATE_SEPARATE_FROM_TRUSTED_STATE=YES
WATERMARK_ADVANCES_AFTER_TRUSTED_PUBLISH_ONLY=YES
TRUST_STATES_DEFINED=YES
DATA_AS_OF_CONTRACT_DEFINED=YES
HANA_IS_SOURCE_AUTHORITY=YES
HANA_IS_CHAT_QUERY_RUNTIME=NO
HANA_QUERY_ON_USER_REQUEST=NO
HANA_FULL_SCAN_POLLING_ALLOWED=NO
HANA_BOUNDED_READS_REQUIRED=YES
HANA_LOW_CONCURRENCY_REQUIRED=YES
HANA_LOAD_MINIMIZATION_MANDATORY=YES
INITIAL_DEFAULT_WORK_UNIT=MONTH
INITIAL_MONTH_EQUALS_ATOMIC_PARQUET_FILE=NO
LIVE_INGESTION_MODE=MICRO_BATCH
MICRO_BATCH_EQUALS_PARQUET_FILE=NO
ATOMIC_FILE_OWNERSHIP=DUCKLAKE
RESOURCE_PREFLIGHT_REQUIRED=YES
RESOURCE_CONTINUOUS_GUARDS_REQUIRED=YES
DUCKDB_MEMORY_LIMIT_REQUIRED=YES
DUCKDB_THREADS_LIMIT_REQUIRED=YES
TEMP_STORAGE_GUARD_REQUIRED=YES
HANA_CONCURRENCY_LIMIT_REQUIRED=YES
BACKPRESSURE_DEFINED=YES
SAFE_ABORT_DEFINED=YES
CHECKPOINT_RESUME_DEFINED=YES
POSTGRES_MODIFIED=NO
DUCKLAKE_MODIFIED=NO
DATA_FILES_MODIFIED=0
SAP_ACCESSED=NO
SAP_WRITE_COUNT=0
RUNTIME_IMPLEMENTED=NO
INGESTION_OPERATIONAL_CONTRACT_READY=YES
TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1_PASS
```

No se inició scheduler, sync continuo, pg_durable workflow, backfill nuevo, business/current build, chat integration ni modificación de SAP, PostgreSQL, DuckLake o datos existentes. La frontera es **STOP AND REVIEW**.

## 30. Segmented execution

Todo trabajo pesado de datos se ejecuta como una orquestación de unidades acotadas. `INITIAL_INGESTION` usa `BOUNDED_SEGMENT`; `INCREMENTAL_UPDATE` usa `BOUNDED_MICRO_BATCH`; reconciliación, rebuild, backfill y dirty reprocessing usan `BOUNDED_SEGMENT`. `LONG_RUNNING_MONOLITHIC_LOADS_ALLOWED=NO` aplica a todos ellos.

Un segmento es la unidad mínima independiente que puede extraer, preservar raw, transformar, validar, reconciliar, publicar y checkpointar. Su contrato futuro incluye `segment_id`, `job_id`, dominio, modo, cobertura, estrategia/rango, budgets de filas/bytes, timeout, perfil de recursos, intento, estados de validación/reconciliación/publicación/checkpoint y `parent_segment_id`. Las estrategias permitidas son `DATE_RANGE`, `DOCENTRY_RANGE`, `TRANSACTION_ID_RANGE`, `KEY_RANGE`, `AFFECTED_KEYS`, `ROW_BUDGET` y `BYTE_BUDGET`.

`SEGMENT_SIZE_CONFIGURABLE=YES` y `SEGMENT_SIZE_ADAPTIVE=YES`: el tamaño depende de dominio, ambiente, densidad de la fuente, respuesta HANA, capacidad de máquina y operación. Ante presión puede reducirse, dividirse, aplicar backoff, pausarse o abortarse de forma segura; nunca aumenta consumo indefinidamente. Un segmento problemático no se publica: se divide en `S1/S2` con la misma semántica e identidades Atomic.

`COVERAGE_MAP_REQUIRED=YES`. La cobertura debe identificar períodos/rangos esperados, trusted, dirty, pendientes, fallidos, divididos, gaps y última reconciliación. Si `S1` y `S2` pasan y `S3` falla, el resume comienza en `S3`, no desde el histórico completo.

## 31. Mutable historical coverage

`HISTORICAL_COVERAGE_MAY_CHANGE_AFTER_INITIAL_INGESTION`. Un período o segmento previamente `TRUSTED` no queda congelado para siempre: puede pasar `TRUSTED → DIRTY → RECONCILING → TRUSTED` o `TRUSTED → DIRTY → DIVERGED`. `CLOSED_FOREVER` no es un supuesto arquitectónico.

La cobertura representa período de negocio; no garantiza que la fuente deje de cambiar. Un cambio SAP observado hoy puede afectar marzo de un año anterior. El sistema marca el scope afectado y conserva el último trusted state hasta que la lectura autoritativa, transformación, validación y reconciliación permitan publicar la corrección.

## 32. Business time versus source change time

**Business time** responde a qué período pertenece el hecho: `DocDate`, posting date, transaction date o snapshot date según dominio. **Change time** responde cuándo SAP creó, modificó o canceló el objeto y puede provenir de update/create date-time, change markers, sequential identifiers u otra señal validada por dominio.

`business_date != source_changed_at` es válido y esperado. Por ejemplo, un documento con `business_date=2026-03-18` puede tener `source_changed_at=2026-09-17T10:32`. `BUSINESS_DATE_ONLY_WATERMARK=FORBIDDEN`: DocDate sirve para coverage/segmentación, pero nunca es la única defensa contra cambios retroactivos. `COVERAGE` (períodos representados) y `CHANGE_WATERMARK` (cambio SAP detectado, procesado, validado y publicado) son conceptos distintos; el segundo puede avanzar hoy por un objeto de 2024.

## 33. Dirty scope and dirty period

`DIRTY_SCOPE` es el alcance mínimo evidence-based que requiere reparación. Puede ser un documento, líneas de documento, `ItemCode×Warehouse`, transaction range, cliente, business-day range, mes u otro scope autorizado por el dominio. `DIRTY_PERIOD` es una agregación operativa útil para visualizar el período afectado, no una orden automática de recargarlo completo.

HISTORICAL_CHANGE_DETECTED DOES NOT AUTOMATICALLY REQUIRE FULL_MONTH_RELOAD. La secuencia preferida es `changed object/key → bounded authoritative reread → bounded rebuild → reconciliation → publish`. Sólo se escala al período completo cuando la semántica de la fuente o la evidencia de reconciliación lo exige. Un cambio en `OINV DocEntry X` con `DocDate=2026-03-18` ensucia el scope del documento y marzo como agregado, relee factura y líneas, valida y limpia el scope; no deja marzo permanentemente incorrecto ni recarga el mes por defecto.

## 34. Historical reconciliation

La reconciliación es parte del modelo de actualización y siempre es segmentada. Después de cada update se compara el objeto afectado contra la autoridad SAP; identity, quantity, document count y state/status requieren tolerancia cero. Amount sólo admite precisión/redondeo explícitamente documentado.

Además del control focal se ejecuta un loop histórico periódico, también segmentado: seleccionar un segmento pequeño, comparar SAP ↔ Data Lake, conservar `TRUSTED` si coincide, marcar `DIRTY` si diverge, reparar bounded, reconciliar y publicar. La frecuencia queda domain-specific y depende de antigüedad, criticidad, frecuencia de cambios y carga HANA; los períodos antiguos pueden revisarse menos, pero no se asumen inmutables sin garantía real.

## 35. Watermark semantics and fail-closed publication

Se separan `business_time`, `change_time`, `coverage_watermark` y `change_watermark`. Un watermark sólo avanza después de `extract → transform → validate → reconcile → trusted publish`. La detección o extracción por sí sola nunca lo mueve.

`WATERMARK_CAN_SKIP_DIRTY_GAP=NO`: un watermark reciente no oculta dirty scopes, gaps, segmentos fallidos ni cobertura histórica divergente. Si falla un segmento, no publica candidate data, no avanza el trusted watermark y mantiene el último trusted state. `DIRTY` describe estado de cobertura/scope; no agrega un trust state de respuesta que sustituya `AUTHORITATIVE_SYNCED`, `AUTHORITATIVE_LAGGING`, `VALIDATED_DERIVED`, `STALE` o `DIVERGED`.

## 36. HANA load and physical contracts

`HANA_LOAD_MINIMIZATION=MANDATORY`. Las lecturas recurrentes son bounded, parametrizadas, de columnas mínimas, baja concurrencia y timeout protegido. `HANA_FULL_SCAN_POLLING_ALLOWED=NO` y `HANA_QUERY_ON_USER_REQUEST=NO`; near-real-time proviene de ingesta compartida incremental, no de consultas por usuario ni scans completos recurrentes.

Raw SAP puede conservar extracciones por segmento y su manifest relaciona `job_id`, `segment_id`, `extraction_id`, modo, cobertura business, change watermark y affected keys. `SEGMENT != PARQUET FILE`, `MONTH != PARQUET FILE` y `MICRO_BATCH != PARQUET FILE`. Atomic continúa bajo `DUCKLAKE_MANAGED`; la segmentación no cambia ownership ni semántica de `ATOMIC_ID`. Raw evidence anterior, manifests y snapshots técnicos no se borran cuando SAP corrige un hecho.

## 37. Future durable operational state

El diseño futuro debe poder persistir jobs, segments, coverage, dirty scopes, watermarks, reconciliations, resource events y retry history. `pg_durable` es candidato preferido para job state, segment state, checkpoints, retries e history, pero este gate no lo implementa ni crea scheduler, poller, executor, detector o worker.

DEV y PROD mantienen los mismos nombres lógicos; diferencias de máquina, fuente, límites y paths viven en configuración. Este gate documenta requisitos runtime enforced, no los implementa.

## 38. Segmented mutable-history gate output

```text
GATE=TELCHI_DATALAKE_SEGMENTED_INGESTION_MUTABLE_HISTORY_CONTRACT_V1
ARCHITECTURE_UPDATED=YES
ADR_INDEX_UPDATED=YES
INITIAL_INGESTION_DEFINED=YES
INCREMENTAL_UPDATE_DEFINED=YES
LONG_RUNNING_MONOLITHIC_LOADS_ALLOWED=NO
INITIAL_COVERAGE_UNIT=MONTH
INITIAL_EXECUTION_UNIT=BOUNDED_SEGMENT
MONTH_EQUALS_SINGLE_EXECUTION=NO
INCREMENTAL_EXECUTION_UNIT=BOUNDED_MICRO_BATCH
RECONCILIATION_EXECUTION_UNIT=BOUNDED_SEGMENT
REBUILD_EXECUTION_UNIT=BOUNDED_SEGMENT
SEGMENT_SIZE_CONFIGURABLE=YES
SEGMENT_SIZE_ADAPTIVE=YES
SEGMENT_SPLIT_SUPPORTED=YES
BUSINESS_TIME_SEPARATE_FROM_CHANGE_TIME=YES
BUSINESS_DATE_ONLY_WATERMARK_ALLOWED=NO
HISTORICAL_PERIODS_MUTABLE=YES
TRUSTED_PERIOD_CAN_BECOME_DIRTY=YES
DIRTY_SCOPE_DEFINED=YES
DIRTY_SCOPE_CAN_BE_SMALLER_THAN_MONTH=YES
FULL_MONTH_RELOAD_IS_DEFAULT=NO
COVERAGE_MAP_REQUIRED=YES
OLD_PERIOD_CHANGE_DETECTION_SUPPORTED=YES
RETROACTIVE_CHANGE_REPROCESSING_DEFINED=YES
PERIODIC_HISTORICAL_RECONCILIATION_DEFINED=YES
WATERMARK_ADVANCES_AFTER_TRUSTED_PUBLISH_ONLY=YES
FAILED_SEGMENT_ADVANCES_WATERMARK=NO
WATERMARK_CAN_SKIP_DIRTY_GAP=NO
CORRECTNESS_OVER_FRESHNESS_OVER_LATENCY=YES
HANA_QUERY_ON_USER_REQUEST=NO
HANA_FULL_SCAN_POLLING_ALLOWED=NO
HANA_BOUNDED_READS_REQUIRED=YES
HANA_LOAD_MINIMIZATION_MANDATORY=YES
RESOURCE_GUARDS_PER_SEGMENT=YES
SAFE_ABORT_PER_SEGMENT=YES
CHECKPOINT_RESUME_PER_SEGMENT=YES
SEGMENT_EQUALS_PARQUET_FILE=NO
MONTH_EQUALS_ATOMIC_PARQUET_FILE=NO
MICRO_BATCH_EQUALS_PARQUET_FILE=NO
ATOMIC_FILE_OWNERSHIP=DUCKLAKE
RUNTIME_IMPLEMENTED=NO
SAP_ACCESSED=NO
SAP_WRITE_COUNT=0
POSTGRES_MODIFIED=NO
DUCKLAKE_MODIFIED=NO
DATA_FILES_MODIFIED=0
SEGMENTED_MUTABLE_HISTORY_CONTRACT_READY=YES
TELCHI_DATALAKE_SEGMENTED_INGESTION_MUTABLE_HISTORY_CONTRACT_V1_PASS
```

No scheduler, backfill, HANA query, runtime executor, change detector, reconciliation worker, adaptive sizing, pg_durable workflow, Atomic rebuild ni modificación de PostgreSQL, DuckLake, Data Root, raw, reference o datos fue realizada. **STOP AND REVIEW**.
