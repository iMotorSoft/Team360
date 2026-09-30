# TELCHI Data Lake ADR Index V1

Este índice registra decisiones arquitectónicas vigentes y breves. La explicación amplia vive en [TELCHI_DATALAKE_ARCHITECTURE_V1.md](TELCHI_DATALAKE_ARCHITECTURE_V1.md); los gates enlazados conservan la evidencia histórica.

## Registry rules

Un ADR `ACCEPTED` permanece vigente hasta que otro ADR lo sustituya. Un cambio requiere ADR nuevo, rationale explícito, `Supersedes` en el nuevo y estado `SUPERSEDED` más `Superseded by` en el anterior.

Los estados permitidos son `ACCEPTED`, `PROVISIONAL`, `SUPERSEDED` y `DEFERRED`. La fecha `2026-09-16` es la fecha de esta consolidación, no una fecha histórica inferida.

## ADR-001 — Greenfield architecture

Telchi se diseña como sistema nuevo y usa legacy sólo como evidencia.

| Field | Value |
| --- | --- |
| ADR ID | ADR-001 |
| Title | Greenfield architecture |
| Status | ACCEPTED |
| Decision | Diseñar Telchi GREENFIELD sin migrar por defecto la arquitectura DataScience legacy. |
| Rationale | Los requisitos actuales de lineage, seguridad, versioning y operación no deben quedar condicionados por patrones históricos. |
| Consequences | No se heredan Tornado, Dask per request, ArangoDB, hardcodes, credenciales, handlers, naming ni modelos físicos legacy. |
| Evidence / source gates | `TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS`; `TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-002 — Parquet, DuckLake, DuckDB and PostgreSQL 18

El stack separa storage, metadata, ejecución y catálogo.

| Field | Value |
| --- | --- |
| ADR ID | ADR-002 |
| Title | Parquet + DuckLake + DuckDB + PostgreSQL 18 |
| Status | ACCEPTED |
| Decision | Usar Parquet para storage, DuckLake para administración lakehouse, DuckDB para ejecución y PostgreSQL 18 como backend de catálogo. |
| Rationale | La separación permite analytics rápido, snapshots técnicos y metadata transaccional sin convertir PostgreSQL en warehouse. |
| Consequences | Cada componente conserva una responsabilidad explícita y Team360 opera por encima del stack. |
| Evidence / source gates | `TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS`; `TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-003 — PostgreSQL is catalog, not warehouse

PostgreSQL conserva metadata DuckLake, no hechos analíticos.

| Field | Value |
| --- | --- |
| ADR ID | ADR-003 |
| Title | PostgreSQL is catalog, not warehouse |
| Status | ACCEPTED |
| Decision | `team360_telchi_ducklake` contiene metadata DuckLake en `public`; los hechos analíticos permanecen en Parquet administrado. |
| Rationale | El foundation validó DuckLake 1.0 con database dedicada y Data Path físico. |
| Consequences | No se describirá ni usará PostgreSQL como Data Warehouse Telchi. |
| Evidence / source gates | `TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-004 — Raw immutable and derived rebuildable

La fuente preservada y los productos derivados tienen ciclos de vida distintos.

| Field | Value |
| --- | --- |
| ADR ID | ADR-004 |
| Title | Raw immutable / derived rebuildable |
| Status | ACCEPTED |
| Decision | Raw es inmutable; reference/crosswalk derivados, atomic, business, current y ops deben ser reconstruibles. |
| Rationale | La separación preserva evidencia y permite corregir transforms sin alterar la fuente. |
| Consequences | Raw no se reescribe, compacta ni limpia automáticamente; derivados registran inputs y versiones. |
| Evidence / source gates | `TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS`; `TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-005 — Same logical names in DEV and PROD

Los entornos difieren por infraestructura, no por nombres lógicos.

| Field | Value |
| --- | --- |
| ADR ID | ADR-005 |
| Title | Same logical names DEV and PROD |
| Status | ACCEPTED |
| Decision | DEV y PROD usan `team360_telchi_ducklake` como database y role lógicos, sin sufijos `_dev` o `_prod`. |
| Rationale | La paridad evita configuración y código divergentes. |
| Consequences | Host, instancia, network, secrets, filesystem y environment config deben aislar entornos; compartir cluster sería un conflicto de infraestructura. |
| Evidence / source gates | `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED`; `TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-006 — Security before retrieval

La autorización limita el scan antes de acceder a hechos.

| Field | Value |
| --- | --- |
| ADR ID | ADR-006 |
| Title | Security before retrieval |
| Status | ACCEPTED |
| Decision | Resolver identity, permissions y allowed scope antes de entity resolution y query de datos. |
| Rationale | Ocultar después de leer o responder no protege filas, columnas, métricas ni scope organizacional. |
| Consequences | Registry, semantic planner, DuckDB y drill-down deben fallar cerrados y aplicar filtros previos. |
| Evidence / source gates | `TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS`; `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-007 — Atomic truth separated from business semantics

