# TELCHI Data Lake Reference V2 rebuild and reconciliation V1

## Resultado

`TELCHI_DATALAKE_REFERENCE_V2_REBUILD_AND_RECONCILIATION_V1_PASS`

Reference V2 fue construido físicamente, reconciliado y promovido de forma lógica. Reference y Crosswalk V1 permanecen byte a byte intactos. El gate no consultó SAP, no modificó PostgreSQL ni DuckLake y no creó Atomic, Business o Current.

## Fuentes y builder

El builder reproducible vive en `investigation/validation/datalake_reference_v2_rebuild_and_reconciliation_v1/build_outputs.py` y soporta `--check`, `--build` y `--verify`. El build fue offline y usó exclusivamente:

- Reference/Crosswalk V1 materializado;
- contratos V2 machine-readable de `datalake_product_and_operating_model_contract_v2/`;
- evidencia y lineage ya preservados por V1.

Los comandos son:

```bash
cd SrvRestAstroLS_v1/backend
uv run python -m modules.telchi.investigation.validation.datalake_reference_v2_rebuild_and_reconciliation_v1.build_outputs --check
uv run python -m modules.telchi.investigation.validation.datalake_reference_v2_rebuild_and_reconciliation_v1.build_outputs --build
uv run python -m modules.telchi.investigation.validation.datalake_reference_v2_rebuild_and_reconciliation_v1.build_outputs --verify
```

`--verify` es offline. No necesita SAP porque todos los inputs quedaron materializados antes de este gate.

## Estrategia física, promoción y rollback

V2 se construye primero en `staging/reference_v2_rebuild/<build_id>/` y sólo después de validar contrato, legibilidad, integridad referencial y fingerprints V1 se publica en:

- `reference/_versions/v2/`;
- `crosswalk/_versions/v2/`.

La versión vigente se declara en `manifests/reference_current.json`. El pointer conserva rutas V1 y V2 y permite rollback lógico a V1 sin reconstrucción ni rename destructivo. No se usan symlinks. Reference V2 no está gestionado por DuckLake.

## Las 21 entidades contractuales

La lista no está hardcodeada como objetivo: el builder deriva V2 de las 14 entidades V1, las migraciones y `reference_schema_contract.csv`, y contrasta el resultado con `reference_v2_designed_count` del summary contractual.

1. branches
2. brand
3. business_unit
4. currencies
5. customers
6. document_types
7. operating_domain
8. operating_model
9. party
10. payment_terms
11. portfolio_family
12. product_business_type
13. production_site
14. products
15. sales_channel
16. salespersons
17. suppliers
18. units_of_measure
19. users
20. warehouse_roles
21. warehouses

`product_groups → portfolio_family` se implementó como migración y reclasificación semántica, no como simple rename. Los 78 grupos V1 no se declararon familias de portafolio. `channels → sales_channel` se implementó como equivalente contractual; ambos estaban vacíos por falta de una autoridad aprobada.

## Producto, IDs y reglas

Los 53.318 IDs canónicos V1 se preservaron; no hay IDs nuevos o cambiados. V2 separa identidad (`canonical_product_id`, código, nombre y evidencia UoM) de clasificaciones y relaciones temporales.

Las únicas reglas automáticas son explícitas y versionadas en `classification_rules.csv`:

- `L_PREFIX_PORTFOLIO_V1`: evidencia histórica `L* → LITEL`;
- `M_PREFIX_PORTFOLIO_V1`: evidencia histórica `M* → MEDICATION_OR_MEDI`.

Ambas producen mappings `PROVISIONAL`; no afirman brand, fabricante, business unit, sitio ni operating model. El consumo de Litel une `product_portfolio_family` con el catálogo y filtra `portfolio_family.code='LITEL'`; no usa `LIKE 'L%'`.

Cobertura de portfolio: 23.542 mappings provisionales (7.158 Litel y 16.384 Medication/Medi) y 29.776 `UNMAPPED`. No se creó `OTHER`.

## Taxonomías, relaciones y gaps

Los valores de catálogo materializados provienen del contrato V2:

