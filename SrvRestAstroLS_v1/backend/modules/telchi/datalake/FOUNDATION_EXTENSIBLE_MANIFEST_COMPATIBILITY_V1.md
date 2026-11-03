# TELCHI_FOUNDATION_EXTENSIBLE_MANIFEST_COMPATIBILITY_V1

Este gate compatibiliza los lectores con extensiones independientes sin promover purchasing ni escribir publicaciones. Contexto: TELCHI, COBRANZAS y COMPRAS_Y_ABASTECIMIENTO, DEVELOPMENT; fuente DATA_LAKE materializada, sin SAP.

## A. Por qué falló la promoción

El reader original reproduce el rechazo del candidate `foundation_afd08d9eca6a725be53cdc3f9d5709c9`: `Receivables Foundation manifest kind is missing or wrong`. CURRENT permanece `foundation_d222a203801cc84e9a14164d26aa67a0`.

La promoción anterior no modificó CURRENT. El candidate conserva los siete componentes de CURRENT y snapshot 1322, pero su builder reemplaza `candidate_kind` por `PURCHASING_FOUNDATION_V1` y añade purchasing.

## B. Assumption acoplada

El consumidor confundía identidad del builder con identidad del contrato global y exigía que el conjunto lógico global fuese exactamente su conjunto requerido.

Clasificación demostrada: MANIFEST_KIND_COUPLING, COMPONENT_COUNT_COUPLING, MANIFEST_SCOPE_CONFUSION y PUBLICATION_READER_ASSUMPTION. No se encontró dependencia de un número global de versión; VERSION_CONTRACT_COUPLING no es la causa original.

`candidate_kind` procede de `create_candidate` de cada extensión. Identifica una construcción histórica, no el schema de Receivables ni un publication manifest físico. El siete no es una constante numérica aislada: resulta de comparar sets con `LOGICAL_COMPONENT_NAMES`.

El manifest global contiene un registry `components`; cada entrada contiene identidad y, para componentes lógicos, datasets. Las publicaciones físicas de Atomic están además enlazadas por las cinco columnas históricas del catálogo. Estos scopes se mantienen separados.

## C. Garantía protegida

El conjunto cerrado intentaba impedir componentes incompletos, versiones mezcladas y snapshots ambiguos. Esa integridad sigue siendo obligatoria.

Receivables requiere `reference`, `sales`, `credit_memo`, `oinm`, `oitw`, `material_supply`, `receivables_collections`. Material Supply requiere los primeros seis. El orden del mapping no participa en el contrato; los hashes canónicos ordenan keys.

Los cinco ids del catálogo deben coincidir con el manifest. Receivables verifica fingerprint SHA-256 del contrato estable, identidad derivada del fingerprint, versión de derivación compatible y metadata de sus tres datasets. Los gold/fingerprints físicos prueban los contenidos, además de la resolución metadata.

## D. Preservación de la garantía

Una extensión debe identificar una publicación base exacta, conservar íntegramente sus entradas, catálogo y snapshot, y declarar contratos estables verificables para cada componente adicional.

`foundation_manifest.py` verifica estructura global, identidad del manifest, nombres únicos, ids no ambiguos, schema, ancestry y ausencia de ciclos. También verifica identidad SHA-256 de extras, hashes de datasets, referencias físicas declaradas y provenance/dependencies. Los hashes físicos se comprueban en la revalidación específica del componente; Receivables no ejecuta cálculos purchasing.

El contrato estable de cada extra enlaza `foundation_publication_id`, `base_snapshot_id`, `reference_version` y hash canónico del registry base completo. Se rechaza cualquier alteración de un componente base, incluso si su id no cambió. La base se obtiene por id explícito, admite CURRENT/SUPERSEDED y nunca se elige por recencia.

## E. Qué cambió

La corrección separa el envelope extensible del conjunto requerido por cada consumidor. No convierte una cantidad exacta en una comparación numérica abierta.

- `foundation_manifest.py`: validador de envelopes y registry extensible.
- `receivables_collections_foundation.py`: valida siete dependencias propias y conserva solo esas siete en `component_versions`; refuerza identity/schema/dataset checks.
- `material_supply_candidate.py`: compatibiliza exclusivamente el lector CURRENT y conserva seis dependencias propias.
- `foundation_publication.py`: rechaza keys JSON duplicadas antes de convertirlas en un dict; el manifest corrupto conserva el fallo cerrado existente.
- `tests/test_receivables_collections_foundation.py`: matriz negativa, legacy y extensiones sucesivas hasta nueve componentes.
- Runner `investigation/validation/foundation_extensible_manifest_compatibility_v1/run_gate.py`: evidencia read-only contra publicaciones reales, motor gold existente y replay purchasing.

La superficie supera cinco archivos porque el segundo lector productivo también bloqueaba extensiones y los duplicados JSON deben detectarse en el repository antes de perderse. No cambia infraestructura transversal de Team360.