Atomic preserva hechos sin congelar interpretaciones ambiguas.

| Field | Value |
| --- | --- |
| ADR ID | ADR-007 |
| Title | Atomic truth separated from business semantics |
| Status | ACCEPTED |
| Decision | Separar hechos atomic reconstruibles de métricas y read models business versionados. |
| Rationale | Cash/credit, net sales, costo, FX, tax y producción aún tienen gaps que no deben contaminar hechos. |
| Consequences | Atomic conserva evidencia suficiente; business puede evolucionar y reconstruirse sin reextraer o mutar raw. |
| Evidence / source gates | `TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS`; `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-008 — Prepared business and current read models

Las cargas ejecutivas usan productos preparados y no reconstrucción completa por request.

| Field | Value |
| --- | --- |
| ADR ID | ADR-008 |
| Title | Prepared business/current read models for CEO workloads |
| Status | ACCEPTED |
| Decision | Enrutar preguntas normales a business/current read models; usar atomic para truth, drill-down, reconciliación y análisis profundo. |
| Rationale | El patrón reduce joins repetidos y sostiene los targets de latencia. |
| Consequences | `sales_flow`, `stock_current`, crédito, producción, compras e inventario requieren builds trazables y freshness. |
| Evidence / source gates | `TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS`; `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-009 — Legacy is baseline only

Legacy informa el sistema nuevo, pero no lo gobierna.

| Field | Value |
| --- | --- |
| ADR ID | ADR-009 |
| Title | Legacy is semantic/performance baseline only |
| Status | ACCEPTED |
| Decision | Usar DataScience legacy como evidencia semántica, casos de negocio, relaciones históricas y baseline de performance. |
| Rationale | Parquet enriquecido demostró velocidad, pero su implementación carece de contratos modernos suficientes. |
| Consequences | Se conserva el principio de read models rápidos sin copiar la arquitectura legacy. |
| Evidence / source gates | `TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS`; `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-010 — Metric semantic versioning

Las definiciones de métricas son contratos versionados.

| Field | Value |
| --- | --- |
| ADR ID | ADR-010 |
| Title | Metric semantic versioning |
| Status | ACCEPTED |
| Decision | Identificar cada métrica como `metric_id + semantic_version`, por ejemplo `NET_SALES@1`. |
| Rationale | Una fórmula no puede reinterpretar silenciosamente resultados históricos. |
| Consequences | Cambios de definición crean versión nueva y traces registran la versión usada. |
| Evidence / source gates | `TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS`; `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-011 — Technical snapshot differs from business historical state

Versionar archivos no define por sí solo un estado empresarial as-of.

| Field | Value |
| --- | --- |
| ADR ID | ADR-011 |
| Title | DuckLake technical snapshot != business historical state |
| Status | ACCEPTED |
| Decision | Tratar snapshots DuckLake como versiones técnicas y estados business as-of como reconstrucciones semánticas independientes. |
| Rationale | Deuda, stock y estados documentales requieren fechas y reglas de dominio. |
| Consequences | “Deuda al 31/08” no puede responderse sólo seleccionando un snapshot técnico. |
| Evidence / source gates | `TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS`; `TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1_PASS`; `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-012 — LLM does not calculate business numbers

El cálculo pertenece al motor analítico y a contratos versionados.

| Field | Value |
| --- | --- |
| ADR ID | ADR-012 |
| Title | LLM does not calculate business numbers |
| Status | ACCEPTED |
| Decision | Usar el LLM para intención, contexto y explicación; usar SQL/DuckDB para cálculos. |
| Rationale | Un LLM no es autoridad para sumas, joins, conversiones, FX, tax, aliases, métricas o scope. |
| Consequences | Toda cifra se deriva de una query autorizada y trazable. |
| Evidence / source gates | `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-013 — Canonical IDs and evidence-based aliases