- product business type: tres valores provisionales;
- operating domain: tres valores provisionales;
- operating model: seis valores provisionales.

Brand, business unit, production site y sales channel permanecen estructuralmente listos pero sin filas inventadas. Las diez relaciones V2 fueron materializadas bajo Crosswalk V2; sólo `product_portfolio_family` tiene mappings. Las demás quedan vacías hasta recibir evidencia. Los intervalos desconocidos permanecen `NULL`.

`party`, `product_manufacturer`, `brand_owner` y `manufacturing_arrangement` permiten representar white-label sin columnas por cliente. El contrato de magistral permanece separado del industrial y permite cliente, preparación, botica/site y tipo sin exigir una orden industrial. Esto prueba representabilidad, no identificación histórica.

Los 17 gaps se mantienen explícitos. Tener estructura no cierra un gap. En particular:

- `BRAND_AUTHORITY=PARTIAL`;
- `BUSINESS_UNIT_TAXONOMY_STATUS=PROVISIONAL`;
- white-label identificado: 0;
- mapping histórico magistral: no disponible;
- producción/sitio: sin mappings aprobados.

Estos gaps no bloquean Atomic porque no degradan identidad, schema, determinismo o lineage.

## Aliases y crosswalks

V2 conserva 53.425 aliases V1 evidence-backed, incluidos los casos Creolina y Saavedra. Hay 24.270 filas marcadas `AMBIGUOUS`; no existe first-match silencioso. Segundo Anillo permanece unresolved porque no apareció evidencia nueva.

Los ocho crosswalks V1 se preservan dentro del namespace V2 y se agregan diez relaciones contractuales, dando 18 datasets físicos. Warehouse y branch continúan separados. La relación V1 conserva 51 mappings confirmados y 82 warehouses sin mapping; las 133 vigencias son desconocidas.

## Determinismo, performance y calidad

Dos builds consecutivos produjeron hashes físicos idénticos para todos los Parquet V2. El build ID deriva de los hashes V1. No se usan UUID aleatorios, orden arbitrario ni first-match.

Benchmark focalizado de alias y dimensiones:

- p50: 0,828 ms;
- p95: 8,278 ms;
- máximo: 8,390 ms.

El target p95 menor o igual a 20 ms se cumple. Los manifests registran paths, versiones, filas, bytes, hashes, build ID, fuente y estado. La evidencia estructurada del gate está en `investigation/validation/datalake_reference_v2_rebuild_and_reconciliation_v1/evidence/`.

## Acceso y límites

- `SAP_ACCESSED=NO`; se reutilizaron snapshots V1.
- `SAP_WRITE_COUNT=0`.
- `POSTGRES_MODIFIED=NO`.
- `DUCKLAKE_MODIFIED=NO`.
- `ATOMIC_TABLES_CREATED=0`.
- `BUSINESS_TABLES_CREATED=0`.
- `CURRENT_TABLES_CREATED=0`.
- `SECRET_LEAKS_FOUND=0`.

## Readiness para Atomic

`REFERENCE_V2_READY_FOR_ATOMIC=YES`. El schema está completo, los IDs son estables, los desconocidos no fueron inventados, las relaciones son válidas, Litel quedó materializado, el lineage es reproducible y V2 es idempotente. Atomic no fue iniciado. El próximo gate previsto puede ser `TELCHI_DATALAKE_ATOMIC_INVENTORY_AND_SALES_V1`, sujeto a revisión explícita.

## Output obligatorio