## F. Qué no cambió

CURRENT, candidate purchasing, datasets, lógica analítica, gold esperados, fingerprints y publications históricas permanecen intactos. No hubo rebuild, promoción, deploy, commit ni consultas SAP.

Los constructores y validadores de candidates históricos conservan sus precondiciones cerradas: verifican una construcción específica. No se amplió su scope a un registry global.

Se preservó el cambio preexistente en `PURCHASING_V1.md`; no se editó `investigation/STATUS_ACTUAL.md`, frontend, providers, knowledge, AG-UI ni otros módulos.

## G. Backward compatibility

La evidencia previa registra CURRENT, todas las filas de publications, pointer completo, gold, cuatro hashes analíticos y fingerprints de todas las columnas analíticas de Receivables.

El runner compara el lector original de HEAD con el corregido y verifica CURRENT antes/después, identidad de componentes, snapshot, counts, montos, settlement, gold y fingerprints. Compara también todas las filas del catálogo y pointer, no solamente el id CURRENT.

Rama de trabajo: `feature/console-backend-core`. El objetivo está limitado a compatibilidad estructural de Foundation y sus lectores.

Counts preservados: 1,859,136 settlement rows, 1,849,408 collection-method rows y 37 commercial-term rows. Settlement: 1,854,836 documentos liquidados, 2,024 abiertos, 44 parciales y 2,232 excluidos. Deuda actual: BOB 4,263,720.23.

Se prueban `foundation_f1ebdb312ae595638c3a3bffbda78629`, `foundation_39e17f1559525d2ca9bd04e17765b750` y `foundation_417c860c216805f18341bb741ee026e3`. Las históricas con Receivables mantienen aceptación/gold; las anteriores sin ese componente mantienen el rechazo específico del consumidor.

## H. Forward compatibility y versioning

El candidate original se admite mediante un adapter explícito del envelope purchasing existente, con base inmutable y validación de extras. No se cambia arbitrariamente su kind ni se reescribe su manifest.

Los builders futuros pueden emitir `candidate_kind=FOUNDATION_EXTENSIBLE_V1`, `manifest_schema_version=1.0.0` y `base_foundation_publication_id` explícito. Cada extra usa el contrato estable ya descrito. El reader no enumera nombres de componentes futuros.

Los kinds legacy `MATERIAL_SUPPLY_V1` y `RECEIVABLES_COLLECTIONS_FOUNDATION_V1` siguen legibles con su registry histórico. Una adición bajo un kind legacy sin provenance de extensión falla. Schemas desconocidos o kind arbitrario fallan.

Los tests prueban N→N+1→N+2 con nombres independientes de purchasing. El candidate real reproduce los mismos resultados Receivables y mantiene purchasing fuera de sus dependencias.

## I. Otros consumidores inspeccionados

El inventario contiene nueve consumidores o familias adicionales al lector Receivables. La búsqueda cubre backend y los gates históricos; ninguna coincidencia se cambia automáticamente.

| Consumidor o familia | Clasificación | Evidencia/acción |
| --- | --- | --- |
| Material Supply CURRENT | SAME_COUPLING → corregido | Kind cerrado y seis componentes globales; subset contractual estricto y prueba sobre candidate con overlay read-only |
| FoundationReader y open_current helpers | SAFE | Valida cinco ids y pinning; registry de tablas limita acceso propio, no total de componentes |
| FoundationPublication metadata/commit | SAFE | Count cinco corresponde a columnas catálogo, no total lógico; no se altera |
| Executive Sales | SAFE | Usa FoundationReader y relaciones propias |
| Material Supply pinned validator | NOT_APPLICABLE | Valida candidate histórico de construcción específica, no consumidor CURRENT extensible |
| Purchasing pinned validator | NOT_APPLICABLE | Gate específico del candidate exacto con ocho componentes; se revalida sin promoción |
| Builders de extensiones históricos | NOT_APPLICABLE | Precondiciones de construcción, no lectura productiva |
| Manual update producer | NOT_APPLICABLE | Contrato de cinco componentes catálogo; mantenimiento separado |
| CG2A V3 y gates investigativos históricos | NOT_APPLICABLE | Esperan publicación/gate histórico explícito; su assert siete no controla runtime productivo |

No quedan lectores productivos conocidos que bloqueen la octava entrada por count/kind. El pinning productivo del candidate se simula solo con overlay en memoria; resolver su primer snapshot CURRENT real corresponde al gate posterior de promoción.

## J. Riesgos y siguiente paso

El modelo extensible es conservador: añade componentes y mantiene toda la base exacta. Cambiar dependencias existentes o un schema mayor requiere otro contrato/gate; no está autorizado por esta compatibilidad.