La resolución de entidades prioriza identidad estable y evidencia.

| Field | Value |
| --- | --- |
| ADR ID | ADR-013 |
| Title | Canonical IDs and evidence-based aliases |
| Status | ACCEPTED |
| Decision | Resolver canonical IDs primero y aceptar sólo aliases observados o aprobados con evidencia. |
| Rationale | Los nombres pueden colisionar, cambiar o no resolver. |
| Consequences | Ambigüedades conservan candidatos; “Segundo Anillo” sigue unresolved hasta evidencia. |
| Evidence / source gates | `TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-014 — Warehouse and branch are distinct

Almacén y sucursal no son sinónimos ni tienen relación necesariamente 1:1.

| Field | Value |
| --- | --- |
| ADR ID | ADR-014 |
| Title | Warehouse and branch are distinct entities |
| Status | ACCEPTED |
| Decision | Modelar warehouse y branch por separado con mapping versionable y estados mapped, unmapped o temporal unknown. |
| Rationale | La evidencia actual no demuestra vigencia histórica ni equivalencia universal. |
| Consequences | Branch puede ser null/unknown y nunca se proyecta hacia el pasado sin evidencia. |
| Evidence / source gates | `TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS`; `TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-015 — L-products priority universe

Los productos L tienen prioridad operacional cuando el dominio lo requiere.

| Field | Value |
| --- | --- |
| ADR ID | ADR-015 |
| Title | L-products are priority universe for Telchi operational analysis |
| Status | ACCEPTED |
| Decision | Priorizar `ItemCode LIKE 'L%'` en stock, replenishment, sales, MRP, capacity y policy cuando aplique. |
| Rationale | El universo tiene flag canónico y evidencia de uso prioritario en investigaciones Telchi. |
| Consequences | La mezcla con no-L exige control explícito; la prioridad no se convierte en exclusión universal silenciosa. |
| Evidence / source gates | `TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED`; `TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-016 — Semantic gaps remain explicit

Una ambigüedad no se resuelve por conveniencia técnica.

| Field | Value |
| --- | --- |
| ADR ID | ADR-016 |
| Title | Semantic gaps remain explicit, not guessed |
| Status | ACCEPTED |
| Decision | Mantener cash/credit, net sales, production count, cost, FX y tax como gaps hasta evidencia suficiente. |
| Rationale | Adivinar cambia cifras y decisiones empresariales sin reconciliación. |
| Consequences | Los hechos pueden avanzar si preservan evidencia; ciertas métricas business no se congelan. |
| Evidence / source gates | `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-017 — Dedicated non-superuser runtime role

El catálogo opera con privilegios mínimos separados del provisioning.

| Field | Value |
| --- | --- |
| ADR ID | ADR-017 |
| Title | PostgreSQL/DuckLake runtime uses dedicated non-superuser role |
| Status | ACCEPTED |
| Decision | Usar `team360_telchi_ducklake` como role runtime dedicado, no superuser, sin create database ni create role. |
| Rationale | Reduce blast radius y separa administración de operación normal. |
| Consequences | Provisioning administrativo permanece fuera del runtime y los secretos fuera de Git. |
| Evidence / source gates | `TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-018 — Raw legacy is never DuckLake-owned

El mirror histórico permanece como fuente preservada externa.

| Field | Value |
| --- | --- |
| ADR ID | ADR-018 |
| Title | Raw legacy is never DuckLake-owned |
| Status | ACCEPTED |
| Decision | Mantener `raw/legacy` fuera del ownership y de las operaciones de lifecycle DuckLake. |
| Rationale | Sus 696 archivos son evidencia byte-identical y no productos administrados. |
| Consequences | No add-data-files, compaction, expiration, rewrite ni cleanup DuckLake sobre raw legacy. |
| Evidence / source gates | `TELCHI_DATALAKE_LEGACY_PARQUET_MIRROR_V1_PASS`; `TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-019 — Performance is an architectural contract

La latencia se diseña y valida, no se trata como optimización tardía.

| Field | Value |
| --- | --- |
| ADR ID | ADR-019 |
| Title | Performance is an architectural contract |
| Status | ACCEPTED |
| Decision | Aplicar targets warm P95 A `100 ms`, B `300 ms`, C `750 ms`; deep analysis no requiere sub-second. |
| Rationale | Los workloads ejecutivos necesitan fast paths predecibles y medibles. |
| Consequences | Las métricas son data-query-only, se evita ATTACH por pregunta y se priorizan read models. |
| Evidence / source gates | `TELCHI_DUCKLAKE_POSTGRES18_FOUNDATION_V1_PASS`; `TELCHI_DATALAKE_CEO_QUERY_SEMANTICS_AND_PERFORMANCE_CONTRACT_V1_DEGRADED` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-020 — Atomic follows business truth