```text
GATE=TELCHI_DATALAKE_REFERENCE_V2_REBUILD_AND_RECONCILIATION_V1
DATA_ROOT=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi
REFERENCE_V1_DATASETS=14
REFERENCE_V2_EXPECTED=21
REFERENCE_V2_CREATED=21
REFERENCE_V2_PHYSICAL_PATH=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi/reference/_versions/v2
REFERENCE_V2_DUCKLAKE_MANAGED=NO
CROSSWALK_V1_DATASETS=8
CROSSWALK_V2_DATASETS=18
CANONICAL_PRODUCTS_V2=53318
CANONICAL_PRODUCT_IDS_PRESERVED=53318
CANONICAL_PRODUCT_IDS_NEW=0
CANONICAL_PRODUCT_IDS_CHANGED=0
PORTFOLIO_FAMILY_MAPPED=23542
PORTFOLIO_FAMILY_UNMAPPED=29776
LITEL_PRODUCTS=7158
MEDICATION_PRODUCTS=16384
PRODUCT_BUSINESS_TYPE_MAPPED=0
PRODUCT_BUSINESS_TYPE_PROVISIONAL=0
PRODUCT_BUSINESS_TYPE_UNMAPPED=53318
BRAND_MAPPED=0
BRAND_UNMAPPED=53318
BUSINESS_UNIT_MAPPED=0
BUSINESS_UNIT_PROVISIONAL=0
BUSINESS_UNIT_UNMAPPED=53318
OPERATING_DOMAIN_MAPPED=0
OPERATING_DOMAIN_UNMAPPED=53318
OPERATING_MODEL_MAPPED=0
OPERATING_MODEL_PROVISIONAL=0
OPERATING_MODEL_UNMAPPED=53318
PRODUCTION_SITES=0
PRODUCT_PRODUCTION_SITE_MAPPED=0
PRODUCT_PRODUCTION_SITE_UNMAPPED=53318
PRODUCTION_SITE_WAREHOUSE_MAPPED=0
PRODUCTION_SITE_WAREHOUSE_UNMAPPED=82
TEMPORAL_VALIDITY_UNKNOWN=133
WHITE_LABEL_REPRESENTABLE=YES
WHITE_LABEL_IDENTIFIED_COUNT=0
WHITE_LABEL_UNRESOLVED=YES
MAGISTRAL_REPRESENTABLE_WITHOUT_INDUSTRIAL_MODEL=YES
MAGISTRAL_REFERENCE_MAPPED=0
MAGISTRAL_REFERENCE_UNMAPPED=0
TELCHI_PRODUCT_DISTINCT_FROM_MANUFACTURED_BY_TELCHI=YES
MANUFACTURED_BY_TELCHI_DISTINCT_FROM_BRAND_OWNERSHIP=YES
LIKE_L_REQUIRED_AT_QUERY_TIME=NO
CROSSWALK_V2_MAPPED=91122
CROSSWALK_V2_UNMAPPED=82
CROSSWALK_V2_AMBIGUOUS=0
CROSSWALK_V2_PROVISIONAL=0
ALIASES_TOTAL=53425
ALIASES_AMBIGUOUS=24270
ENTITY_RESOLUTION_P50_MS=0.828
ENTITY_RESOLUTION_P95_MS=8.278
ENTITY_RESOLUTION_MAX_MS=8.39
REFERENCE_V1_FILES_MODIFIED=0
REFERENCE_V1_FILES_DELETED=0
REFERENCE_V1_FILES_MOVED=0
CROSSWALK_V1_FILES_MODIFIED=0
CROSSWALK_V1_FILES_DELETED=0
CROSSWALK_V1_FILES_MOVED=0
SECOND_RUN_IDEMPOTENT=YES
REFERENCE_V2_ROLLBACK_READY=YES
SAP_ACCESSED=NO
SAP_ACCESS_PURPOSE=NONE
SAP_WRITE_COUNT=0
POSTGRES_MODIFIED=NO
DUCKLAKE_MODIFIED=NO
ATOMIC_TABLES_CREATED=0
BUSINESS_TABLES_CREATED=0
CURRENT_TABLES_CREATED=0
KNOWN_SEMANTIC_GAPS_BEFORE=17
KNOWN_SEMANTIC_GAPS_AFTER=17
REFERENCE_V2_RECONCILED=YES
REFERENCE_V2_READY_FOR_ATOMIC=YES
SECRET_LEAKS_FOUND=0
TELCHI_DATALAKE_REFERENCE_V2_REBUILD_AND_RECONCILIATION_V1_PASS
```

STOP AND REVIEW.