Las publicaciones base deben seguir disponibles para probar provenance. Ancestry se limita a 32 extensiones y rechaza ciclos. Los archivos extras se validan físicamente por su reader/gate específico; el envelope valida su declaración estructural e identidad estable.

El gold histórico de 2026-08-31 conserva `OPEN_DEBT_PARTITION=FAIL`, una salida previamente sellada (diferencia de 0.02 entre particiones y total). No se corrige ni se oculta: el gate prueba igualdad exacta de outputs y flags, no redefine esa semántica.

El próximo gate puede intentar promover el mismo candidate cuando todas las validaciones finales aquí estén cerradas. Este gate termina antes de esa operación.

## Validaciones y evidencia

Los comandos siguientes ejercitan código local, publicaciones materializadas y documentación. La evidencia generada vive fuera del Data Root, en el directorio canónico de evidence Telchi.

```bash
cd SrvRestAstroLS_v1/backend
uv run pytest modules/telchi/datalake/tests modules/telchi/runtime/tests -q -p no:cacheprovider
uv run python -m modules.telchi.investigation.validation.foundation_extensible_manifest_compatibility_v1.run_gate
```

Evidence root: `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/TELCHI_FOUNDATION_EXTENSIBLE_MANIFEST_COMPATIBILITY_V1`. `before.json` conserva el baseline previo; `root_cause.json`, `receivables_parity.json`, `historical_publications.json`, `purchasing_revalidation.json`, `foundation_fingerprints.json` y `summary.json` documentan el resultado real.

Preflight: conexión DuckLake READ_ONLY, `SELECT 1`, PostgreSQL autenticado, pointer único y publicaciones explícitas presentes. LLM, auth de providers, crédito y Milvus son NOT_APPLICABLE: no participan en estos readers ni se consultan.

Corrida real final: PASS, con Receivables/Foundation parity exacta, purchasing gold/parity/replay PASS y todas las filas de catálogo/pointer sin cambios.

Durante la preparación se corrigieron dos errores del runner: comparación Decimal/JSON sin normalización y comparación de identity candidate contra contexto CURRENT. La corrida completa corregida terminó con exit 0. No se alteraron gold ni expectations.

La suite completa pasó con 335 tests antes del último caso negativo. Una repetición posterior abortó cinco tests de captura por `RESOURCE_BLOCKED: load_ratio_above_maximum`; los otros 331 pasaron. La segunda repetición confirma los mismos cinco abortos ambientales. No se desactivó el guard ni se editaron tests de captura. La validación final focalizada del alcance pasó con 187/187; los cinco abortos de la suite ampliada se reportan como limitación ambiental, no como regresiones de contratos. El gate estructural cumple todos sus criterios.

## Resultado final

El gate de compatibilidad es PASS; las validaciones específicas y materiales reales pasan. La suite ampliada tiene cinco abortos ambientales documentados, por lo que no se declara PASS para esa suite. No se promueve purchasing.

```text
GATE=TELCHI_FOUNDATION_EXTENSIBLE_MANIFEST_COMPATIBILITY_V1_PASS
ROOT_CAUSE=MANIFEST_KIND_COUPLING+COMPONENT_COUNT_COUPLING+MANIFEST_SCOPE_CONFUSION+PUBLICATION_READER_ASSUMPTION
PREVIOUS_CURRENT=foundation_d222a203801cc84e9a14164d26aa67a0
CURRENT_PUBLICATION_ID=foundation_d222a203801cc84e9a14164d26aa67a0
CURRENT_MODIFIED=NO
RECEIVABLES_READER_COMPATIBLE=YES
RECEIVABLES_PARITY=PASS
PURCHASING_CANDIDATE_COMPATIBLE=YES
PURCHASING_CANDIDATE_ID=foundation_afd08d9eca6a725be53cdc3f9d5709c9
PURCHASING_CANDIDATE_REBUILT=NO
ADDITIONAL_COMPONENTS_ALLOWED=YES
REQUIRED_COMPONENT_VALIDATION_STRICT=YES
MANIFEST_KIND_COMPATIBILITY=PASS
NEGATIVE_TESTS=PASS
OTHER_CONSUMERS_CHECKED=9
OTHER_BLOCKING_CONSUMERS=0
VERSION_MIXING=NO
FOUNDATION_PARITY=PASS
SAP_ACCESSED=NO
SAP_QUERY_COUNT=0
SAP_WRITE_COUNT=0
TEST_FAILURES=5
READY_TO_RETRY_PURCHASING_PROMOTION=YES
```

`TEST_FAILURES=5` cuenta los abortos ambientales de la última suite ampliada; los 187 tests focalizados del gate tienen cero fallos. El siguiente gate debe comprobar su propio preflight de recursos y nunca omitirlo. La aptitud estructural no autoriza ni ejecuta promoción.

LAT: `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check` pasan. Warnings existentes: LAT sin init/version y sin key para semantic search; no afectan estos checks.