El núcleo atomic no replica el schema físico de SAP.

| Field | Value |
| --- | --- |
| ADR ID | ADR-020 |
| Title | Atomic is driven by business truth, not SAP table mirroring |
| Status | ACCEPTED |
| Decision | Diseñar entidades atomic por grain y verdad de negocio, preservando native identities y lineage SAP. |
| Rationale | Una tabla SAP puede mezclar responsabilidades y una verdad puede requerir varias tablas y relaciones. |
| Consequences | Atomic Core define entidades como documentos, líneas, movimientos, pagos y reconciliaciones, no copias 1:1. |
| Evidence / source gates | `TELCHI_SAP_KNOWLEDGE_INVENTORY_V1_DEGRADED`; `TELCHI_DATALAKE_CANONICAL_MODEL_AND_LINEAGE_V1_PASS`; `TELCHI_DATALAKE_PHYSICAL_PARQUET_DESIGN_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-021 — Separate product operating concepts

Marca, unidad de negocio, modelo operativo, canal y sitio productivo representan ejes semánticos distintos.

| Field | Value |
| --- | --- |
| ADR ID | ADR-021 |
| Title | Separate Brand, Business Unit, Operating Model, Channel and Production Site |
| Status | ACCEPTED |
| Decision | Modelar brand, business unit, operating model, sales/distribution channel y production site como conceptos distintos, sin inferir equivalencia entre ellos. |
| Rationale | Cada eje responde una pregunta diferente de identidad, organización, transformación, comercialización o ubicación física. |
| Consequences | `RETAIL` no se fija como canal o business unit sin evidencia; `is_telchi_product` e `is_l_product` tampoco sustituyen esos conceptos. |
| Evidence / source gates | `TELCHI_DATALAKE_PRODUCT_OPERATING_MODEL_AND_STABLE_SCHEMA_CONTRACT_V1` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-022 — Production site differs from warehouse

El sitio de transformación física y la ubicación logística de inventario requieren identidades y relaciones propias.

| Field | Value |
| --- | --- |
| ADR ID | ADR-022 |
| Title | Production Site Is Distinct From Warehouse |
| Status | ACCEPTED |
| Decision | Modelar production site separado de warehouse y permitir que un sitio se relacione con múltiples warehouses. |
| Rationale | Fabricación, fraccionamiento o acondicionamiento no equivalen al rol logístico del inventario. |
| Consequences | No se asume 1:1; producto–sitio usa relación temporal evidence-based y warehouses pueden tener roles diferentes. |
| Evidence / source gates | `TELCHI_DATALAKE_PRODUCT_OPERATING_MODEL_AND_STABLE_SCHEMA_CONTRACT_V1` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-023 — Product operating classification is evidence-based

Las clasificaciones operativas no se deducen de convenciones de naming aisladas.

| Field | Value |
| --- | --- |
| ADR ID | ADR-023 |
| Title | Product Operating Classification Must Be Evidence-Based |
| Status | ACCEPTED |
| Decision | No inferir fabricación, fraccionamiento, marca, business unit o sitio productivo únicamente desde `ItemCode`, prefijos o nombres. |
| Rationale | La regla histórica L identifica una familia prioritaria, pero no demuestra los demás atributos operativos. |
| Consequences | Mappings desconocidos quedan `UNMAPPED`, `AMBIGUOUS` o `PROVISIONAL`; las queries consumen atributos canónicos materializados. |
| Evidence / source gates | `TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1_PASS`; `TELCHI_DATALAKE_PRODUCT_OPERATING_MODEL_AND_STABLE_SCHEMA_CONTRACT_V1` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-024 — Business unit taxonomy

El concepto es estable, pero el vocabulario organizacional todavía requiere validación del negocio.

| Field | Value |
| --- | --- |
| ADR ID | ADR-024 |
| Title | Business Unit Taxonomy |
| Status | PROVISIONAL |
| Decision | Aceptar `business_unit` como concepto canónico y diferir su taxonomía concreta hasta contar con evidencia organizacional. |
| Rationale | Valores candidatos como LITEL, MEDI, RETAIL o MANUFACTURING podrían mezclar familias, canales y organización. |
| Consequences | No se cargan valores especulativos ni se congela una relación producto–business unit sin fuente, confianza y temporalidad apropiadas. |
| Evidence / source gates | `TELCHI_DATALAKE_PRODUCT_OPERATING_MODEL_AND_STABLE_SCHEMA_CONTRACT_V1` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-025 — Stable schema and extensible reference data

La evolución normal del negocio ocurre por contenido y relaciones versionadas, no por columnas nuevas para cada categoría.

| Field | Value |
| --- | --- |
| ADR ID | ADR-025 |
| Title | Stable Canonical Schema, Extensible Reference Data |
| Status | ACCEPTED |
| Decision | Preferir evolución mediante contenido de catálogos y relaciones versionadas; reservar cambios de schema para conceptos semánticos genuinamente nuevos. |
| Rationale | Una taxonomía variable no debe obligar a migrar hechos ni proliferar flags booleanos, y tampoco justifica un EAV genérico. |
| Consequences | Conceptos estables usan IDs y relaciones explícitas; DuckLake schema evolution queda como herramienta controlada, no como configuración normal del negocio. |
| Evidence / source gates | `TELCHI_DATALAKE_PRODUCT_OPERATING_MODEL_AND_STABLE_SCHEMA_CONTRACT_V1`; `TELCHI_DATALAKE_PRODUCT_AND_OPERATING_MODEL_CONTRACT_V2` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

V2 refuerza ADR-025: las nuevas clasificaciones se incorporan por reference content y relaciones versionadas antes que por columnas. No se crea un ADR-030 redundante.

## ADR-026 — Telchi Product, Manufacturing and Brand Ownership Are Distinct

| Field | Value |
| --- | --- |
| ADR ID | ADR-026 |
| Title | Telchi Product, Manufacturing and Brand Ownership Are Distinct |
| Status | ACCEPTED |
| Decision | Tratar `is_telchi_product`, `manufactured_by_telchi` y `brand_owned_by_telchi` como predicados semánticamente independientes, preferentemente derivados de relaciones autoritativas. |
| Rationale | Fabricación, propiedad comercial y pertenencia al portfolio Telchi responden preguntas distintas; white-label demuestra que no son equivalentes. |
| Consequences | Los flags no son fuente primaria universal y pueden materializarse sólo en read models; la definición comercial de producto Telchi queda como gap. |
| Evidence / source gates | `TELCHI_DATALAKE_PRODUCT_AND_OPERATING_MODEL_CONTRACT_V2` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-027 — Contract Manufacturing and White-Label Belong to Industrial Production

| Field | Value |
| --- | --- |
| ADR ID | ADR-027 |
| Title | Contract Manufacturing and White-Label Belong to Industrial Production |
| Status | ACCEPTED |
| Decision | Modelar producción para terceros y white-label dentro de industrial manufacturing mediante arrangements, parties y brand ownership independientes. |
| Rationale | Ambos requieren fórmula/BOM, órdenes, componentes, costos, lotes, sitios y trazabilidad industrial; white-label agrega marca de tercero. |
| Consequences | Atomic preservará customer tercero y evidencia industrial sin convertir white-label en flag estructural ni inferir manufacturer, brand owner o seller. |
| Evidence / source gates | `TELCHI_DATALAKE_PRODUCT_AND_OPERATING_MODEL_CONTRACT_V2` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-028 — Magistral Compounding Belongs to Pharmacy/Botica, Not Industrial Production

| Field | Value |
| --- | --- |
| ADR ID | ADR-028 |
| Title | Magistral Compounding Belongs to Pharmacy/Botica, Not Industrial Production |
| Status | ACCEPTED |
| Decision | Modelar cada preparación magistral como hecho de botica separado de órdenes, BOM, consumos y receipts industriales. |
| Rationale | Es una preparación puntual para cliente y droga/preparación, no producción industrial repetitiva ni white-label. |
| Consequences | Se distingue `magistral_preparation` de `industrial_formula/BOM`, se minimiza PII y una evaluación incompleta declara `PARTIAL_ECONOMIC_EVALUATION`. |
| Evidence / source gates | `TELCHI_DATALAKE_PRODUCT_AND_OPERATING_MODEL_CONTRACT_V2` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-029 — Portfolio Family and Product Business Type Are Independent Dimensions

| Field | Value |
| --- | --- |
| ADR ID | ADR-029 |
| Title | Portfolio Family and Product Business Type Are Independent Dimensions |
| Status | ACCEPTED |
| Decision | Usar `portfolio_family` para medicamentos versus Litel y `product_business_type` para elaborados, materias primas y fracciones, separadas de brand y business unit. |
| Rationale | Los dos niveles responden preguntas ejecutivas diferentes y no deben colapsar clasificación comercial con organización. |
| Consequences | `product_family` y `commercial_family` son aliases deprecados; las taxonomías concretas permanecen provisionales y evidence-based. |
| Evidence / source gates | `TELCHI_DATALAKE_PRODUCT_AND_OPERATING_MODEL_CONTRACT_V2` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-030 — Two Ingestion Modes: Initial and Incremental Update

Esta decisión separa la construcción del baseline de su mantenimiento sin duplicar la semántica canónica.

| Field | Value |
| --- | --- |
| ADR ID | ADR-030 |
| Title | Two Ingestion Modes: Initial and Incremental Update |
| Status | ACCEPTED |
| Decision | Telchi distingue `INITIAL_INGESTION` de `INCREMENTAL_UPDATE`; reconciliación es control interno del UPDATE y ambos comparten schemas, transformaciones y validaciones canónicas. |
| Rationale | Backfill acotado y sincronización incremental tienen selección de fuente, ventanas y cursores distintos, pero no deben producir verdades incompatibles. |
| Consequences | `MONTH` es unidad preferida del baseline y `MICRO_BATCH` unidad lógica del update; ninguno obliga un archivo Atomic por unidad. |
| Evidence / source gates | `TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-031 — Correctness Over Freshness Over Latency

La exactitud reconciliada tiene prioridad sobre el atraso o la velocidad de publicación.

| Field | Value |
| --- | --- |
| ADR ID | ADR-031 |
| Title | Correctness Over Freshness Over Latency |
| Status | ACCEPTED |
| Decision | Sólo datos validados pueden promoverse a trusted; freshness puede degradarse, correctness no. Para igual definición, scope y `as_of`, el resultado local debe coincidir con SAP. |
| Rationale | Una cifra incorrecta es más dañina que un dato explícitamente atrasado. |
| Consequences | Se exponen `data_as_of` y estado de reconciliación; candidate state fallido no se publica. |
| Evidence / source gates | `TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-032 — SAP HANA Is Source Authority, Not Query Runtime

SAP conserva autoridad de valores y el Data Lake desacopla las preguntas de usuario.

| Field | Value |
| --- | --- |
| ADR ID | ADR-032 |
| Title | SAP HANA Is Source Authority, Not Query Runtime |
| Status | ACCEPTED |
| Decision | HANA es fuente READ ONLY para extracción y reconciliación; el chat nunca consulta HANA por pregunta y sirve trusted local state. |
| Rationale | La carga debe depender de cambios reales y no de usuarios, chats o dashboards. |
| Consequences | Full-scan polling, N+1, queries por usuario y fallback silencioso a SAP quedan prohibidos; una verificación administrativa focal READ ONLY es excepción controlada. |
| Evidence / source gates | `TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-033 — Fail-Closed Data Publication

La promoción a trusted requiere validación y reconciliación exitosas.

| Field | Value |
| --- | --- |
| ADR ID | ADR-033 |
| Title | Fail-Closed Data Publication |
| Status | ACCEPTED |
| Decision | Ante divergence o validation failure no se publica candidate state ni avanza watermark; permanece el último trusted state y se activa reconciliación/retry. |
| Rationale | Avanzar el cursor antes de publicar produciría pérdida silenciosa y ocultaría divergencias de SAP. |
| Consequences | Trust states diferencian synced, lagging, derived, stale y diverged; el nuevo dato divergente no puede servirse como válido. |
| Evidence / source gates | `TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-034 — Resource-Guarded Data Workloads

La ingesta debe proteger simultáneamente el host, DuckDB, almacenamiento temporal y HANA.

| Field | Value |
| --- | --- |
| ADR ID | ADR-034 |
| Title | Resource-Guarded Data Workloads |
| Status | ACCEPTED |
| Decision | Todo job pesado usa límites configurables, preflight, checks continuos, baja concurrencia, backpressure, checkpoints y safe abort. |
| Rationale | Un proceso previo comprometió la máquina; el consumo sin límites es una falla arquitectónica, no una cuestión de disciplina operativa. |
| Consequences | Warning pausa o aplica backoff; critical aborta limpiamente, preserva el último trusted state y permite resume sin repetir todo el histórico. |
| Evidence / source gates | `TELCHI_DATALAKE_INGESTION_MODES_AND_RESOURCE_GUARDS_CONTRACT_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-035 — All Heavy Data Workloads Use Bounded Segments

Los trabajos pesados no se ejecutan como cargas monolíticas de larga duración.

| Field | Value |
| --- | --- |
| ADR ID | ADR-035 |
| Title | All Heavy Data Workloads Use Bounded Segments |
| Status | ACCEPTED |
| Decision | Initial, update, rebuild, backfill y reconciliation son orquestaciones de segmentos bounded, checkpointed y resource-guarded; `LONG_RUNNING_MONOLITHIC_LOADS_ALLOWED=NO`. |
| Rationale | Un fallo debe aislarse a un segmento y permitir resume sin repetir el histórico ni comprometer la máquina. |
| Consequences | El tamaño es configurable/adaptativo, puede dividirse sin cambiar semántica y una unidad lógica no implica un archivo Parquet. |
| Evidence / source gates | `TELCHI_DATALAKE_SEGMENTED_INGESTION_MUTABLE_HISTORY_CONTRACT_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-036 — Historical Business Periods Remain Mutable

La cobertura trusted no congela para siempre la historia de SAP.

| Field | Value |
| --- | --- |
| ADR ID | ADR-036 |
| Title | Historical Business Periods Remain Mutable |
| Status | ACCEPTED |
| Decision | Un período histórico previamente trusted puede pasar a `DIRTY` cuando SAP registra posteriormente un cambio que afecta ese período. |
| Rationale | La experiencia operativa de Telchi demuestra que meses históricos pueden modificarse después de su carga inicial. |
| Consequences | Coverage map, dirty scopes y reconciliación periódica son obligatorios; no se usa `CLOSED_FOREVER`. |
| Evidence / source gates | `TELCHI_DATALAKE_SEGMENTED_INGESTION_MUTABLE_HISTORY_CONTRACT_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-037 — Business Time and Source Change Time Are Separate

La fecha de negocio y el momento de modificación de la fuente tienen funciones distintas.

| Field | Value |
| --- | --- |
| ADR ID | ADR-037 |
| Title | Business Time and Source Change Time Are Separate |
| Status | ACCEPTED |
| Decision | La sincronización incremental debe rastrear change-time de SAP independientemente de DocDate/posting date/business time; `BUSINESS_DATE_ONLY_WATERMARK=FORBIDDEN`. |
| Rationale | Un cambio observado hoy puede afectar un período antiguo y no debe descartarse por ser anterior al watermark de negocio. |
| Consequences | Coverage y change watermark avanzan y se auditan por separado; las señales de change time son domain-specific y validadas. |
| Evidence / source gates | `TELCHI_DATALAKE_SEGMENTED_INGESTION_MUTABLE_HISTORY_CONTRACT_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## ADR-038 — Dirty Scope Is Reprocessed at the Smallest Authoritative Grain

Una modificación histórica se repara focalmente antes de escalar.

| Field | Value |
| --- | --- |
| ADR ID | ADR-038 |
| Title | Dirty Scope Is Reprocessed at the Smallest Authoritative Grain |
| Status | ACCEPTED |
| Decision | Los cambios históricos disparan reprocessing bounded en el menor grain autoritativo posible, no una recarga automática del mes completo. |
| Rationale | La relectura focal minimiza carga HANA, reduce tiempo y conserva correctness sin dejar dirty la cobertura afectada. |
| Consequences | `DIRTY_SCOPE` puede ser documento, líneas, key compuesto, rango u otro alcance evidence-based; el período completo sólo es escalamiento explícito. |
| Evidence / source gates | `TELCHI_DATALAKE_SEGMENTED_INGESTION_MUTABLE_HISTORY_CONTRACT_V1_PASS` |
| Supersedes | None |
| Superseded by | None |
| Date | 2026-09-16 |

## Current registry summary

El total se calcula desde el registry machine-readable real; no se crean ADRs para alcanzar un número.

```text
ADR_TOTAL=38
ADR_ACCEPTED=37
ADR_PROVISIONAL=1
ADR_DEFERRED=0
ADR_SUPERSEDED=0
```
